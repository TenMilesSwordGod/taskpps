from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from taskpps.config import build_retry_log_path
from taskpps.db.engine import get_session_factory
from taskpps.db.repository import RetryRecordRepository, RunRepository, TaskRunRepository
from taskpps.domain.context import ExecutionContext
from taskpps.domain.pipeline import ResolvedPipeline, ResolvedStep, ResolvedTask
from taskpps.engine.retry_runner import RetryRunner
from taskpps.executors.base import ExecutorResult
from taskpps.models.run import RunStatus, TaskStatus


def _mock_session_factory():
    mock_session = AsyncMock()
    mock_cm = AsyncMock()
    mock_cm.__aenter__ = AsyncMock(return_value=mock_session)
    mock_cm.__aexit__ = AsyncMock(return_value=None)
    mock_factory = MagicMock(return_value=mock_cm)
    return mock_factory, mock_session


@pytest.mark.asyncio
class TestRetryRecordRepository:
    @pytest.mark.zentao("TC-S0384", domain="server/services", priority="P0")
    async def test_create_and_get_retry_record(self, db_engine, clean_db):
        async with get_session_factory()() as session:
            run_repo = RunRepository(session)
            run = await run_repo.create_run(pipeline_name="test", pipeline_file="test.yaml")

            task_repo = TaskRunRepository(session)
            task_run = await task_repo.create_task_run(
                run_id=run.id,
                task_name="sub.t1",
                task_type="command",
            )

            repo = RetryRecordRepository(session)
            record = await repo.create_retry_record(
                run_id=run.id,
                task_run_id=task_run.id,
                task_name="sub.t1",
                subpipeline_name="sub",
                retry_version=1,
                command="echo hello",
                original_command="echo hello",
                log_path="/tmp/test.log",
            )
            assert record.id is not None
            assert record.retry_version == 1
            assert record.status == TaskStatus.PENDING

            fetched = await repo.get_retry_record(record.id)
            assert fetched is not None
            assert fetched.command == "echo hello"

    @pytest.mark.zentao("TC-S0385", domain="server/services", priority="P2")
    async def test_list_retries_by_task(self, db_engine, clean_db):
        async with get_session_factory()() as session:
            run_repo = RunRepository(session)
            run = await run_repo.create_run(pipeline_name="test", pipeline_file="test.yaml")

            task_repo = TaskRunRepository(session)
            task_run = await task_repo.create_task_run(
                run_id=run.id,
                task_name="sub.t1",
                task_type="command",
            )

            repo = RetryRecordRepository(session)
            for v in range(1, 4):
                await repo.create_retry_record(
                    run_id=run.id,
                    task_run_id=task_run.id,
                    task_name="sub.t1",
                    subpipeline_name="sub",
                    retry_version=v,
                    command=f"echo {v}",
                    original_command=f"echo {v}",
                    log_path=f"/tmp/{v}.log",
                )

            records = await repo.list_retries_by_task(run.id, "sub.t1")
            assert len(records) == 3
            assert [r.retry_version for r in records] == [1, 2, 3]

    @pytest.mark.zentao("TC-S0386", domain="server/services", priority="P1")
    async def test_update_retry_status(self, db_engine, clean_db):
        async with get_session_factory()() as session:
            run_repo = RunRepository(session)
            run = await run_repo.create_run(pipeline_name="test")

            task_repo = TaskRunRepository(session)
            task_run = await task_repo.create_task_run(run_id=run.id, task_name="sub.t1")

            repo = RetryRecordRepository(session)
            record = await repo.create_retry_record(
                run_id=run.id,
                task_run_id=task_run.id,
                task_name="sub.t1",
                subpipeline_name="sub",
                retry_version=1,
                command="echo ok",
                original_command="echo ok",
                log_path="/tmp/test.log",
            )

            now = datetime.now(timezone.utc)
            await repo.update_retry_status(
                record.id,
                TaskStatus.SUCCESS,
                exit_code=0,
                finished_at=now,
            )

            updated = await repo.get_retry_record(record.id)
            assert updated.status == TaskStatus.SUCCESS
            assert updated.exit_code == 0
            assert updated.finished_at is not None

    @pytest.mark.zentao("TC-S0387", domain="server/services", priority="P1")
    async def test_get_next_retry_version(self, db_engine, clean_db):
        async with get_session_factory()() as session:
            run_repo = RunRepository(session)
            run = await run_repo.create_run(pipeline_name="test")

            task_repo = TaskRunRepository(session)
            task_run = await task_repo.create_task_run(run_id=run.id, task_name="sub.t1")

            repo = RetryRecordRepository(session)
            v1 = await repo.get_next_retry_version(run.id, "sub.t1")
            assert v1 == 1

            await repo.create_retry_record(
                run_id=run.id,
                task_run_id=task_run.id,
                task_name="sub.t1",
                subpipeline_name="sub",
                retry_version=1,
                command="echo 1",
                original_command="echo 1",
                log_path="/tmp/1.log",
            )

            v2 = await repo.get_next_retry_version(run.id, "sub.t1")
            assert v2 == 2

    @pytest.mark.zentao("TC-S0388", domain="server/services", priority="P2")
    async def test_delete_retries_for_run(self, db_engine, clean_db):
        async with get_session_factory()() as session:
            run_repo = RunRepository(session)
            run = await run_repo.create_run(pipeline_name="test")

            task_repo = TaskRunRepository(session)
            task_run = await task_repo.create_task_run(run_id=run.id, task_name="sub.t1")

            repo = RetryRecordRepository(session)
            await repo.create_retry_record(
                run_id=run.id,
                task_run_id=task_run.id,
                task_name="sub.t1",
                subpipeline_name="sub",
                retry_version=1,
                command="echo",
                original_command="echo",
                log_path="/tmp/1.log",
            )

            deleted = await repo.delete_retries_for_run(run.id)
            assert deleted == 1

            records = await repo.list_retries_by_run(run.id)
            assert len(records) == 0


@pytest.mark.asyncio
class TestRetryRunner:
    def _make_pipeline(self, tasks: list[ResolvedTask]) -> ResolvedPipeline:
        from taskpps.domain.pipeline import ResolvedSubPipeline
        from taskpps.schemas.pipeline import PipelineConfig

        config = PipelineConfig()
        sub = ResolvedSubPipeline(name="sub", tasks=tasks, config=config)
        return ResolvedPipeline(name="test", subpipelines=[sub], top_config=config)

    @pytest.mark.zentao("TC-S0389", domain="server/services", priority="P0")
    async def test_retry_single_task_success(self):
        tasks = [ResolvedTask(name="t1", task_type="command", command="echo ok")]
        pipeline = self._make_pipeline(tasks)
        ctx = ExecutionContext(pipeline=pipeline, run_id="test_retry")

        runner = RetryRunner(run_id="retry_1", pipeline=pipeline, context=ctx)

        mock_executor = AsyncMock()
        mock_executor.execute.return_value = ExecutorResult(exit_code=0, stdout="ok")

        task_plan = [
            {
                "name": "sub.t1",
                "command": "echo ok",
                "retry_record_id": "rec_1",
                "log_path": "/tmp/retry_1.log",
            }
        ]

        runner._update_record = AsyncMock()

        with (
            patch("taskpps.engine.retry_runner.create_executor", return_value=mock_executor),
            patch("taskpps.engine.retry_runner.get_event_bus"),
        ):
            results = await runner.retry_tasks(task_plan)

        assert "sub.t1" in results
        assert results["sub.t1"].success

    @pytest.mark.zentao("TC-S0390", domain="server/services", priority="P1")
    async def test_retry_single_task_failure(self):
        tasks = [ResolvedTask(name="t1", task_type="command", command="exit 1")]
        pipeline = self._make_pipeline(tasks)
        ctx = ExecutionContext(pipeline=pipeline, run_id="test_retry")

        runner = RetryRunner(run_id="retry_1", pipeline=pipeline, context=ctx)

        mock_executor = AsyncMock()
        mock_executor.execute.return_value = ExecutorResult(exit_code=1, stderr="fail")

        task_plan = [
            {
                "name": "sub.t1",
                "command": "exit 1",
                "retry_record_id": "rec_1",
                "log_path": "/tmp/retry_2.log",
            }
        ]

        runner._update_record = AsyncMock()

        with (
            patch("taskpps.engine.retry_runner.create_executor", return_value=mock_executor),
            patch("taskpps.engine.retry_runner.get_event_bus"),
        ):
            results = await runner.retry_tasks(task_plan)

        assert not results["sub.t1"].success

    @pytest.mark.zentao("TC-S0391", domain="server/services", priority="P1")
    async def test_retry_custom_command_override(self):
        tasks = [ResolvedTask(name="t1", task_type="command", command="original")]
        pipeline = self._make_pipeline(tasks)
        ctx = ExecutionContext(pipeline=pipeline, run_id="test_retry")

        runner = RetryRunner(run_id="retry_1", pipeline=pipeline, context=ctx)

        mock_executor = AsyncMock()
        mock_executor.execute.return_value = ExecutorResult(exit_code=0, stdout="overridden")

        task_plan = [
            {
                "name": "sub.t1",
                "command": "echo custom_command",
                "retry_record_id": "rec_1",
                "log_path": "/tmp/retry_3.log",
            }
        ]

        runner._update_record = AsyncMock()

        with (
            patch("taskpps.engine.retry_runner.create_executor", return_value=mock_executor),
            patch("taskpps.engine.retry_runner.get_event_bus"),
        ):
            await runner.retry_tasks(task_plan)

        assert mock_executor.execute.call_count == 1
        call_kwargs = mock_executor.execute.call_args[1]
        assert call_kwargs["command"] == "echo custom_command"

    @pytest.mark.zentao("TC-S0392", domain="server/services", priority="P1")
    async def test_retry_task_not_found(self):
        pipeline = self._make_pipeline([])
        ctx = ExecutionContext(pipeline=pipeline, run_id="test_retry")

        runner = RetryRunner(run_id="retry_1", pipeline=pipeline, context=ctx)

        task_plan = [
            {
                "name": "sub.nonexistent",
                "command": "echo",
                "retry_record_id": "rec_x",
                "log_path": "/tmp/x.log",
            }
        ]

        mock_factory, mock_session = _mock_session_factory()

        runner._update_record = AsyncMock()

        with (
            patch("taskpps.engine.retry_runner.get_event_bus"),
        ):
            results = await runner.retry_tasks(task_plan)

        assert "sub.nonexistent" in results
        assert not results["sub.nonexistent"].success
        assert "not found" in (results["sub.nonexistent"].stderr or "")

    @pytest.mark.zentao("TC-S0393", domain="server/services", priority="P1")
    async def test_retry_cancelled(self):
        tasks = [ResolvedTask(name="t1", task_type="command", command="echo ok")]
        pipeline = self._make_pipeline(tasks)
        ctx = ExecutionContext(pipeline=pipeline, run_id="test_retry")

        runner = RetryRunner(run_id="retry_1", pipeline=pipeline, context=ctx)
        runner._update_record = AsyncMock()
        await runner.cancel()

        task_plan = [
            {
                "name": "sub.t1",
                "command": "echo ok",
                "retry_record_id": "rec_1",
                "log_path": "/tmp/cancel.log",
            }
        ]

        with (
            patch("taskpps.engine.retry_runner.get_event_bus"),
        ):
            results = await runner.retry_tasks(task_plan)

        assert "sub.t1" in results
        assert not results["sub.t1"].success

    @pytest.mark.zentao("TC-S0394", domain="server/services", priority="P1")
    async def test_retry_cancels_running_executor(self):
        """Issue #102: 取消进行中的重试时应终止正在执行的 executor。"""
        tasks = [ResolvedTask(name="t1", task_type="command", command="sleep 10")]
        pipeline = self._make_pipeline(tasks)
        ctx = ExecutionContext(pipeline=pipeline, run_id="test_retry")

        runner = RetryRunner(run_id="retry_cancel_running", pipeline=pipeline, context=ctx)
        runner._update_record = AsyncMock()

        started = asyncio.Event()
        stop_event = asyncio.Event()
        mock_executor = AsyncMock()

        async def _long_execute(*_args, **_kwargs):
            started.set()
            try:
                await asyncio.wait_for(stop_event.wait(), timeout=10)
            except asyncio.TimeoutError:
                return ExecutorResult(exit_code=0, stdout="ok")
            return ExecutorResult(exit_code=-1, stdout="cancelled")

        async def _cancel():
            stop_event.set()

        mock_executor.execute.side_effect = _long_execute
        mock_executor.cancel = AsyncMock(side_effect=_cancel)

        task_plan = [
            {
                "name": "sub.t1",
                "command": "sleep 10",
                "retry_record_id": "rec_1",
                "log_path": "/tmp/cancel_running.log",
            }
        ]

        with (
            patch("taskpps.engine.retry_runner.create_executor", return_value=mock_executor),
            patch("taskpps.engine.retry_runner.get_event_bus"),
        ):
            retry_task = asyncio.create_task(runner.retry_tasks(task_plan))
            await asyncio.wait_for(started.wait(), timeout=1)
            await runner.cancel()
            results = await asyncio.wait_for(retry_task, timeout=2)

        assert "sub.t1" in results
        assert not results["sub.t1"].success
        mock_executor.cancel.assert_awaited_once()

    @pytest.mark.zentao("TC-S0395", domain="server/services", priority="P1")
    async def test_retry_sequential_strategy_runs_one_at_a_time(self):
        tasks = [
            ResolvedTask(name="t1", task_type="command", command="echo 1"),
            ResolvedTask(name="t2", task_type="command", command="echo 2"),
        ]
        pipeline = self._make_pipeline(tasks)
        ctx = ExecutionContext(pipeline=pipeline, run_id="test_retry")

        runner = RetryRunner(run_id="retry_seq", pipeline=pipeline, context=ctx, execution_strategy="sequential")

        events: list[tuple[str, str]] = []

        def _fake_create_executor(task, *_args, **_kwargs):
            mock_executor = AsyncMock()

            async def _execute(*args, **kwargs):
                events.append((task.name, "start"))
                await asyncio.sleep(0.01)
                events.append((task.name, "end"))
                return ExecutorResult(exit_code=0, stdout="ok")

            mock_executor.execute.side_effect = _execute
            return mock_executor

        task_plan = [
            {"name": "sub.t1", "command": "echo 1", "retry_record_id": "rec_1", "log_path": "/tmp/r1.log"},
            {"name": "sub.t2", "command": "echo 2", "retry_record_id": "rec_2", "log_path": "/tmp/r2.log"},
        ]

        runner._update_record = AsyncMock()

        with (
            patch("taskpps.engine.retry_runner.create_executor", side_effect=_fake_create_executor),
            patch("taskpps.engine.retry_runner.get_event_bus"),
        ):
            results = await runner.retry_tasks(task_plan)

        assert all(r.success for r in results.values())
        # sequential: t1 start -> t1 end -> t2 start -> t2 end
        assert events == [("t1", "start"), ("t1", "end"), ("t2", "start"), ("t2", "end")]

    @pytest.mark.zentao("TC-S0396", domain="server/services", priority="P1")
    async def test_retry_parallel_strategy_runs_concurrently(self):
        tasks = [
            ResolvedTask(name="t1", task_type="command", command="echo 1"),
            ResolvedTask(name="t2", task_type="command", command="echo 2"),
        ]
        pipeline = self._make_pipeline(tasks)
        ctx = ExecutionContext(pipeline=pipeline, run_id="test_retry")

        runner = RetryRunner(run_id="retry_par", pipeline=pipeline, context=ctx, execution_strategy="parallel")

        events: list[tuple[str, str]] = []
        t1_started = asyncio.Event()
        t2_started = asyncio.Event()

        def _fake_create_executor(task, *_args, **_kwargs):
            mock_executor = AsyncMock()

            async def _execute(*args, **kwargs):
                events.append((task.name, "start"))
                if task.name == "t1":
                    t1_started.set()
                    await asyncio.wait_for(t2_started.wait(), timeout=1)
                else:
                    t2_started.set()
                    await asyncio.wait_for(t1_started.wait(), timeout=1)
                events.append((task.name, "end"))
                return ExecutorResult(exit_code=0, stdout="ok")

            mock_executor.execute.side_effect = _execute
            return mock_executor

        task_plan = [
            {"name": "sub.t1", "command": "echo 1", "retry_record_id": "rec_1", "log_path": "/tmp/r1.log"},
            {"name": "sub.t2", "command": "echo 2", "retry_record_id": "rec_2", "log_path": "/tmp/r2.log"},
        ]

        runner._update_record = AsyncMock()

        with (
            patch("taskpps.engine.retry_runner.create_executor", side_effect=_fake_create_executor),
            patch("taskpps.engine.retry_runner.get_event_bus"),
        ):
            results = await runner.retry_tasks(task_plan)

        assert all(r.success for r in results.values())
        # parallel: both start before either ends
        assert events.index(("t2", "start")) < events.index(("t1", "end"))

    @pytest.mark.zentao("TC-S0397", domain="server/services", priority="P1")
    async def test_retry_parallel_max_parallel_queues_extra_tasks(self):
        """
        Issue #100: RetryRunner 的 max_parallel 限制总并发数。
        当并行任务数超过 max_parallel 时，多余任务应排队等待。
        """
        tasks = [
            ResolvedTask(name="t1", task_type="command", command="echo 1"),
            ResolvedTask(name="t2", task_type="command", command="echo 2"),
            ResolvedTask(name="t3", task_type="command", command="echo 3"),
        ]
        pipeline = self._make_pipeline(tasks)
        ctx = ExecutionContext(pipeline=pipeline, run_id="test_retry")

        # max_parallel=1，三个并行任务只能串行执行
        runner = RetryRunner(
            run_id="retry_par_1",
            pipeline=pipeline,
            context=ctx,
            execution_strategy="parallel",
            max_parallel=1,
        )

        events: list[str] = []
        gate = asyncio.Event()

        def _fake_create_executor(task, *_args, **_kwargs):
            mock_executor = AsyncMock()

            async def _execute(*args, **kwargs):
                events.append(f"start:{task.name}")
                await gate.wait()
                events.append(f"end:{task.name}")
                return ExecutorResult(exit_code=0, stdout="ok")

            mock_executor.execute.side_effect = _execute
            return mock_executor

        task_plan = [
            {"name": "sub.t1", "command": "echo 1", "retry_record_id": "rec_1", "log_path": "/tmp/r1.log"},
            {"name": "sub.t2", "command": "echo 2", "retry_record_id": "rec_2", "log_path": "/tmp/r2.log"},
            {"name": "sub.t3", "command": "echo 3", "retry_record_id": "rec_3", "log_path": "/tmp/r3.log"},
        ]

        runner._update_record = AsyncMock()

        async def run_retry():
            with (
                patch("taskpps.engine.retry_runner.create_executor", side_effect=_fake_create_executor),
                patch("taskpps.engine.retry_runner.get_event_bus"),
            ):
                return await runner.retry_tasks(task_plan)

        retry_task = asyncio.create_task(run_retry())
        # 等待第一个任务启动并占满信号量
        for _ in range(50):
            if events:
                break
            await asyncio.sleep(0.01)
        assert len(events) == 1 and events[0].startswith("start:")

        gate.set()
        results = await retry_task

        assert all(r.success for r in results.values())
        # 由于 max_parallel=1，三个任务实际串行：start->end->start->end...
        for i in range(0, len(events) - 1):
            if events[i].startswith("start:"):
                # 每个 start 后必须紧跟 end
                assert events[i + 1] == f"end:{events[i].split(':')[1]}"

    @pytest.mark.zentao("TC-S0413", domain="server/services", priority="P0")
    async def test_retry_steps_task_executes_each_step(self):
        """v2 (2026-07): retry_runner 修复后，steps 任务应逐条送 step.run 到 executor，
        而非传 command="" 导致空跑。
        """
        steps = [
            ResolvedStep(run="echo step1"),
            ResolvedStep(run="echo step2"),
            ResolvedStep(run="echo step3"),
        ]
        tasks = [ResolvedTask(name="t1", task_type="steps", steps=steps)]
        pipeline = self._make_pipeline(tasks)
        ctx = ExecutionContext(pipeline=pipeline, run_id="test_steps_retry")

        runner = RetryRunner(run_id="r1", pipeline=pipeline, context=ctx)

        mock_executor = AsyncMock()
        mock_executor.execute.return_value = ExecutorResult(exit_code=0, stdout="ok")

        task_plan = [
            {
                "name": "sub.t1",
                "command": "",  # steps 任务 retry_record 的 command 为空（无单命令）
                "retry_record_id": "rec_1",
                "log_path": "/tmp/steps_retry.log",
            }
        ]

        runner._update_record = AsyncMock()

        with (
            patch("taskpps.engine.retry_runner.create_executor", return_value=mock_executor),
            patch("taskpps.engine.retry_runner.get_event_bus"),
        ):
            results = await runner.retry_tasks(task_plan)

        assert "sub.t1" in results
        assert results["sub.t1"].success

        # 核心断言：executor.execute 被调用 3 次（每个 step 一次），
        # 而非原来传 command="" 仅被调用 1 次
        assert mock_executor.execute.call_count == 3

        # 每次调用的 command kwarg 应对应各个 step.run
        calls = [call.kwargs["command"] for call in mock_executor.execute.call_args_list]
        assert calls == ["echo step1", "echo step2", "echo step3"]

    @pytest.mark.zentao("TC-S0414", domain="server/services", priority="P0")
    async def test_retry_commands_task_executes_each_command(self):
        """v2 (2026-07): retry_runner 修复后，commands 任务应逐条送 cmd 到 executor，
        而非 "\n".join 后仅送一条多行命令。
        """
        tasks = [ResolvedTask(name="t1", task_type="command", commands=["echo cmd1", "echo cmd2"])]
        pipeline = self._make_pipeline(tasks)
        ctx = ExecutionContext(pipeline=pipeline, run_id="test_cmds_retry")

        runner = RetryRunner(run_id="r2", pipeline=pipeline, context=ctx)

        mock_executor = AsyncMock()
        mock_executor.execute.return_value = ExecutorResult(exit_code=0, stdout="ok")

        task_plan = [
            {
                "name": "sub.t1",
                "command": "",  # commands 任务 retry_record 的 command 为空
                "retry_record_id": "rec_2",
                "log_path": "/tmp/cmds_retry.log",
            }
        ]

        runner._update_record = AsyncMock()

        with (
            patch("taskpps.engine.retry_runner.create_executor", return_value=mock_executor),
            patch("taskpps.engine.retry_runner.get_event_bus"),
        ):
            results = await runner.retry_tasks(task_plan)

        assert "sub.t1" in results
        assert results["sub.t1"].success

        # 每个 command 一条 execute 调用
        assert mock_executor.execute.call_count == 2
        calls = [call.kwargs["command"] for call in mock_executor.execute.call_args_list]
        assert calls == ["echo cmd1", "echo cmd2"]

    @pytest.mark.zentao("TC-S0415", domain="server/services", priority="P1")
    async def test_retry_steps_task_with_per_step_cd_and_env(self):
        """v2 (2026-07): steps 任务重试时，每步的 cd 和 env 覆盖应正确传递到 executor。"""
        steps = [
            ResolvedStep(run="echo step1", cd="/tmp", env={"A": "1"}),
            ResolvedStep(run="echo step2", cd="/var", env={"B": "2"}),
        ]
        tasks = [ResolvedTask(name="t1", task_type="steps", steps=steps)]
        pipeline = self._make_pipeline(tasks)
        ctx = ExecutionContext(pipeline=pipeline, run_id="test_steps_per")
        runner = RetryRunner(run_id="r3", pipeline=pipeline, context=ctx)

        mock_executor = AsyncMock()
        mock_executor.execute.return_value = ExecutorResult(exit_code=0, stdout="ok")

        task_plan = [
            {"name": "sub.t1", "command": "", "retry_record_id": "rec_3", "log_path": "/tmp/sp.log"}
        ]

        runner._update_record = AsyncMock()

        with (
            patch("taskpps.engine.retry_runner.create_executor", return_value=mock_executor),
            patch("taskpps.engine.retry_runner.get_event_bus"),
        ):
            await runner.retry_tasks(task_plan)

        calls = mock_executor.execute.call_args_list
        # Step 1: cwd="/tmp", env contains A=1
        assert calls[0].kwargs["cwd"] == "/tmp"
        assert calls[0].kwargs["env"].get("A") == "1"
        # Step 2: cwd="/var", env contains B=2
        assert calls[1].kwargs["cwd"] == "/var"
        assert calls[1].kwargs["env"].get("B") == "2"


@pytest.mark.asyncio
class TestPipelineServiceRetry:
    @pytest.mark.zentao("TC-S0398", domain="server/services", priority="P1")
    async def test_retry_run_returns_immediately_with_pending_status(self, db_engine, clean_db):
        """Issue #98: retry_run 应立即返回，重试在后台执行，记录状态为 PENDING。"""
        from taskpps.services.pipeline_service import PipelineService

        async with get_session_factory()() as session:
            run_repo = RunRepository(session)
            task_repo = TaskRunRepository(session)

            run = await run_repo.create_run(
                pipeline_name="deploy",
                pipeline_file="deploy.yaml",
                params={"env": {"GLOBAL_VAR": "global_value"}},
            )
            await task_repo.create_task_run(
                run_id=run.id,
                task_name="sub.step1",
                task_type="command",
                subpipeline_name="sub",
            )

        import taskpps.config as cfg

        cfg._settings = None
        cfg.load_settings(str(cfg.find_project_root() / "taskpps.yaml"))

        service = PipelineService()
        with patch.object(service, "_load_resolved_pipeline") as mock_load:
            mock_pipeline = MagicMock()
            mock_task1 = ResolvedTask(name="step1", task_type="command", command="echo hello")
            from taskpps.domain.pipeline import ResolvedSubPipeline
            from taskpps.schemas.pipeline import PipelineConfig

            mock_sub = ResolvedSubPipeline(name="sub", tasks=[mock_task1], config=PipelineConfig())
            mock_pipeline.subpipelines = [mock_sub]
            mock_pipeline.top_config = PipelineConfig()
            mock_pipeline.get_task_by_name.side_effect = lambda n: {"step1": mock_task1}.get(n)
            mock_load.return_value = mock_pipeline

            with patch("taskpps.services.pipeline_service.RetryRunner") as mock_runner_cls:
                mock_runner = AsyncMock()
                mock_runner_cls.return_value = mock_runner

                result = await service.retry_run(
                    run_id=run.id,
                    tasks=["sub.step1"],
                    include_upstream=False,
                )

                # 让后台任务有机会执行
                await asyncio.sleep(0)

        # API 应立即返回，不等待重试完成
        assert result["run_id"] == run.id
        assert len(result["retry_records"]) == 1
        assert result["retry_records"][0]["task_name"] == "sub.step1"
        # 返回时状态应为 PENDING（重试在后台执行）
        assert result["retry_records"][0]["status"] == "pending"
        # 后台任务应被创建
        mock_runner.retry_tasks.assert_awaited_once()

    @pytest.mark.zentao("TC-S0399", domain="server/services", priority="P1")
    async def test_retry_run_passes_execution_strategy(self, db_engine, clean_db):
        from taskpps.services.pipeline_service import PipelineService

        async with get_session_factory()() as session:
            run_repo = RunRepository(session)
            task_repo = TaskRunRepository(session)

            run = await run_repo.create_run(
                pipeline_name="deploy",
                pipeline_file="deploy.yaml",
            )
            await task_repo.create_task_run(
                run_id=run.id,
                task_name="sub.step1",
                task_type="command",
                subpipeline_name="sub",
            )

        import taskpps.config as cfg

        cfg._settings = None
        cfg.load_settings(str(cfg.find_project_root() / "taskpps.yaml"))

        service = PipelineService()
        with patch.object(service, "_load_resolved_pipeline") as mock_load:
            mock_pipeline = MagicMock()
            mock_task1 = ResolvedTask(name="step1", task_type="command", command="echo hello")
            from taskpps.domain.pipeline import ResolvedSubPipeline
            from taskpps.schemas.pipeline import PipelineConfig

            mock_sub = ResolvedSubPipeline(name="sub", tasks=[mock_task1], config=PipelineConfig())
            mock_pipeline.subpipelines = [mock_sub]
            mock_pipeline.top_config = PipelineConfig()
            mock_pipeline.get_task_by_name.side_effect = lambda n: {"step1": mock_task1}.get(n)
            mock_load.return_value = mock_pipeline

            with patch("taskpps.services.pipeline_service.RetryRunner") as mock_runner_cls:
                mock_runner = AsyncMock()
                mock_runner_cls.return_value = mock_runner
                await service.retry_run(
                    run_id=run.id,
                    tasks=["sub.step1"],
                    retry_execution_strategy="sequential",
                )

                # 让后台任务有机会执行
                await asyncio.sleep(0)

        mock_runner_cls.assert_called_once()
        call_kwargs = mock_runner_cls.call_args[1]
        assert call_kwargs["execution_strategy"] == "sequential"
        mock_runner.retry_tasks.assert_awaited_once()

    @pytest.mark.zentao("TC-S0400", domain="server/services", priority="P1")
    async def test_retry_run_raises_on_running(self, db_engine, clean_db):
        from taskpps.services.pipeline_service import PipelineService

        async with get_session_factory()() as session:
            run_repo = RunRepository(session)
            await run_repo.create_run(pipeline_name="test", pipeline_file="test.yaml")

            run2 = await run_repo.create_run(pipeline_name="test2", pipeline_file="test2.yaml")
            run2.status = RunStatus.RUNNING
            session.add(run2)
            await session.commit()

        service = PipelineService()
        with pytest.raises(ValueError, match="仍在进行"):
            await service.retry_run(run_id=run2.id, tasks=["sub.t1"])

    @pytest.mark.zentao("TC-S0401", domain="server/services", priority="P1")
    async def test_select_retry_report(self, db_engine, clean_db):
        from taskpps.services.pipeline_service import PipelineService

        async with get_session_factory()() as session:
            run_repo = RunRepository(session)
            task_repo = TaskRunRepository(session)
            retry_repo = RetryRecordRepository(session)

            run = await run_repo.create_run(pipeline_name="test")
            tr = await task_repo.create_task_run(
                run_id=run.id,
                task_name="sub.t1",
                task_type="command",
            )
            tr.status = TaskStatus.FAILED
            session.add(tr)
            await session.commit()

            record = await retry_repo.create_retry_record(
                run_id=run.id,
                task_run_id=tr.id,
                task_name="sub.t1",
                subpipeline_name="sub",
                retry_version=1,
                command="echo ok",
                original_command="echo ok",
                log_path="/tmp/r.log",
            )
            await retry_repo.update_retry_status(record.id, TaskStatus.SUCCESS, exit_code=0)

        service = PipelineService()
        result = await service.select_retry_report(
            run_id=run.id,
            task_name="sub.t1",
            selected_retry_id=record.id,
        )
        assert result["selected_retry_id"] == record.id

        async with get_session_factory()() as session:
            task_repo = TaskRunRepository(session)
            updated = await task_repo.get_task_run(tr.id)
            assert updated.selected_retry_id == record.id
            assert updated.status == TaskStatus.SUCCESS
            # Issue #99: 设为最终版本应同步更新 task run 的退出码、错误、日志路径和时间
            assert updated.exit_code == 0
            assert updated.error == record.error
            assert updated.log_path == record.log_path
            assert updated.started_at == record.started_at
            assert updated.finished_at == record.finished_at

    @pytest.mark.zentao("TC-S0402", domain="server/services", priority="P2")
    async def test_select_original_version_as_final(self, db_engine, clean_db):
        """Issue #92: 选择 v0（原始版本）作为最终版本应将 selected_retry_id 设为 null"""
        from taskpps.services.pipeline_service import PipelineService

        async with get_session_factory()() as session:
            run_repo = RunRepository(session)
            task_repo = TaskRunRepository(session)
            retry_repo = RetryRecordRepository(session)

            run = await run_repo.create_run(pipeline_name="test")
            tr = await task_repo.create_task_run(
                run_id=run.id,
                task_name="sub.t1",
                task_type="command",
            )
            tr.status = TaskStatus.FAILED
            session.add(tr)
            await session.commit()

            record = await retry_repo.create_retry_record(
                run_id=run.id,
                task_run_id=tr.id,
                task_name="sub.t1",
                subpipeline_name="sub",
                retry_version=1,
                command="echo ok",
                original_command="echo ok",
                log_path="/tmp/r.log",
            )
            await retry_repo.update_retry_status(record.id, TaskStatus.SUCCESS, exit_code=0)

        service = PipelineService()
        # 先选中 v1
        await service.select_retry_report(
            run_id=run.id,
            task_name="sub.t1",
            selected_retry_id=record.id,
        )

        # 再切回 v0（原始版本），selected_retry_id=None
        result = await service.select_retry_report(
            run_id=run.id,
            task_name="sub.t1",
            selected_retry_id=None,
        )
        assert result["selected_retry_id"] is None

        async with get_session_factory()() as session:
            task_repo = TaskRunRepository(session)
            updated = await task_repo.get_task_run(tr.id)
            assert updated.selected_retry_id is None

    @pytest.mark.zentao("TC-S0403", domain="server/services", priority="P1")
    async def test_retry_versions(self, db_engine, clean_db):
        from taskpps.services.pipeline_service import PipelineService

        async with get_session_factory()() as session:
            run_repo = RunRepository(session)
            task_repo = TaskRunRepository(session)
            retry_repo = RetryRecordRepository(session)

            run = await run_repo.create_run(pipeline_name="test")
            tr = await task_repo.create_task_run(
                run_id=run.id,
                task_name="sub.t1",
                task_type="command",
            )
            for v in range(1, 4):
                r = await retry_repo.create_retry_record(
                    run_id=run.id,
                    task_run_id=tr.id,
                    task_name="sub.t1",
                    subpipeline_name="sub",
                    retry_version=v,
                    command=f"echo {v}",
                    original_command=f"echo {v}",
                    log_path=f"/tmp/{v}.log",
                )
                await retry_repo.update_retry_status(r.id, TaskStatus.SUCCESS, exit_code=0)

        service = PipelineService()
        result = await service.get_retry_versions(run.id)
        assert "sub.t1" in result["task_retries"]
        assert len(result["task_retries"]["sub.t1"]) == 4  # v0 + 3 retry versions

    @pytest.mark.zentao("TC-S0404", domain="server/services", priority="P1")
    async def test_cancel_retry_run(self, db_engine, clean_db):
        """Issue #102: cancel_retry_run 应找到并取消活跃的 RetryRunner。"""
        from taskpps.engine.retry_runner import _active_retries
        from taskpps.services.pipeline_service import PipelineService

        async with get_session_factory()() as session:
            run_repo = RunRepository(session)
            run = await run_repo.create_run(pipeline_name="test", pipeline_file="test.yaml")
            task_repo = TaskRunRepository(session)
            await task_repo.create_task_run(run_id=run.id, task_name="sub.t1", task_type="command")

        service = PipelineService()
        mock_runner = AsyncMock()
        _active_retries[run.id] = mock_runner
        try:
            result = await service.cancel_retry_run(run.id)
            assert result is True
            mock_runner.cancel.assert_awaited_once()
        finally:
            _active_retries.pop(run.id, None)

    @pytest.mark.zentao("TC-S0405", domain="server/services", priority="P1")
    async def test_cancel_retry_run_not_found(self, db_engine, clean_db):
        """Issue #102: 运行不存在或无活跃重试时 cancel_retry_run 返回 False。"""
        from taskpps.services.pipeline_service import PipelineService

        service = PipelineService()
        assert await service.cancel_retry_run("nonexistent") is False

    @pytest.mark.zentao("TC-S0406", domain="server/services", priority="P1")
    async def test_retry_command_flow(self, db_engine, clean_db):
        from taskpps.services.pipeline_service import PipelineService

        async with get_session_factory()() as session:
            run_repo = RunRepository(session)
            task_repo = TaskRunRepository(session)
            retry_repo = RetryRecordRepository(session)

            run = await run_repo.create_run(pipeline_name="test", params=json.dumps({"var": "val"}))
            tr = await task_repo.create_task_run(run_id=run.id, task_name="sub.t1")
            record = await retry_repo.create_retry_record(
                run_id=run.id,
                task_run_id=tr.id,
                task_name="sub.t1",
                subpipeline_name="sub",
                retry_version=1,
                command="${env.var}",
                original_command="${env.var}",
                log_path="/tmp/x.log",
            )

        service = PipelineService()
        cmd_result = await service.get_retry_command(record.id)
        assert cmd_result is not None
        assert cmd_result["retry_id"] == record.id

        update_result = await service.update_retry_command(record.id, "new command")
        assert update_result["command"] == "new command"

    @pytest.mark.zentao("TC-S0407", domain="server/services", priority="P2")
    async def test_dependency_tree(self, db_engine, clean_db):
        from taskpps.services.pipeline_service import PipelineService

        async with get_session_factory()() as session:
            run_repo = RunRepository(session)
            run = await run_repo.create_run(
                pipeline_name="deploy",
                pipeline_file="deploy.yaml",
            )

        service = PipelineService()
        with pytest.raises(ValueError, match="not found"):
            await service.get_dependency_tree("nonexistent", "sub.step1")

    @pytest.mark.zentao("TC-S0408", domain="server/services", priority="P2")
    async def test_resolve_template(self):
        from taskpps.services.pipeline_service import PipelineService

        result = PipelineService._resolve_template(
            "${env.cmd} --testcase a",
            {"cmd": "/usr/bin/python run.py"},
        )
        assert result == "/usr/bin/python run.py --testcase a"

        result = PipelineService._resolve_template(
            "${env.exec_command} --testcase a",
            {"exec_command": "/usr/bin/python run.py"},
        )
        assert result == "/usr/bin/python run.py --testcase a"

    @pytest.mark.zentao("TC-S0409", domain="server/services", priority="P1")
    async def test_build_retry_log_path(self):
        path = build_retry_log_path("p1", "v1", "run1", "sub.t1", 1)
        assert "retries" in str(path)
        assert "sub.t1.retry-1.log" in str(path)


@pytest.mark.asyncio
class TestRetryAPI:
    @pytest.mark.zentao("TC-S0410", domain="server/services", priority="P1")
    async def test_retry_versions_api(self, client, db_engine, clean_db):
        async with get_session_factory()() as session:
            run_repo = RunRepository(session)
            run = await run_repo.create_run(pipeline_name="test")

        resp = await client.get(f"/api/runs/{run.id}/retry/versions")
        assert resp.status_code == 200
        data = resp.json()
        assert "task_retries" in data

    @pytest.mark.zentao("TC-S0411", domain="server/services", priority="P1")
    async def test_retry_command_api_not_found(self, client, db_engine, clean_db):
        async with get_session_factory()() as session:
            run_repo = RunRepository(session)
            run = await run_repo.create_run(pipeline_name="test")

        resp = await client.get(f"/api/runs/{run.id}/retry/nonexistent/command")
        assert resp.status_code == 404

    @pytest.mark.zentao("TC-S0412", domain="server/services", priority="P1")
    async def test_retry_dependency_tree_api(self, client, db_engine, clean_db):
        async with get_session_factory()() as session:
            run_repo = RunRepository(session)
            run = await run_repo.create_run(
                pipeline_name="deploy",
                pipeline_file="deploy.yaml",
            )

        resp = await client.get(f"/api/runs/{run.id}/retry/dependency-tree?task=sub.step1")
        assert resp.status_code in (200, 400)


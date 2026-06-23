import asyncio
import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from taskpps.domain.context import ExecutionContext
from taskpps.domain.pipeline import ResolvedPipeline, ResolvedSubPipeline, ResolvedTask
from taskpps.engine.runner import PipelineRunner, get_active_runner
from taskpps.executors.base import ExecutorResult
from taskpps.executors.local import LocalExecutor
from taskpps.executors.ssh import SSHExecutor
from taskpps.schemas.pipeline import OptionsYAML, PipelineConfig, PipelineYAML, SubPipeline, TaskYAML


def make_pipeline(name="test", tasks=None, options=None):
    if tasks is None:
        tasks = [ResolvedTask(name="t1", task_type="command", command="echo hi")]
    return ResolvedPipeline(name=name, tasks=tasks, options=options or OptionsYAML())


@pytest.fixture
def mock_repos():
    run_repo = MagicMock()
    run_repo.update_run_status = AsyncMock()
    run_repo.get_run = AsyncMock()
    run_repo.create_run = AsyncMock()
    task_repo = MagicMock()
    task_repo.update_task_status = AsyncMock()
    task_repo.create_task_run = AsyncMock()
    task_repo.list_task_runs = AsyncMock()
    task_repo.cancel_pending_tasks = AsyncMock()
    task_repo.get_running_tasks = AsyncMock()
    task_repo.get_task_run = AsyncMock()
    task_repo.update_stuck_tasks = AsyncMock()
    return run_repo, task_repo


@pytest.fixture
def mock_session_factory(mock_repos):
    run_repo, task_repo = mock_repos
    mock_session = MagicMock()

    with (
        patch("taskpps.engine.runner.RunRepository") as mock_rr,
        patch("taskpps.engine.runner.TaskRunRepository") as mock_tr,
    ):
        mock_rr.side_effect = lambda s: run_repo
        mock_tr.side_effect = lambda s: task_repo

        mock_sf = MagicMock()
        mock_sf.return_value = mock_session

        with patch("taskpps.engine.runner.get_session_factory", return_value=mock_sf):
            yield run_repo, task_repo


class TestPipelineRunnerInit:
    def test_init(self):
        pipeline = ResolvedPipeline(
            name="test",
            tasks=[ResolvedTask(name="t1", task_type="command", command="echo hi")],
            options=OptionsYAML(),
        )
        ctx = ExecutionContext(pipeline=pipeline, run_id="test123")
        runner = PipelineRunner(run_id="test123", pipeline=pipeline, context=ctx)
        assert runner.run_id == "test123"
        assert runner._cancelled is False
        assert runner._task_run_ids == {}

    def test_get_active_runner_empty(self):
        result = get_active_runner("nonexistent")
        assert result is None

    def test_get_active_runner_returns_none(self):
        assert get_active_runner("nonexistent") is None

    @pytest.mark.asyncio
    async def test_unexpected_error_init(self, mock_session_factory):
        tasks = [ResolvedTask(name="t1", task_type="command", command="echo hi")]
        pipeline = make_pipeline(tasks=tasks)
        ctx = ExecutionContext(pipeline=pipeline, run_id="test8")
        runner = PipelineRunner(run_id="test8", pipeline=pipeline, context=ctx)
        assert runner._unexpected_error is False


class TestPipelineRunnerRun:
    @pytest.mark.asyncio
    async def test_unknown_dependency(self, mock_session_factory):
        run_repo, _task_repo = mock_session_factory
        tasks = [
            ResolvedTask(name="a", task_type="command", command="echo", depends_on=["unknown"]),
        ]
        pipeline = make_pipeline(tasks=tasks)
        ctx = ExecutionContext(pipeline=pipeline, run_id="test1")
        runner = PipelineRunner(run_id="test1", pipeline=pipeline, context=ctx)

        await runner.run()
        calls = [c[0][1] for c in run_repo.update_run_status.call_args_list]
        assert "failed" in calls

    @pytest.mark.asyncio
    async def test_success(self, mock_session_factory):
        run_repo, _task_repo = mock_session_factory
        tasks = [ResolvedTask(name="t1", task_type="command", command="echo hi")]
        pipeline = make_pipeline(tasks=tasks)
        ctx = ExecutionContext(pipeline=pipeline, run_id="test2")
        runner = PipelineRunner(run_id="test2", pipeline=pipeline, context=ctx)
        runner._task_run_ids = {"t1": "tr1"}

        mock_executor = AsyncMock()
        mock_executor.execute.return_value = ExecutorResult(exit_code=0, stdout="ok")

        with (
            patch("taskpps.engine.runner.create_executor", return_value=mock_executor),
            patch("taskpps.engine.runner.get_logs_dir"),
            patch("taskpps.engine.runner.get_event_bus"),
        ):
            await runner.run()

        assert run_repo.update_run_status.call_count >= 1
        assert run_repo.update_run_status.call_args[0][1] == "success"

    @pytest.mark.asyncio
    async def test_console_log_contains_header_after_run(self, mock_session_factory, tmp_path):
        # Issue #15: after a single task runs, console.log must already
        # contain the header (and the [PIPELINE] subpipelines block).
        # Without an explicit flush the first few lines can be sitting in
        # the OS write buffer and not yet visible to a reader tailing
        # the log while the server is still alive.
        _run_repo, _task_repo = mock_session_factory
        log_path = tmp_path / "console.log"

        tasks = [ResolvedTask(name="t1", task_type="command", command="echo hi")]
        pipeline = make_pipeline(tasks=tasks)
        ctx = ExecutionContext(pipeline=pipeline, run_id="flush_test")
        runner = PipelineRunner(run_id="flush_test", pipeline=pipeline, context=ctx)
        runner._task_run_ids = {"t1": "tr1"}
        runner._pipeline_id = "pid"
        runner._pipeline_version = "v1"

        mock_executor = AsyncMock()
        mock_executor.execute.return_value = ExecutorResult(exit_code=0, stdout="ok")

        with (
            patch("taskpps.engine.runner.create_executor", return_value=mock_executor),
            patch("taskpps.engine.runner.get_event_bus"),
            patch("taskpps.engine.runner.build_pipeline_log_path", return_value=log_path),
        ):
            await runner.run()

        # The runner wrote the log at the path provided by the patched
        # build_pipeline_log_path. The header block must already be on
        # disk before run() returns.
        assert log_path.exists()
        content = log_path.read_text()
        assert "Pipeline Execution Log" in content
        assert "[PIPELINE:SETUP]" in content
        assert "[SYSTEM] Run ID: flush_test" in content
        assert "[PIPELINE] SubPipelines:" in content
        assert "SUCCESS" in content
        # The header must come before the trailing summary, not be
        # somehow overwritten by it.
        assert content.index("Pipeline Execution Log") < content.index("SUCCESS")

    @pytest.mark.asyncio
    async def test_subpipeline_levels_in_yaml_order(self):
        # Subpipelines at the same level (no inter-dependency) must be
        # ordered in YAML declaration order, so that the level list in
        # console.log is stable and matches what the user wrote. See issue #13.
        spec = PipelineYAML(
            name="p",
            pipelines=[
                SubPipeline(name="sync", tasks=[TaskYAML(name="t", command="echo s")]),
                SubPipeline(name="tests", tasks=[TaskYAML(name="t", command="echo t")]),
            ],
        )
        from taskpps.domain.pipeline import ResolvedPipeline

        pipeline = ResolvedPipeline.from_yaml(spec, pipeline_file="x.yaml")
        ctx = ExecutionContext(pipeline=pipeline, run_id="ord")
        runner = PipelineRunner(run_id="ord", pipeline=pipeline, context=ctx)
        levels = runner._build_subpipeline_levels()
        # Both in level 1 (no depends_on) but in YAML order.
        assert levels == [["sync", "tests"]]

    @pytest.mark.asyncio
    async def test_subpipeline_levels_with_dependency(self):
        # An explicit depends_on must still put the dependent in a later
        # level regardless of YAML order. See issue #13.
        spec = PipelineYAML(
            name="p",
            pipelines=[
                SubPipeline(name="tests", depends_on=["sync"], tasks=[TaskYAML(name="t", command="echo t")]),
                SubPipeline(name="sync", tasks=[TaskYAML(name="t", command="echo s")]),
            ],
        )
        from taskpps.domain.pipeline import ResolvedPipeline

        pipeline = ResolvedPipeline.from_yaml(spec, pipeline_file="x.yaml")
        ctx = ExecutionContext(pipeline=pipeline, run_id="dep")
        runner = PipelineRunner(run_id="dep", pipeline=pipeline, context=ctx)
        levels = runner._build_subpipeline_levels()
        assert levels == [["sync"], ["tests"]]

    @pytest.mark.asyncio
    async def test_unrelated_subpipelines_run_sequentially(self, mock_session_factory):
        # Two subpipelines with no inter-dependency should still run one
        # after the other (not concurrently), so that console.log writes
        # for sub A finish before sub B starts. See issue #13.
        run_repo, _task_repo = mock_session_factory

        sub_a = ResolvedSubPipeline(
            name="A",
            config=PipelineConfig(),
            tasks=[ResolvedTask(name="a1", task_type="command", command="echo a")],
        )
        sub_b = ResolvedSubPipeline(
            name="B",
            config=PipelineConfig(),
            tasks=[ResolvedTask(name="b1", task_type="command", command="echo b")],
        )
        pipeline = ResolvedPipeline(name="p", subpipelines=[sub_a, sub_b], top_config=PipelineConfig())
        ctx = ExecutionContext(pipeline=pipeline, run_id="seq")
        runner = PipelineRunner(run_id="seq", pipeline=pipeline, context=ctx)
        runner._task_run_ids = {"A.a1": "tr-a", "B.b1": "tr-b"}

        execution_order: list[str] = []

        async def fake_execute_subpipeline(name):
            execution_order.append(f"start:{name}")
            # Yield to event loop; if the runner used asyncio.gather, the
            # other subpipeline would also start here. With the sequential
            # for-loop, this yields but the runner waits for us to finish.
            await asyncio.sleep(0)
            execution_order.append(f"end:{name}")
            return {"success": True}

        with (
            patch.object(runner, "_execute_subpipeline", side_effect=fake_execute_subpipeline),
            patch("taskpps.engine.runner.get_logs_dir"),
            patch("taskpps.engine.runner.get_event_bus"),
        ):
            await runner.run()

        # A must complete before B starts.
        assert execution_order == ["start:A", "end:A", "start:B", "end:B"]
        assert run_repo.update_run_status.call_args[0][1] == "success"

    @pytest.mark.asyncio
    async def test_parallel_strategy_executes_tasks_concurrently(self, mock_session_factory):
        # Issue #83: execution_strategy=parallel 时,同一 subpipeline 内无依赖的
        # task 必须并发执行,而不是被 implicit_sequential 拆成多个 level 顺序执行。
        run_repo, _task_repo = mock_session_factory

        sub = ResolvedSubPipeline(
            name="sub",
            config=PipelineConfig(execution_strategy="parallel"),
            tasks=[
                ResolvedTask(name="task-a", task_type="command", command="echo a"),
                ResolvedTask(name="task-b", task_type="command", command="echo b"),
                ResolvedTask(name="task-c", task_type="command", command="echo c"),
            ],
        )
        pipeline = ResolvedPipeline(name="p", subpipelines=[sub], top_config=PipelineConfig())
        ctx = ExecutionContext(pipeline=pipeline, run_id="par")
        runner = PipelineRunner(run_id="par", pipeline=pipeline, context=ctx)
        runner._task_run_ids = {"sub.task-a": "ta", "sub.task-b": "tb", "sub.task-c": "tc"}

        execution_order: list[str] = []
        received_max_parallel: list[int | None] = []

        async def fake_execute_task(task, sub_name="", max_parallel=None):
            received_max_parallel.append(max_parallel)
            qualified = f"{sub_name}.{task.name}" if sub_name else task.name
            execution_order.append(f"start:{qualified}")
            # 让出事件循环,使并发执行的 task 在此交错;顺序执行时不会交错
            await asyncio.sleep(0.01)
            execution_order.append(f"end:{qualified}")
            return ExecutorResult(exit_code=0)

        with (
            patch.object(runner, "_execute_task", side_effect=fake_execute_task),
            patch("taskpps.engine.runner.get_logs_dir"),
            patch("taskpps.engine.runner.get_event_bus"),
        ):
            await runner.run()

        # Issue #115: parallel 策略下,runner 必须将默认的 max_concurrent_tasks(5)
        # 作为 max_parallel 传递给 _execute_task,避免 agent 默认串行化。
        assert received_max_parallel == [5, 5, 5], f"Unexpected max_parallel values: {received_max_parallel}"
        starts = [i for i, e in enumerate(execution_order) if e.startswith("start:")]
        ends = [i for i, e in enumerate(execution_order) if e.startswith("end:")]
        assert len(starts) == 3
        assert len(ends) == 3
        # 并发执行的标志:所有 start 都在第一个 end 之前
        last_start = max(starts)
        first_end = min(ends)
        assert last_start < first_end, f"Tasks not concurrent: {execution_order}"
        assert run_repo.update_run_status.call_args[0][1] == "success"

    @pytest.mark.asyncio
    async def test_inherited_cwd_reaches_executor(self, mock_session_factory):
        # Issue #9: top-level / subpipeline / task cwd should all propagate
        # to the executor via the resolved task's cwd field.
        run_repo, _task_repo = mock_session_factory

        # Use ResolvedSubPipeline.from_yaml so that subpipeline.config.cwd
        # is merged into tasks without their own cwd (mirrors production
        # behavior).
        from taskpps.schemas.pipeline import PipelineYAML, SubPipeline, TaskYAML

        spec = PipelineYAML(
            name="p",
            config={"cwd": "/top"},
            pipelines=[
                SubPipeline(
                    name="sub",
                    config={"cwd": "/sub"},
                    tasks=[
                        TaskYAML(name="t1", command="echo hi"),
                        TaskYAML(name="t2", command="echo bye", cwd="/task"),
                    ],
                )
            ],
        )
        from taskpps.domain.pipeline import ResolvedPipeline

        pipeline = ResolvedPipeline.from_yaml(spec, pipeline_file="x.yaml")
        # Resolved task cwd honors: subpipeline.config.cwd / task.cwd
        assert pipeline.subpipelines[0].tasks[0].cwd == "/sub"
        assert pipeline.subpipelines[0].tasks[1].cwd == "/task"

        ctx = ExecutionContext(pipeline=pipeline, run_id="test_cwd")
        runner = PipelineRunner(run_id="test_cwd", pipeline=pipeline, context=ctx)
        runner._task_run_ids = {"sub.t1": "tr1", "sub.t2": "tr2"}

        mock_executor = AsyncMock()
        mock_executor.execute.return_value = ExecutorResult(exit_code=0, stdout="ok")

        with (
            patch("taskpps.engine.runner.create_executor", return_value=mock_executor),
            patch("taskpps.engine.runner.get_logs_dir"),
            patch("taskpps.engine.runner.get_event_bus"),
        ):
            await runner.run()

        # Both tasks executed and the final run status is success.
        assert mock_executor.execute.call_count == 2
        assert run_repo.update_run_status.call_args[0][1] == "success"

    @pytest.mark.asyncio
    async def test_with_executor_exception(self, mock_session_factory):
        run_repo, _task_repo = mock_session_factory
        tasks = [ResolvedTask(name="t1", task_type="command", command="echo hi")]
        pipeline = make_pipeline(tasks=tasks)
        ctx = ExecutionContext(pipeline=pipeline, run_id="test4")
        runner = PipelineRunner(run_id="test4", pipeline=pipeline, context=ctx)
        runner._task_run_ids = {"t1": "tr1"}

        mock_executor = AsyncMock()
        mock_executor.execute.side_effect = Exception("unexpected error")

        with (
            patch("taskpps.engine.runner.create_executor", return_value=mock_executor),
            patch("taskpps.engine.runner.get_logs_dir"),
            patch("taskpps.engine.runner.get_event_bus"),
        ):
            await runner.run()

        assert run_repo.update_run_status.call_count >= 1

    @pytest.mark.asyncio
    async def test_dependency_failure(self, mock_session_factory):
        run_repo, _task_repo = mock_session_factory
        tasks = [
            ResolvedTask(name="t1", task_type="command", command="exit 1"),
            ResolvedTask(name="t2", task_type="command", command="echo should not run", depends_on=["t1"]),
        ]
        pipeline = make_pipeline(tasks=tasks)
        ctx = ExecutionContext(pipeline=pipeline, run_id="test5")
        runner = PipelineRunner(run_id="test5", pipeline=pipeline, context=ctx)
        runner._task_run_ids = {"t1": "tr1", "t2": "tr2"}

        mock_executor = AsyncMock()
        mock_executor.execute.return_value = ExecutorResult(exit_code=1, stderr="failed")

        with (
            patch("taskpps.engine.runner.create_executor", return_value=mock_executor),
            patch("taskpps.engine.runner.get_logs_dir"),
            patch("taskpps.engine.runner.get_event_bus"),
        ):
            await runner.run()

        assert run_repo.update_run_status.call_args[0][1] in ("failed", "partial")

    @pytest.mark.asyncio
    async def test_skip_dependency_failed(self, mock_session_factory):
        _run_repo, task_repo = mock_session_factory
        tasks = [
            ResolvedTask(name="t1", task_type="command", command="exit 1"),
            ResolvedTask(name="t2", task_type="command", command="echo dep", depends_on=["t1"]),
        ]
        pipeline = make_pipeline(tasks=tasks)
        ctx = ExecutionContext(pipeline=pipeline, run_id="test6")
        runner = PipelineRunner(run_id="test6", pipeline=pipeline, context=ctx)
        runner._task_run_ids = {"t1": "tr1", "t2": "tr2"}

        mock_executor = AsyncMock()
        mock_executor.execute.return_value = ExecutorResult(exit_code=1, stderr="failed")

        with (
            patch("taskpps.engine.runner.create_executor", return_value=mock_executor),
            patch("taskpps.engine.runner.get_logs_dir"),
            patch("taskpps.engine.runner.get_event_bus"),
            patch("taskpps.engine.runner.get_settings"),
        ):
            await runner.run()

        assert task_repo.update_task_status.call_count >= 1

    @pytest.mark.asyncio
    async def test_cancelled_during_execution(self, mock_session_factory):
        run_repo, _task_repo = mock_session_factory
        tasks = [
            ResolvedTask(name="t1", task_type="command", command="echo hi"),
            ResolvedTask(name="t2", task_type="command", command="echo there", depends_on=["t1"]),
        ]
        pipeline = make_pipeline(tasks=tasks)
        ctx = ExecutionContext(pipeline=pipeline, run_id="test7")
        runner = PipelineRunner(run_id="test7", pipeline=pipeline, context=ctx)
        runner._cancelled = True

        with patch("taskpps.engine.runner.get_event_bus"):
            await runner.run()

        assert run_repo.update_run_status.call_args[0][1] == "cancelled"

    @pytest.mark.asyncio
    async def test_unexpected_error_sets_failed(self, mock_session_factory):
        run_repo, _task_repo = mock_session_factory
        tasks = [ResolvedTask(name="t1", task_type="command", command="echo hi")]
        pipeline = make_pipeline(tasks=tasks)
        ctx = ExecutionContext(pipeline=pipeline, run_id="test9")
        runner = PipelineRunner(run_id="test9", pipeline=pipeline, context=ctx)
        runner._task_run_ids = {"t1": "tr1"}

        with (
            patch("taskpps.domain.dag.DAG.get_execution_levels", side_effect=RuntimeError("dag crash")),
            patch("taskpps.engine.runner.get_event_bus"),
            patch("taskpps.engine.runner.get_logs_dir"),
            patch("taskpps.engine.runner.get_settings"),
        ):
            await runner.run()

        assert runner._unexpected_error is True
        assert run_repo.update_run_status.call_args[0][1] == "failed"

    @pytest.mark.asyncio
    async def test_cancelled_error_sets_terminal_status(self, mock_session_factory):
        """Issue #66: asyncio.CancelledError (BaseException) 跳过最终状态更新,
        导致 run 永远停在 RUNNING。修复后 finally 块应兜底设置终态。"""
        run_repo, _task_repo = mock_session_factory
        tasks = [ResolvedTask(name="t1", task_type="command", command="echo hi")]
        pipeline = make_pipeline(tasks=tasks)
        ctx = ExecutionContext(pipeline=pipeline, run_id="test_cancel_err")
        runner = PipelineRunner(run_id="test_cancel_err", pipeline=pipeline, context=ctx)
        runner._task_run_ids = {"t1": "tr1"}

        with (
            patch.object(runner, "_build_subpipeline_levels", side_effect=asyncio.CancelledError()),
            patch("taskpps.engine.runner.get_event_bus"),
            patch("taskpps.engine.runner.get_logs_dir"),
            patch("taskpps.engine.runner.get_settings"),
        ):
            await runner.run()

        # 最终状态必须是终态(failed/cancelled),不能停留在 running
        final_status = run_repo.update_run_status.call_args[0][1]
        assert final_status in ("failed", "cancelled"), f"Expected terminal status, got {final_status}"


class TestPipelineRunnerCancel:
    @pytest.mark.asyncio
    async def test_cancel(self, mock_session_factory):
        _run_repo, _task_repo = mock_session_factory
        tasks = [ResolvedTask(name="t1", task_type="command", command="echo hi")]
        pipeline = make_pipeline(tasks=tasks)
        ctx = ExecutionContext(pipeline=pipeline, run_id="test3")
        runner = PipelineRunner(run_id="test3", pipeline=pipeline, context=ctx)

        with patch("taskpps.engine.runner.get_event_bus"):
            await runner.cancel()

        assert runner._cancelled is True

    @pytest.mark.asyncio
    async def test_cancel_updates_run_status_to_cancelled(self, mock_session_factory):
        run_repo, _task_repo = mock_session_factory
        tasks = [ResolvedTask(name="t1", task_type="command", command="echo hi")]
        pipeline = make_pipeline(tasks=tasks)
        ctx = ExecutionContext(pipeline=pipeline, run_id="test_cancel_status")
        runner = PipelineRunner(run_id="test_cancel_status", pipeline=pipeline, context=ctx)

        with patch("taskpps.engine.runner.get_event_bus"):
            await runner.cancel()

        assert runner._cancelled is True
        # The run's status must be persisted as "cancelled" immediately so
        # users don't see it stuck at "running" while a long task drains.
        assert run_repo.update_run_status.call_count >= 1
        cancelled_calls = [
            c for c in run_repo.update_run_status.call_args_list if len(c.args) > 1 and c.args[1] == "cancelled"
        ]
        assert len(cancelled_calls) == 1


class TestPipelineRunnerBoundary:
    @pytest.mark.asyncio
    async def test_empty_command_succeeds(self, mock_session_factory):
        run_repo, _task_repo = mock_session_factory
        tasks = [ResolvedTask(name="t1", task_type="command", command="")]
        pipeline = make_pipeline(tasks=tasks)
        ctx = ExecutionContext(pipeline=pipeline, run_id="test_empty")
        runner = PipelineRunner(run_id="test_empty", pipeline=pipeline, context=ctx)
        runner._task_run_ids = {"t1": "tr1"}

        mock_executor = AsyncMock()
        mock_executor.execute.return_value = ExecutorResult(exit_code=0, stdout="")

        with (
            patch("taskpps.engine.runner.create_executor", return_value=mock_executor),
            patch("taskpps.engine.runner.get_logs_dir"),
            patch("taskpps.engine.runner.get_event_bus"),
        ):
            await runner.run()

        assert run_repo.update_run_status.call_args[0][1] == "success"

    @pytest.mark.asyncio
    async def test_command_with_exit_code_127(self, mock_session_factory):
        run_repo, _task_repo = mock_session_factory
        tasks = [ResolvedTask(name="t1", task_type="command", command="nonexistent_cmd_xyz")]
        pipeline = make_pipeline(tasks=tasks)
        ctx = ExecutionContext(pipeline=pipeline, run_id="test_127")
        runner = PipelineRunner(run_id="test_127", pipeline=pipeline, context=ctx)
        runner._task_run_ids = {"t1": "tr1"}

        mock_executor = AsyncMock()
        mock_executor.execute.return_value = ExecutorResult(exit_code=127, stderr="cmd not found")

        with (
            patch("taskpps.engine.runner.create_executor", return_value=mock_executor),
            patch("taskpps.engine.runner.get_logs_dir"),
            patch("taskpps.engine.runner.get_event_bus"),
        ):
            await runner.run()

        assert run_repo.update_run_status.call_args[0][1] in ("failed", "partial")

    @pytest.mark.asyncio
    async def test_task_with_signal_exit_code_neg1(self, mock_session_factory):
        run_repo, _task_repo = mock_session_factory
        tasks = [ResolvedTask(name="t1", task_type="command", command="kill -9 $$")]
        pipeline = make_pipeline(tasks=tasks)
        ctx = ExecutionContext(pipeline=pipeline, run_id="test_sig")
        runner = PipelineRunner(run_id="test_sig", pipeline=pipeline, context=ctx)
        runner._task_run_ids = {"t1": "tr1"}

        mock_executor = AsyncMock()
        mock_executor.execute.return_value = ExecutorResult(exit_code=-1, stderr="killed")

        with (
            patch("taskpps.engine.runner.create_executor", return_value=mock_executor),
            patch("taskpps.engine.runner.get_logs_dir"),
            patch("taskpps.engine.runner.get_event_bus"),
        ):
            await runner.run()

        assert run_repo.update_run_status.call_args[0][1] in ("failed", "partial")

    @pytest.mark.asyncio
    async def test_task_with_exit_code_neg9(self, mock_session_factory):
        run_repo, _task_repo = mock_session_factory
        tasks = [ResolvedTask(name="t1", task_type="command", command="kill -9 $$")]
        pipeline = make_pipeline(tasks=tasks)
        ctx = ExecutionContext(pipeline=pipeline, run_id="test_sig9")
        runner = PipelineRunner(run_id="test_sig9", pipeline=pipeline, context=ctx)
        runner._task_run_ids = {"t1": "tr1"}

        mock_executor = AsyncMock()
        mock_executor.execute.return_value = ExecutorResult(exit_code=-9, stderr="killed by SIGKILL")

        with (
            patch("taskpps.engine.runner.create_executor", return_value=mock_executor),
            patch("taskpps.engine.runner.get_logs_dir"),
            patch("taskpps.engine.runner.get_event_bus"),
        ):
            await runner.run()

        assert run_repo.update_run_status.call_args[0][1] in ("failed", "partial")

    @pytest.mark.asyncio
    async def test_negative_exit_code_logs_signal_message(self, mock_session_factory):
        tasks = [ResolvedTask(name="t1", task_type="command", command="kill -9 $$")]
        pipeline = make_pipeline(tasks=tasks)
        ctx = ExecutionContext(pipeline=pipeline, run_id="test_neg_log")
        runner = PipelineRunner(run_id="test_neg_log", pipeline=pipeline, context=ctx)
        runner._task_run_ids = {"t1": "tr1"}

        mock_executor = AsyncMock()
        mock_executor.execute.return_value = ExecutorResult(exit_code=-9, stderr="killed by SIGKILL")

        with (
            patch("taskpps.engine.runner.create_executor", return_value=mock_executor),
            patch("taskpps.engine.runner.get_logs_dir"),
            patch("taskpps.engine.runner.get_event_bus"),
            patch.object(runner, "_write_pipeline_log") as mock_log,
        ):
            await runner.run()

        mock_log.assert_any_call(
            "FAILED",
            "Task 'test.t1' failed with exit code: -9 (process was killed by signal or did not start properly)",
        )

    @pytest.mark.asyncio
    async def test_multiple_tasks_sequential_all_succeed(self, mock_session_factory):
        run_repo, _task_repo = mock_session_factory
        tasks = [
            ResolvedTask(name="t1", task_type="command", command="echo 1"),
            ResolvedTask(name="t2", task_type="command", command="echo 2"),
            ResolvedTask(name="t3", task_type="command", command="echo 3"),
        ]
        pipeline = make_pipeline(tasks=tasks)
        ctx = ExecutionContext(pipeline=pipeline, run_id="test_multi")
        runner = PipelineRunner(run_id="test_multi", pipeline=pipeline, context=ctx)
        runner._task_run_ids = {"t1": "tr1", "t2": "tr2", "t3": "tr3"}

        mock_executor = AsyncMock()
        mock_executor.execute.return_value = ExecutorResult(exit_code=0, stdout="ok")

        with (
            patch("taskpps.engine.runner.create_executor", return_value=mock_executor),
            patch("taskpps.engine.runner.get_logs_dir"),
            patch("taskpps.engine.runner.get_event_bus"),
        ):
            await runner.run()

        assert run_repo.update_run_status.call_args[0][1] == "success"
        assert mock_executor.execute.call_count == 3

    @pytest.mark.asyncio
    async def test_on_failure_continue_skips_dependent_tasks(self, mock_session_factory):
        _run_repo, _task_repo = mock_session_factory
        tasks = [
            ResolvedTask(name="t1", task_type="command", command="exit 1"),
            ResolvedTask(name="t2", task_type="command", command="echo ok"),
        ]
        pipeline = make_pipeline(tasks=tasks, options=OptionsYAML(on_failure="continue"))
        ctx = ExecutionContext(pipeline=pipeline, run_id="test_cont2")
        runner = PipelineRunner(run_id="test_cont2", pipeline=pipeline, context=ctx)
        runner._task_run_ids = {"t1": "tr1", "t2": "tr2"}

        call_count = 0

        async def side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return ExecutorResult(exit_code=1, stderr="fail")
            return ExecutorResult(exit_code=0, stdout="ok")

        mock_executor = AsyncMock()
        mock_executor.execute.side_effect = side_effect

        with (
            patch("taskpps.engine.runner.create_executor", return_value=mock_executor),
            patch("taskpps.engine.runner.get_logs_dir"),
            patch("taskpps.engine.runner.get_event_bus"),
            patch("taskpps.engine.runner.get_settings"),
        ):
            await runner.run()

        assert mock_executor.execute.call_count == 1, "sequential 下 t1 失败后: 隐式依赖 t1 的 t2 应被跳过"

    @pytest.mark.asyncio
    async def test_retry_on_failure(self, mock_session_factory):
        _run_repo, _task_repo = mock_session_factory
        tasks = [ResolvedTask(name="t1", task_type="command", command="exit 1", retry=2)]
        pipeline = make_pipeline(tasks=tasks)
        ctx = ExecutionContext(pipeline=pipeline, run_id="test_retry")
        runner = PipelineRunner(run_id="test_retry", pipeline=pipeline, context=ctx)
        runner._task_run_ids = {"t1": "tr1"}

        mock_executor = AsyncMock()
        mock_executor.execute.return_value = ExecutorResult(exit_code=1, stderr="fail")

        with (
            patch("taskpps.engine.runner.create_executor", return_value=mock_executor),
            patch("taskpps.engine.runner.get_logs_dir"),
            patch("taskpps.engine.runner.get_event_bus"),
            patch("taskpps.engine.runner.get_settings"),
        ):
            await runner.run()

        assert mock_executor.execute.call_count == 3

    @pytest.mark.asyncio
    async def test_retry_eventually_succeeds(self, mock_session_factory):
        run_repo, _task_repo = mock_session_factory
        tasks = [ResolvedTask(name="t1", task_type="command", command="echo ok", retry=2)]
        pipeline = make_pipeline(tasks=tasks)
        ctx = ExecutionContext(pipeline=pipeline, run_id="test_retry_ok")
        runner = PipelineRunner(run_id="test_retry_ok", pipeline=pipeline, context=ctx)
        runner._task_run_ids = {"t1": "tr1"}

        call_count = 0

        async def side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                return ExecutorResult(exit_code=1, stderr="fail")
            return ExecutorResult(exit_code=0, stdout="ok")

        mock_executor = AsyncMock()
        mock_executor.execute.side_effect = side_effect

        with (
            patch("taskpps.engine.runner.create_executor", return_value=mock_executor),
            patch("taskpps.engine.runner.get_logs_dir"),
            patch("taskpps.engine.runner.get_event_bus"),
            patch("taskpps.engine.runner.get_settings"),
        ):
            await runner.run()

        assert run_repo.update_run_status.call_args[0][1] == "success"
        assert mock_executor.execute.call_count == 3

    @pytest.mark.asyncio
    async def test_task_timeout_produces_exit_code_neg1(self, mock_session_factory):
        run_repo, _task_repo = mock_session_factory
        tasks = [ResolvedTask(name="t1", task_type="command", command="sleep 999", timeout=1)]
        pipeline = make_pipeline(tasks=tasks)
        ctx = ExecutionContext(pipeline=pipeline, run_id="test_timeout")
        runner = PipelineRunner(run_id="test_timeout", pipeline=pipeline, context=ctx)
        runner._task_run_ids = {"t1": "tr1"}

        mock_executor = AsyncMock()
        mock_executor.execute.return_value = ExecutorResult(exit_code=-1, stdout="timeout")

        with (
            patch("taskpps.engine.runner.create_executor", return_value=mock_executor),
            patch("taskpps.engine.runner.get_logs_dir"),
            patch("taskpps.engine.runner.get_event_bus"),
        ):
            await runner.run()

        assert run_repo.update_run_status.call_args[0][1] in ("failed", "partial")

    @pytest.mark.asyncio
    async def test_execute_task_with_cwd_validation(self, tmp_path, mock_session_factory):
        run_repo, _task_repo = mock_session_factory
        tasks = [ResolvedTask(name="t1", task_type="command", command="echo hi", cwd="/nonexistent/path/xyz")]
        pipeline = make_pipeline(tasks=tasks)
        ctx = ExecutionContext(pipeline=pipeline, run_id="test_cwd_bad")
        runner = PipelineRunner(run_id="test_cwd_bad", pipeline=pipeline, context=ctx)
        runner._task_run_ids = {"t1": "tr1"}

        mock_executor = AsyncMock()
        mock_executor.execute.return_value = ExecutorResult(exit_code=0, stdout="ok")

        with (
            patch("taskpps.engine.runner.create_executor", return_value=mock_executor),
            patch("taskpps.engine.runner.get_logs_dir"),
            patch("taskpps.engine.runner.get_event_bus"),
        ):
            await runner.run()

        assert run_repo.update_run_status.call_args[0][1] == "success"

    @pytest.mark.asyncio
    async def test_cwd_not_overridden_for_non_local_executor(self, tmp_path, mock_session_factory):
        run_repo, _task_repo = mock_session_factory
        tasks = [ResolvedTask(name="t1", task_type="command", command="echo hi", cwd="/nonexistent/path/xyz")]
        pipeline = make_pipeline(tasks=tasks)
        ctx = ExecutionContext(pipeline=pipeline, run_id="test_cwd_ssh")
        runner = PipelineRunner(run_id="test_cwd_ssh", pipeline=pipeline, context=ctx)
        runner._task_run_ids = {"t1": "tr1"}

        mock_executor = AsyncMock()
        mock_executor.execute.return_value = ExecutorResult(exit_code=0, stdout="ok")

        with (
            patch("taskpps.engine.runner.create_executor", return_value=mock_executor),
            patch("taskpps.engine.runner.get_logs_dir"),
            patch("taskpps.engine.runner.get_event_bus"),
        ):
            await runner.run()

        assert run_repo.update_run_status.call_args[0][1] == "success"
        call_kwargs = mock_executor.execute.call_args[1]
        assert call_kwargs.get("cwd") == "/nonexistent/path/xyz"

    @pytest.mark.asyncio
    async def test_cwd_overridden_for_local_executor(self, tmp_path, mock_session_factory):
        run_repo, _task_repo = mock_session_factory
        tasks = [ResolvedTask(name="t1", task_type="command", command="echo hi", cwd="/nonexistent/path/xyz")]
        pipeline = make_pipeline(tasks=tasks)
        ctx = ExecutionContext(pipeline=pipeline, run_id="test_cwd_local")
        runner = PipelineRunner(run_id="test_cwd_local", pipeline=pipeline, context=ctx)
        runner._task_run_ids = {"t1": "tr1"}

        executor = LocalExecutor()
        executor.execute = AsyncMock(return_value=ExecutorResult(exit_code=0, stdout="ok"))

        with (
            patch("taskpps.engine.runner.create_executor", return_value=executor),
            patch("taskpps.engine.runner.get_logs_dir"),
            patch("taskpps.engine.runner.get_event_bus"),
        ):
            await runner.run()

        assert run_repo.update_run_status.call_args[0][1] == "success"
        call_kwargs = executor.execute.call_args[1]
        assert call_kwargs.get("cwd") == os.getcwd()

    @pytest.mark.asyncio
    async def test_cwd_preserved_when_valid_for_local_executor(self, tmp_path, mock_session_factory):
        run_repo, _task_repo = mock_session_factory
        valid_cwd = str(tmp_path)
        tasks = [ResolvedTask(name="t1", task_type="command", command="echo hi", cwd=valid_cwd)]
        pipeline = make_pipeline(tasks=tasks)
        ctx = ExecutionContext(pipeline=pipeline, run_id="test_cwd_valid")
        runner = PipelineRunner(run_id="test_cwd_valid", pipeline=pipeline, context=ctx)
        runner._task_run_ids = {"t1": "tr1"}

        executor = LocalExecutor()
        executor.execute = AsyncMock(return_value=ExecutorResult(exit_code=0, stdout="ok"))

        with (
            patch("taskpps.engine.runner.create_executor", return_value=executor),
            patch("taskpps.engine.runner.get_logs_dir"),
            patch("taskpps.engine.runner.get_event_bus"),
        ):
            await runner.run()

        assert run_repo.update_run_status.call_args[0][1] == "success"
        call_kwargs = executor.execute.call_args[1]
        assert call_kwargs.get("cwd") == valid_cwd

    @pytest.mark.asyncio
    async def test_ssh_executor_with_remote_cwd_not_overridden(self, tmp_path, mock_session_factory):
        run_repo, _task_repo = mock_session_factory
        remote_cwd = "/home/auto/heng"
        tasks = [ResolvedTask(name="t1", task_type="command", command="echo hi", cwd=remote_cwd, host="remote-host")]
        pipeline = make_pipeline(tasks=tasks)
        ctx = ExecutionContext(pipeline=pipeline, run_id="test_ssh_cwd")
        runner = PipelineRunner(run_id="test_ssh_cwd", pipeline=pipeline, context=ctx)
        runner._task_run_ids = {"t1": "tr1"}

        ssh_executor = SSHExecutor(host="remote-host")
        ssh_executor.execute = AsyncMock(return_value=ExecutorResult(exit_code=0, stdout="ok"))

        with (
            patch("taskpps.engine.runner.create_executor", return_value=ssh_executor),
            patch("taskpps.engine.runner.get_logs_dir"),
            patch("taskpps.engine.runner.get_event_bus"),
        ):
            await runner.run()

        assert run_repo.update_run_status.call_args[0][1] == "success"
        call_kwargs = ssh_executor.execute.call_args[1]
        assert call_kwargs.get("cwd") == remote_cwd

    @pytest.mark.asyncio
    async def test_ssh_executor_with_nonexistent_local_path_preserved(self, tmp_path, mock_session_factory):
        run_repo, _task_repo = mock_session_factory
        remote_only_cwd = "/remote/machine/only/path"
        tasks = [
            ResolvedTask(name="t1", task_type="command", command="echo hi", cwd=remote_only_cwd, host="remote-host")
        ]
        pipeline = make_pipeline(tasks=tasks)
        ctx = ExecutionContext(pipeline=pipeline, run_id="test_ssh_remote_only")
        runner = PipelineRunner(run_id="test_ssh_remote_only", pipeline=pipeline, context=ctx)
        runner._task_run_ids = {"t1": "tr1"}

        ssh_executor = SSHExecutor(host="remote-host")
        ssh_executor.execute = AsyncMock(return_value=ExecutorResult(exit_code=0, stdout="ok"))

        with (
            patch("taskpps.engine.runner.create_executor", return_value=ssh_executor),
            patch("taskpps.engine.runner.get_logs_dir"),
            patch("taskpps.engine.runner.get_event_bus"),
        ):
            await runner.run()

        assert run_repo.update_run_status.call_args[0][1] == "success"
        call_kwargs = ssh_executor.execute.call_args[1]
        assert call_kwargs.get("cwd") == remote_only_cwd
        assert call_kwargs.get("cwd") != os.getcwd()

    @pytest.mark.asyncio
    async def test_task_with_commands_list(self, mock_session_factory):
        run_repo, _task_repo = mock_session_factory
        tasks = [ResolvedTask(name="t1", task_type="command", commands=["echo step1", "echo step2"])]
        pipeline = make_pipeline(tasks=tasks)
        ctx = ExecutionContext(pipeline=pipeline, run_id="test_cmds")
        runner = PipelineRunner(run_id="test_cmds", pipeline=pipeline, context=ctx)
        runner._task_run_ids = {"t1": "tr1"}

        call_count = 0

        async def side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            return ExecutorResult(exit_code=0, stdout=f"cmd_{call_count}")

        mock_executor = AsyncMock()
        mock_executor.execute.side_effect = side_effect

        with (
            patch("taskpps.engine.runner.create_executor", return_value=mock_executor),
            patch("taskpps.engine.runner.get_logs_dir"),
            patch("taskpps.engine.runner.get_event_bus"),
        ):
            await runner.run()

        assert run_repo.update_run_status.call_args[0][1] == "success"
        assert mock_executor.execute.call_count >= 2

    @pytest.mark.asyncio
    async def test_empty_pipeline_returns_immediately(self, mock_session_factory):
        run_repo, _task_repo = mock_session_factory
        pipeline = ResolvedPipeline(name="test", subpipelines=[])
        ctx = ExecutionContext(pipeline=pipeline, run_id="test_nosub")
        runner = PipelineRunner(run_id="test_nosub", pipeline=pipeline, context=ctx)

        with patch("taskpps.engine.runner.get_event_bus"):
            await runner.run()

        # 空 pipeline (无 subpipeline) 直接标记为 SUCCESS, 不执行任何任务
        assert run_repo.update_run_status.call_args[0][1] == "success"


class TestPipelineRunnerExitCodeCoverage:
    @pytest.mark.asyncio
    async def test_asyncio_gather_exception_produces_exit_code_neg1(self, mock_session_factory):
        run_repo, _task_repo = mock_session_factory
        tasks = [
            ResolvedTask(name="t1", task_type="command", command="echo hi"),
            ResolvedTask(name="t2", task_type="command", command="echo there"),
        ]
        pipeline = make_pipeline(tasks=tasks)
        ctx = ExecutionContext(pipeline=pipeline, run_id="test_gather")
        runner = PipelineRunner(run_id="test_gather", pipeline=pipeline, context=ctx)
        runner._task_run_ids = {"t1": "tr1", "t2": "tr2"}

        mock_executor = AsyncMock()
        mock_executor.execute.side_effect = RuntimeError("simulated asyncio.gather exception")

        with (
            patch("taskpps.engine.runner.create_executor", return_value=mock_executor),
            patch("taskpps.engine.runner.get_logs_dir"),
            patch("taskpps.engine.runner.get_event_bus"),
            patch("taskpps.engine.runner.get_settings"),
        ):
            await runner.run()

        assert run_repo.update_run_status.call_args[0][1] in ("failed", "partial")

    @pytest.mark.asyncio
    async def test_evaluate_when_expression(self, mock_session_factory):
        from taskpps.engine.runner import _evaluate_when

        assert _evaluate_when(None, {}) is True
        assert _evaluate_when('${env.APP_ENV} == "production"', {"APP_ENV": "production"}) is True
        assert _evaluate_when('${env.APP_ENV} == "production"', {"APP_ENV": "staging"}) is False
        assert _evaluate_when('${env.APP_ENV} != "production"', {"APP_ENV": "staging"}) is True
        assert _evaluate_when("invalid expr", {}) is True

    @pytest.mark.asyncio
    async def test_evaluate_when_without_env_prefix(self, mock_session_factory):
        """Issue #85: when 条件支持 ${VAR} 格式(无 env. 前缀)"""
        from taskpps.engine.runner import _evaluate_when

        # ${VAR} == "value" 格式(无 env. 前缀)
        assert _evaluate_when('${RUN_PERF} == "true"', {"RUN_PERF": "true"}) is True
        assert _evaluate_when('${RUN_PERF} == "true"', {"RUN_PERF": "false"}) is False
        # ${VAR} != "value" 格式
        assert _evaluate_when('${RUN_PERF} != "true"', {"RUN_PERF": "false"}) is True

    @pytest.mark.asyncio
    async def test_evaluate_when_without_quotes(self, mock_session_factory):
        """Issue #85: when 条件支持无引号值(如 ${VAR} == true)"""
        from taskpps.engine.runner import _evaluate_when

        # ${VAR} == true(无引号)
        assert _evaluate_when("${RUN_PERF} == true", {"RUN_PERF": "true"}) is True
        assert _evaluate_when("${RUN_PERF} == true", {"RUN_PERF": "false"}) is False
        # ${VAR} == false(无引号)
        assert _evaluate_when("${RUN_SMOKE} == false", {"RUN_SMOKE": "true"}) is False
        assert _evaluate_when("${RUN_SMOKE} == false", {"RUN_SMOKE": "false"}) is True
        # ${env.VAR} == true(有 env. 前缀 + 无引号)
        assert _evaluate_when("${env.RUN_PERF} == true", {"RUN_PERF": "true"}) is True
        assert _evaluate_when("${env.RUN_PERF} == true", {"RUN_PERF": "false"}) is False

    @pytest.mark.asyncio
    async def test_when_condition_skips_task(self, mock_session_factory):
        _run_repo, _task_repo = mock_session_factory
        tasks = [
            ResolvedTask(name="t1", task_type="command", command="echo hi", when='${env.SKIP} == "yes"'),
        ]
        pipeline = make_pipeline(tasks=tasks)
        ctx = ExecutionContext(pipeline=pipeline, run_id="test_when")
        runner = PipelineRunner(run_id="test_when", pipeline=pipeline, context=ctx)
        runner._task_run_ids = {"t1": "tr1"}

        mock_executor = AsyncMock()

        with (
            patch("taskpps.engine.runner.create_executor", return_value=mock_executor),
            patch("taskpps.engine.runner.get_logs_dir"),
            patch("taskpps.engine.runner.get_event_bus"),
        ):
            await runner.run()

        mock_executor.execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_subpipeline_not_found_produces_failure(self, mock_session_factory):
        _run_repo, _task_repo = mock_session_factory
        sub = MagicMock()
        sub.name = "sub1"
        sub.tasks = []
        sub.config = MagicMock()
        sub.config.execution_strategy = "sequential"
        sub.config.on_failure = "fail"
        sub.depends_on = []

        pipeline = ResolvedPipeline(name="test", subpipelines=[sub])
        ctx = ExecutionContext(pipeline=pipeline, run_id="test_subnf")
        runner = PipelineRunner(run_id="test_subnf", pipeline=pipeline, context=ctx)

        with (
            patch.object(pipeline, "get_subpipeline_by_name", return_value=None),
            patch("taskpps.engine.runner.get_event_bus"),
            patch("taskpps.engine.runner.get_session_factory"),
            patch("taskpps.engine.runner.get_settings"),
        ):
            await runner.run()

    @pytest.mark.asyncio
    async def test_subpipeline_dag_error_produces_failure(self, mock_session_factory):
        _run_repo, _task_repo = mock_session_factory
        sub = MagicMock()
        sub.name = "sub1"
        sub.tasks = [ResolvedTask(name="t1", task_type="command", command="echo hi")]
        sub.config = MagicMock()
        sub.config.execution_strategy = "sequential"
        sub.config.on_failure = "fail"
        sub.depends_on = []

        pipeline = ResolvedPipeline(name="test", subpipelines=[sub])
        ctx = ExecutionContext(pipeline=pipeline, run_id="test_dag")
        runner = PipelineRunner(run_id="test_dag", pipeline=pipeline, context=ctx)

        with (
            patch("taskpps.domain.dag.DAG.get_execution_levels", side_effect=RuntimeError("dag error")),
            patch("taskpps.engine.runner.get_event_bus"),
            patch("taskpps.engine.runner.get_session_factory"),
            patch("taskpps.engine.runner.get_settings"),
        ):
            await runner.run()

    @pytest.mark.asyncio
    async def test_subpipeline_with_depends_on_skip(self, mock_session_factory):
        _run_repo, _task_repo = mock_session_factory
        sub1 = MagicMock()
        sub1.name = "sub1"
        sub1.tasks = [ResolvedTask(name="t1", task_type="command", command="exit 1")]
        sub1.config = MagicMock()
        sub1.config.execution_strategy = "sequential"
        sub1.config.on_failure = "fail"
        sub1.depends_on = []

        sub2 = MagicMock()
        sub2.name = "sub2"
        sub2.tasks = [ResolvedTask(name="t2", task_type="command", command="echo ok")]
        sub2.config = MagicMock()
        sub2.config.execution_strategy = "sequential"
        sub2.config.on_failure = "fail"
        sub2.depends_on = ["sub1"]

        pipeline = ResolvedPipeline(name="test", subpipelines=[sub1, sub2])
        pipeline.top_config = MagicMock()
        ctx = ExecutionContext(pipeline=pipeline, run_id="test_dep_skip")
        runner = PipelineRunner(run_id="test_dep_skip", pipeline=pipeline, context=ctx)
        runner._task_run_ids = {"sub1.t1": "tr1", "sub2.t2": "tr2"}

        mock_executor = AsyncMock()
        mock_executor.execute.return_value = ExecutorResult(exit_code=1, stderr="fail")

        with (
            patch("taskpps.engine.runner.create_executor", return_value=mock_executor),
            patch("taskpps.engine.runner.get_event_bus"),
            patch("taskpps.engine.runner.get_session_factory"),
            patch("taskpps.engine.runner.get_settings"),
            patch("taskpps.engine.runner.get_logs_dir"),
        ):
            await runner.run()

    @pytest.mark.asyncio
    async def test_pipeline_with_multiple_levels(self, mock_session_factory):
        _run_repo, _task_repo = mock_session_factory
        sub1 = ResolvedSubPipeline(
            name="sub1",
            tasks=[ResolvedTask(name="t1", task_type="command", command="echo 1")],
            config=PipelineConfig(),
            depends_on=[],
        )

        sub2 = ResolvedSubPipeline(
            name="sub2",
            tasks=[ResolvedTask(name="t2", task_type="command", command="echo 2")],
            config=PipelineConfig(),
            depends_on=["sub1"],
        )

        pipeline = ResolvedPipeline(name="test", subpipelines=[sub1, sub2])
        pipeline.top_config = MagicMock()
        ctx = ExecutionContext(pipeline=pipeline, run_id="test_multi_level")
        runner = PipelineRunner(run_id="test_multi_level", pipeline=pipeline, context=ctx)
        runner._task_run_ids = {"sub1.t1": "tr1", "sub2.t2": "tr2"}

        mock_executor = AsyncMock()
        mock_executor.execute.return_value = ExecutorResult(exit_code=0, stdout="ok")

        with (
            patch("taskpps.engine.runner.create_executor", return_value=mock_executor),
            patch("taskpps.engine.runner.get_event_bus"),
            patch("taskpps.engine.runner.get_session_factory"),
            patch("taskpps.engine.runner.get_settings"),
            patch("taskpps.engine.runner.get_logs_dir"),
        ):
            await runner.run()

        assert mock_executor.execute.call_count >= 2

    @pytest.mark.asyncio
    async def test_task_with_exit_code_neg1_in_subpipeline(self, mock_session_factory):
        _run_repo, _task_repo = mock_session_factory
        sub = MagicMock()
        sub.name = "sub1"
        sub.tasks = [ResolvedTask(name="t1", task_type="command", command="kill -9 $$")]
        sub.config = MagicMock()
        sub.config.execution_strategy = "sequential"
        sub.config.on_failure = "fail"
        sub.depends_on = []
        sub.get_task_by_name.return_value = ResolvedTask(name="t1", task_type="command", command="kill -9 $$")

        pipeline = ResolvedPipeline(name="test", subpipelines=[sub])
        pipeline.top_config = MagicMock()
        ctx = ExecutionContext(pipeline=pipeline, run_id="test_sub_neg1")
        runner = PipelineRunner(run_id="test_sub_neg1", pipeline=pipeline, context=ctx)
        runner._task_run_ids = {"sub1.t1": "tr1"}

        mock_executor = AsyncMock()
        mock_executor.execute.return_value = ExecutorResult(exit_code=-1, stderr="killed")

        with (
            patch("taskpps.engine.runner.create_executor", return_value=mock_executor),
            patch("taskpps.engine.runner.get_event_bus"),
            patch("taskpps.engine.runner.get_session_factory"),
            patch("taskpps.engine.runner.get_settings"),
            patch("taskpps.engine.runner.get_logs_dir"),
        ):
            await runner.run()

    @pytest.mark.asyncio
    async def test_pipeline_logging_initialized(self, tmp_path, mock_session_factory):
        run_repo, _task_repo = mock_session_factory
        tasks = [ResolvedTask(name="t1", task_type="command", command="echo hi")]
        pipeline = make_pipeline(tasks=tasks)
        ctx = ExecutionContext(pipeline=pipeline, run_id="test_log")
        runner = PipelineRunner(run_id="test_log", pipeline=pipeline, context=ctx)
        runner._task_run_ids = {"t1": "tr1"}
        runner._pipeline_id = "test_pipe"
        runner._pipeline_version = "v1"

        mock_executor = AsyncMock()
        mock_executor.execute.return_value = ExecutorResult(exit_code=0, stdout="ok")

        with (
            patch("taskpps.engine.runner.create_executor", return_value=mock_executor),
            patch("taskpps.engine.runner.get_logs_dir", return_value=tmp_path),
            patch("taskpps.engine.runner.get_workspaces_dir"),
            patch("taskpps.engine.runner.get_event_bus"),
            patch("taskpps.engine.runner.build_pipeline_log_path", return_value=tmp_path / "console.log"),
        ):
            await runner.run()

        assert run_repo.update_run_status.call_args[0][1] == "success"

    @pytest.mark.asyncio
    async def test_pipeline_log_write_resilient(self, tmp_path, mock_session_factory):
        run_repo, _task_repo = mock_session_factory
        tasks = [ResolvedTask(name="t1", task_type="command", command="echo hi")]
        pipeline = make_pipeline(tasks=tasks)
        ctx = ExecutionContext(pipeline=pipeline, run_id="test_logr")
        runner = PipelineRunner(run_id="test_logr", pipeline=pipeline, context=ctx)
        runner._task_run_ids = {"t1": "tr1"}
        runner._pipeline_id = "test_pipe"
        runner._pipeline_version = "v1"
        runner._pipeline_log_path = tmp_path / "console.log"

        mock_executor = AsyncMock()
        mock_executor.execute.return_value = ExecutorResult(exit_code=0, stdout="ok")

        read_log_path = tmp_path / "readonly.log"
        read_log_path.write_text("")
        read_log_path.chmod(0o444)

        with (
            patch("taskpps.engine.runner.create_executor", return_value=mock_executor),
            patch("taskpps.engine.runner.get_logs_dir", return_value=tmp_path),
            patch("taskpps.engine.runner.get_workspaces_dir"),
            patch("taskpps.engine.runner.get_event_bus"),
            patch.object(runner, "_init_pipeline_log"),
        ):
            runner._pipeline_log_path = read_log_path
            await runner.run()

        assert run_repo.update_run_status.call_args[0][1] == "success"

    @pytest.mark.asyncio
    async def test_write_pipeline_log_handles_oserror(self, tmp_path):
        tasks = [ResolvedTask(name="t1", task_type="command", command="echo hi")]
        pipeline = make_pipeline(tasks=tasks)
        ctx = ExecutionContext(pipeline=pipeline, run_id="test_wpl")
        runner = PipelineRunner(run_id="test_wpl", pipeline=pipeline, context=ctx)
        runner._pipeline_log_path = tmp_path / "broken.log"

        with patch("builtins.open", side_effect=OSError("disk full")):
            runner._write_pipeline_log("INFO", "test message")

        assert not tmp_path.joinpath("broken.log").exists()

    @pytest.mark.asyncio
    async def test_top_level_runner_exception_handled(self, mock_session_factory):
        _run_repo, _task_repo = mock_session_factory
        sub = ResolvedSubPipeline(
            name="sub1",
            tasks=[ResolvedTask(name="t1", task_type="command", command="echo hi")],
            config=PipelineConfig(),
            depends_on=[],
        )

        pipeline = ResolvedPipeline(name="test", subpipelines=[sub])
        pipeline.top_config = MagicMock()
        ctx = ExecutionContext(pipeline=pipeline, run_id="test_runner_exc")
        runner = PipelineRunner(run_id="test_runner_exc", pipeline=pipeline, context=ctx)

        with (
            patch.object(runner, "_build_subpipeline_levels", side_effect=RuntimeError("top-level crash")),
            patch("taskpps.engine.runner.get_event_bus"),
            patch("taskpps.engine.runner.get_session_factory"),
            patch("taskpps.engine.runner.get_settings"),
        ):
            await runner.run()

        assert runner._unexpected_error is True

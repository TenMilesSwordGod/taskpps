from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from taskpps.domain.context import ExecutionContext
from taskpps.domain.pipeline import ResolvedPipeline, ResolvedTask
from taskpps.engine.runner import PipelineRunner
from taskpps.executors.base import ExecutorResult
from taskpps.schemas.pipeline import OptionsYAML


def make_pipeline(name="test", tasks=None, options=None):
    if tasks is None:
        tasks = [ResolvedTask(name="t1", task_type="command", command="echo hi")]
    return ResolvedPipeline(name=name, tasks=tasks, options=options or OptionsYAML())


def _setup_config():
    import taskpps.config as cfg

    if cfg._project_root is None:
        root = cfg.find_project_root()
        cfg.set_project_root(root)
    cfg._settings = None
    cfg.load_settings()


class TestPipelineExecution:
    @pytest.mark.asyncio
    async def test_single_successful_task(self, db_engine, clean_db):
        _setup_config()
        task = ResolvedTask(name="build", task_type="command", command="echo hello")
        pipeline = make_pipeline("success", [task])
        ctx = ExecutionContext(pipeline=pipeline, run_id="exec-1")

        runner = PipelineRunner(run_id="exec-1", pipeline=pipeline, context=ctx)

        mock_executor = AsyncMock()
        mock_executor.execute.return_value = ExecutorResult(exit_code=0, stdout="hello")

        with (
            patch("taskpps.engine.runner.create_executor", return_value=mock_executor),
            patch("taskpps.engine.runner.get_logs_dir"),
            patch("taskpps.engine.runner.get_event_bus"),
        ):
            await runner.run()

        assert mock_executor.execute.call_count == 1

    @pytest.mark.asyncio
    async def test_task_failure_on_fail_mode(self, db_engine, clean_db):
        _setup_config()
        tasks = [
            ResolvedTask(name="flaky", task_type="command", command="exit 1"),
            ResolvedTask(
                name="next",
                task_type="command",
                command="echo skipped",
                depends_on=["flaky"],
            ),
        ]
        pipeline = make_pipeline("fail", tasks, OptionsYAML(on_failure="fail"))
        ctx = ExecutionContext(pipeline=pipeline, run_id="exec-2")

        runner = PipelineRunner(run_id="exec-2", pipeline=pipeline, context=ctx)

        call_count = 0

        async def mock_execute(command, env, log_path, timeout=None, cwd=None):
            nonlocal call_count
            call_count += 1
            return ExecutorResult(exit_code=1, stderr="error")

        mock_executor = AsyncMock()
        mock_executor.execute.side_effect = mock_execute

        with (
            patch("taskpps.engine.runner.create_executor", return_value=mock_executor),
            patch("taskpps.engine.runner.get_logs_dir"),
            patch("taskpps.engine.runner.get_event_bus"),
        ):
            await runner.run()

        assert call_count == 1, "flaky 失败后依赖它的 next 应被跳过"

    @pytest.mark.asyncio
    async def test_on_failure_continue(self, db_engine, clean_db):
        _setup_config()
        tasks = [
            ResolvedTask(name="flaky", task_type="command", command="exit 1"),
            ResolvedTask(
                name="reliable",
                task_type="command",
                command="echo reliable",
                depends_on=["flaky"],
            ),
        ]
        pipeline = make_pipeline("continue", tasks, OptionsYAML(on_failure="continue"))
        ctx = ExecutionContext(pipeline=pipeline, run_id="exec-3")

        runner = PipelineRunner(run_id="exec-3", pipeline=pipeline, context=ctx)

        call_count = 0

        async def mock_execute(command, env, log_path, timeout=None, cwd=None):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return ExecutorResult(exit_code=1, stderr="fail")
            return ExecutorResult(exit_code=0, stdout="ok")

        mock_executor = AsyncMock()
        mock_executor.execute.side_effect = mock_execute

        with (
            patch("taskpps.engine.runner.create_executor", return_value=mock_executor),
            patch("taskpps.engine.runner.get_logs_dir"),
            patch("taskpps.engine.runner.get_event_bus"),
        ):
            await runner.run()

        assert call_count == 1, "flaky 失败后依赖它的 reliable 应被跳过"

    @pytest.mark.asyncio
    async def test_task_dag_execution_order(self, db_engine, clean_db):
        _setup_config()
        tasks = [
            ResolvedTask(name="a", task_type="command", command="echo a"),
            ResolvedTask(name="b", task_type="command", command="echo b", depends_on=["a"]),
            ResolvedTask(name="c", task_type="command", command="echo c", depends_on=["a"]),
            ResolvedTask(name="d", task_type="command", command="echo d", depends_on=["b", "c"]),
        ]
        pipeline = make_pipeline("dag", tasks, OptionsYAML())
        ctx = ExecutionContext(pipeline=pipeline, run_id="exec-dag")

        runner = PipelineRunner(run_id="exec-dag", pipeline=pipeline, context=ctx)

        executed = []

        async def mock_execute(command, env, log_path, timeout=None, cwd=None):
            task_name = env.get("TASKPPS_TASK_ID", "unknown")
            executed.append(task_name)
            return ExecutorResult(exit_code=0, stdout="ok")

        mock_executor = AsyncMock()
        mock_executor.execute.side_effect = mock_execute

        with (
            patch("taskpps.engine.runner.create_executor", return_value=mock_executor),
            patch("taskpps.engine.runner.get_logs_dir"),
            patch("taskpps.engine.runner.get_event_bus"),
        ):
            await runner.run()

        assert "dag.a" in executed
        for dep in ["dag.b", "dag.c"]:
            assert executed.index("dag.a") < executed.index(dep)
        assert executed.index("dag.d") > max(executed.index("dag.b"), executed.index("dag.c"))

    @pytest.mark.asyncio
    async def test_task_cancellation(self, db_engine, clean_db):
        _setup_config()
        task = ResolvedTask(name="build", task_type="command", command="sleep 999")
        pipeline = make_pipeline("cancel", [task])
        ctx = ExecutionContext(pipeline=pipeline, run_id="cancel-1")

        runner = PipelineRunner(run_id="cancel-1", pipeline=pipeline, context=ctx)

        async def slow_execute(command, env, log_path, timeout=None, cwd=None):
            await asyncio.sleep(0.1)
            return ExecutorResult(exit_code=0, stdout="done")

        mock_executor = AsyncMock()
        mock_executor.execute.side_effect = slow_execute
        mock_executor.cancel = AsyncMock()

        with (
            patch("taskpps.engine.runner.create_executor", return_value=mock_executor),
            patch("taskpps.engine.runner.get_logs_dir"),
            patch("taskpps.engine.runner.get_event_bus"),
        ):
            run_task = asyncio.create_task(runner.run())
            # 等待 executor 进入 _running_executors, 避免 0.01s 固定 sleep
            # 受系统负载影响导致尚未启动就调用 cancel()。
            for _ in range(100):
                if "build" in runner._running_executors:
                    break
                await asyncio.sleep(0.01)
            else:
                pytest.fail("Executor was not added to _running_executors within 1s")
            await runner.cancel()
            await run_task

        assert mock_executor.cancel.called

    @pytest.mark.asyncio
    async def test_retry_on_failure(self, db_engine, clean_db):
        _setup_config()
        tasks = [ResolvedTask(name="t1", task_type="command", command="exit 1", retry=2)]
        pipeline = make_pipeline("retry", tasks)
        ctx = ExecutionContext(pipeline=pipeline, run_id="exec-retry")

        runner = PipelineRunner(run_id="exec-retry", pipeline=pipeline, context=ctx)

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
    async def test_when_condition_skips_task(self, db_engine, clean_db):
        _setup_config()
        tasks = [
            ResolvedTask(
                name="should_skip",
                task_type="command",
                command="echo should not run",
                when='${env.SKIP_ME} == "yes"',
            ),
        ]
        pipeline = make_pipeline("when", tasks)
        ctx = ExecutionContext(pipeline=pipeline, run_id="exec-when", env={"SKIP_ME": "no"})

        runner = PipelineRunner(run_id="exec-when", pipeline=pipeline, context=ctx)

        mock_executor = AsyncMock()

        with (
            patch("taskpps.engine.runner.create_executor", return_value=mock_executor),
            patch("taskpps.engine.runner.get_logs_dir"),
            patch("taskpps.engine.runner.get_event_bus"),
        ):
            await runner.run()

        mock_executor.execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_multiple_commands_execution(self, db_engine, clean_db):
        _setup_config()
        tasks = [ResolvedTask(name="multi", task_type="command", commands=["echo step1", "echo step2", "echo step3"])]
        pipeline = make_pipeline("multi-cmd", tasks)
        ctx = ExecutionContext(pipeline=pipeline, run_id="exec-multi")

        runner = PipelineRunner(run_id="exec-multi", pipeline=pipeline, context=ctx)

        mock_executor = AsyncMock()
        mock_executor.execute.return_value = ExecutorResult(exit_code=0, stdout="ok")

        with (
            patch("taskpps.engine.runner.create_executor", return_value=mock_executor),
            patch("taskpps.engine.runner.get_logs_dir"),
            patch("taskpps.engine.runner.get_event_bus"),
        ):
            await runner.run()

        assert mock_executor.execute.call_count == 3

    @pytest.mark.asyncio
    async def test_empty_pipeline_returns_immediately(self, db_engine, clean_db):
        _setup_config()
        pipeline = ResolvedPipeline(name="empty", subpipelines=[])
        ctx = ExecutionContext(pipeline=pipeline, run_id="exec-empty")
        runner = PipelineRunner(run_id="exec-empty", pipeline=pipeline, context=ctx)

        with patch("taskpps.engine.runner.get_event_bus"):
            await runner.run()

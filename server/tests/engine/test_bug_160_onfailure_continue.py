"""
Bug #160: on_failure=continue 在 task 级别（含 retry 耗尽场景）未生效
- 依赖任务的 on_failure 应阻止下游被 block
- SubPipeline 级别 on_failure=continue 行为正确（已有覆盖）
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from taskpps.domain.context import ExecutionContext
from taskpps.domain.pipeline import ResolvedPipeline, ResolvedSubPipeline, ResolvedTask
from taskpps.engine.runner import PipelineRunner
from taskpps.executors.base import ExecutorResult
from taskpps.schemas.pipeline import PipelineConfig


def _make_subpipeline(
    sub_name: str,
    tasks: list[ResolvedTask],
    on_failure: str = "fail",
    depends_on: list[str] | None = None,
) -> ResolvedSubPipeline:
    return ResolvedSubPipeline(
        name=sub_name,
        tasks=tasks,
        config=PipelineConfig(on_failure=on_failure),
        depends_on=depends_on or [],
    )


@pytest.fixture
def mock_session_factory():
    """Minimal session mock sufficient for _execute_subpipeline flow."""
    mock_session = MagicMock()
    mock_cm = MagicMock()
    mock_cm.__aenter__ = AsyncMock(return_value=mock_session)
    mock_cm.__aexit__ = AsyncMock(return_value=None)
    mock_sf = MagicMock(return_value=mock_cm)

    from taskpps.db.repository import RunRepository, TaskRunRepository

    with (
        patch("taskpps.engine.runner.get_session_factory", return_value=mock_sf),
        patch("taskpps.engine.runner.RunRepository", return_value=AsyncMock()),
        patch("taskpps.engine.runner.TaskRunRepository", return_value=AsyncMock()),
    ):
        yield


@pytest.mark.asyncio
class TestOnFailureContinueTaskLevel:
    """Bug #160 核心场景: task 级别 on_failure=continue"""

    @pytest.mark.zentao("TC-S1700", domain="server/engine", priority="P0")
    async def test_on_failure_continue_depends_on_dependency_fails_but_dependent_runs(
        self, mock_session_factory
    ):
        """
        Bug #160 复现:
        task_a: on_failure=continue  + task 必然失败
        task_b: depends_on=[task_a]
        期望: task_b 应继续执行（不被 SKIP）
        实际(当前Bug): task_b 被 SKIP
        """
        task_a = ResolvedTask(
            name="task_a", task_type="command", command="exit 1",
            on_failure="continue",
        )
        task_b = ResolvedTask(
            name="task_b", task_type="command", command="echo ok",
            depends_on=["task_a"],
        )
        sub = _make_subpipeline("sub", [task_a, task_b])
        pipeline = ResolvedPipeline(name="test", subpipelines=[sub], top_config=PipelineConfig())
        ctx = ExecutionContext(pipeline=pipeline, run_id="bug160_1")
        runner = PipelineRunner(run_id="bug160_1", pipeline=pipeline, context=ctx)
        runner._task_run_ids = {"sub.task_a": "tr_a", "sub.task_b": "tr_b"}

        mock_executor = AsyncMock()
        mock_executor.execute.return_value = ExecutorResult(exit_code=1, stderr="fail")

        with (
            patch("taskpps.engine.runner.create_executor", return_value=mock_executor),
            patch("taskpps.engine.runner.get_logs_dir"),
            patch("taskpps.engine.runner.get_event_bus"),
            patch("taskpps.engine.runner.get_settings"),
        ):
            await runner.run()

        # Bug #160: on_failure=continue 时 task_b 应被执行而非被跳过
        # 当前 Bug 导致 task_b 被跳过, execute 只被 task_a 调用 1 次
        assert mock_executor.execute.call_count == 2, (
            f"on_failure=continue bug: task_b should execute, "
            f"but got {mock_executor.execute.call_count} calls"
        )

    @pytest.mark.zentao("TC-S1701", domain="server/engine", priority="P0")
    async def test_on_failure_continue_with_retry_exhausted_dependent_runs(
        self, mock_session_factory
    ):
        """
        Bug #160: retry 耗尽 + on_failure=continue + depends_on
        task_a: retry=2, on_failure=continue, 每次均失败
        task_b: depends_on=[task_a]
        期望: task_b 应继续执行
        """
        task_a = ResolvedTask(
            name="task_a", task_type="command", command="exit 1",
            retry=2, on_failure="continue",
        )
        task_b = ResolvedTask(
            name="task_b", task_type="command", command="echo ok",
            depends_on=["task_a"],
        )
        sub = _make_subpipeline("sub", [task_a, task_b])
        pipeline = ResolvedPipeline(name="test", subpipelines=[sub], top_config=PipelineConfig())
        ctx = ExecutionContext(pipeline=pipeline, run_id="bug160_retry")
        runner = PipelineRunner(run_id="bug160_retry", pipeline=pipeline, context=ctx)
        runner._task_run_ids = {"sub.task_a": "tr_a", "sub.task_b": "tr_b"}

        mock_executor = AsyncMock()
        mock_executor.execute.return_value = ExecutorResult(exit_code=1, stderr="fail")

        with (
            patch("taskpps.engine.runner.create_executor", return_value=mock_executor),
            patch("taskpps.engine.runner.get_logs_dir"),
            patch("taskpps.engine.runner.get_event_bus"),
            patch("taskpps.engine.runner.get_settings"),
        ):
            await runner.run()

        # retry=2 + 初始 attempt=1, task_a 总共执行 3 次, task_b 应再执行 1 次
        assert mock_executor.execute.call_count == 4, (
            f"retry exhausted + on_failure=continue: expected 4 calls "
            f"(3 for task_a retries + 1 for task_b), got {mock_executor.execute.call_count}"
        )

    @pytest.mark.zentao("TC-S1702", domain="server/engine", priority="P1")
    async def test_on_failure_continue_via_pipeline_config_dependent_runs(
        self, mock_session_factory
    ):
        """
        on_failure=continue 从 pipeline config 继承到 task
        task_a 失败, task_b 依赖 task_a
        期望: task_b 应继续执行
        """
        config = PipelineConfig(on_failure="continue")
        task_a = ResolvedTask(
            name="task_a", task_type="command", command="exit 1",
        )
        task_b = ResolvedTask(
            name="task_b", task_type="command", command="echo ok",
            depends_on=["task_a"],
        )
        sub = ResolvedSubPipeline(
            name="sub", tasks=[task_a, task_b], config=config,
        )
        pipeline = ResolvedPipeline(name="test", subpipelines=[sub], top_config=config)
        ctx = ExecutionContext(pipeline=pipeline, run_id="bug160_cfg")
        runner = PipelineRunner(run_id="bug160_cfg", pipeline=pipeline, context=ctx)
        runner._task_run_ids = {"sub.task_a": "tr_a", "sub.task_b": "tr_b"}

        mock_executor = AsyncMock()
        mock_executor.execute.return_value = ExecutorResult(exit_code=1, stderr="fail")

        with (
            patch("taskpps.engine.runner.create_executor", return_value=mock_executor),
            patch("taskpps.engine.runner.get_logs_dir"),
            patch("taskpps.engine.runner.get_event_bus"),
            patch("taskpps.engine.runner.get_settings"),
        ):
            await runner.run()

        assert mock_executor.execute.call_count == 2, (
            f"on_failure=continue via config: expected 2 calls, "
            f"got {mock_executor.execute.call_count}"
        )

    @pytest.mark.zentao("TC-S1703", domain="server/engine", priority="P1")
    async def test_on_failure_continue_large_retry_exhausted(self, mock_session_factory):
        """
        on_failure=continue + retry=5 (大值) 耗尽
        task_a: retry=5, on_failure=continue
        task_b: depends_on=[task_a]
        期望: task_b 继续执行
        """
        task_a = ResolvedTask(
            name="task_a", task_type="command", command="exit 1",
            retry=5, on_failure="continue",
        )
        task_b = ResolvedTask(
            name="task_b", task_type="command", command="echo ok",
            depends_on=["task_a"],
        )
        sub = _make_subpipeline("sub", [task_a, task_b])
        pipeline = ResolvedPipeline(name="test", subpipelines=[sub], top_config=PipelineConfig())
        ctx = ExecutionContext(pipeline=pipeline, run_id="bug160_bigretry")
        runner = PipelineRunner(run_id="bug160_bigretry", pipeline=pipeline, context=ctx)
        runner._task_run_ids = {"sub.task_a": "tr_a", "sub.task_b": "tr_b"}

        mock_executor = AsyncMock()
        mock_executor.execute.return_value = ExecutorResult(exit_code=1, stderr="fail")

        with (
            patch("taskpps.engine.runner.create_executor", return_value=mock_executor),
            patch("taskpps.engine.runner.get_logs_dir"),
            patch("taskpps.engine.runner.get_event_bus"),
            patch("taskpps.engine.runner.get_settings"),
        ):
            await runner.run()

        # retry=5: task_a attempts = 6, task_b = 1, total = 7
        assert mock_executor.execute.call_count == 7, (
            f"on_failure=continue + retry=5 exhausted: expected 7 calls, "
            f"got {mock_executor.execute.call_count}"
        )


@pytest.mark.asyncio
class TestOnFailureStopRegression:
    """回归: on_failure=stop(默认) 行为不变"""

    @pytest.mark.zentao("TC-S1704", domain="server/engine", priority="P1")
    async def test_on_failure_stop_blocks_dependent(self, mock_session_factory):
        """
        默认 on_failure=fail (stop) 行为: 依赖任务失败后, 下游被 block
        此场景必须保持不变
        """
        task_a = ResolvedTask(
            name="task_a", task_type="command", command="exit 1",
        )
        task_b = ResolvedTask(
            name="task_b", task_type="command", command="echo ok",
            depends_on=["task_a"],
        )
        sub = _make_subpipeline("sub", [task_a, task_b], on_failure="fail")
        pipeline = ResolvedPipeline(name="test", subpipelines=[sub], top_config=PipelineConfig())
        ctx = ExecutionContext(pipeline=pipeline, run_id="bug160_stop")
        runner = PipelineRunner(run_id="bug160_stop", pipeline=pipeline, context=ctx)
        runner._task_run_ids = {"sub.task_a": "tr_a", "sub.task_b": "tr_b"}

        mock_executor = AsyncMock()
        mock_executor.execute.return_value = ExecutorResult(exit_code=1, stderr="fail")

        with (
            patch("taskpps.engine.runner.create_executor", return_value=mock_executor),
            patch("taskpps.engine.runner.get_logs_dir"),
            patch("taskpps.engine.runner.get_event_bus"),
            patch("taskpps.engine.runner.get_settings"),
        ):
            await runner.run()

        # 默认 fail 行为: task_b 应被跳过, 只执行 task_a
        assert mock_executor.execute.call_count == 1, (
            f"on_failure=fail: task_b should be skipped, "
            f"but got {mock_executor.execute.call_count} calls"
        )

    @pytest.mark.zentao("TC-S1705", domain="server/engine", priority="P1")
    async def test_on_failure_stop_retry_exhausted_blocks_dependent(
        self, mock_session_factory
    ):
        """
        on_failure=fail (stop) + retry 耗尽: 下游应被 block
        回归确认 retry 耗尽后默认行为不变
        """
        task_a = ResolvedTask(
            name="task_a", task_type="command", command="exit 1",
            retry=2,
        )
        task_b = ResolvedTask(
            name="task_b", task_type="command", command="echo ok",
            depends_on=["task_a"],
        )
        sub = _make_subpipeline("sub", [task_a, task_b], on_failure="fail")
        pipeline = ResolvedPipeline(name="test", subpipelines=[sub], top_config=PipelineConfig())
        ctx = ExecutionContext(pipeline=pipeline, run_id="bug160_stop_retry")
        runner = PipelineRunner(run_id="bug160_stop_retry", pipeline=pipeline, context=ctx)
        runner._task_run_ids = {"sub.task_a": "tr_a", "sub.task_b": "tr_b"}

        mock_executor = AsyncMock()
        mock_executor.execute.return_value = ExecutorResult(exit_code=1, stderr="fail")

        with (
            patch("taskpps.engine.runner.create_executor", return_value=mock_executor),
            patch("taskpps.engine.runner.get_logs_dir"),
            patch("taskpps.engine.runner.get_event_bus"),
            patch("taskpps.engine.runner.get_settings"),
        ):
            await runner.run()

        # retry=2 + 初始: 3 次, task_b 被跳过, 总计 3
        assert mock_executor.execute.call_count == 3, (
            f"on_failure=fail + retry exhausted: expected 3 calls, "
            f"got {mock_executor.execute.call_count}"
        )


@pytest.mark.asyncio
class TestOnFailureContinueMixed:
    """混合场景: 多 task 中部分 on_failure=continue"""

    @pytest.mark.zentao("TC-S1706", domain="server/engine", priority="P1")
    async def test_mixed_on_failure_continue_and_stop(self, mock_session_factory):
        """
        task_a: on_failure=stop (失败 block 下游)
        task_b: depends_on=[task_a] (应被 block)
        task_c: on_failure=continue + 失败 (下游不 block)
        task_d: depends_on=[task_c] (应继续)
        当前Bug: task_a 先失败 → task_b 被 block
                 task_c 应不 block task_d, 但当前会被 block
        """
        task_a = ResolvedTask(
            name="task_a", task_type="command", command="exit 1",
        )
        task_b = ResolvedTask(
            name="task_b", task_type="command", command="echo b",
            depends_on=["task_a"],
        )
        task_c = ResolvedTask(
            name="task_c", task_type="command", command="exit 1",
            on_failure="continue",
        )
        task_d = ResolvedTask(
            name="task_d", task_type="command", command="echo d",
            depends_on=["task_c"],
        )
        sub = ResolvedSubPipeline(
            name="sub", tasks=[task_a, task_b, task_c, task_d],
            config=PipelineConfig(execution_strategy="parallel"),
        )
        pipeline = ResolvedPipeline(name="test", subpipelines=[sub], top_config=PipelineConfig())
        ctx = ExecutionContext(pipeline=pipeline, run_id="bug160_mixed")
        runner = PipelineRunner(run_id="bug160_mixed", pipeline=pipeline, context=ctx)
        runner._task_run_ids = {
            "sub.task_a": "tr_a", "sub.task_b": "tr_b",
            "sub.task_c": "tr_c", "sub.task_d": "tr_d",
        }

        mock_executor = AsyncMock()
        mock_executor.execute.return_value = ExecutorResult(exit_code=1, stderr="fail")

        with (
            patch("taskpps.engine.runner.create_executor", return_value=mock_executor),
            patch("taskpps.engine.runner.get_logs_dir"),
            patch("taskpps.engine.runner.get_event_bus"),
            patch("taskpps.engine.runner.get_settings"),
        ):
            await runner.run()

        # task_a + task_c 应执行 = 2 次; task_b 应被 skip; task_d 应执行 = 1 次
        # 总: 3 次. 当前 Bug 下 task_d 被跳过, 只有 2 次
        assert mock_executor.execute.call_count == 3, (
            f"mixed scenario: expected 3 calls (task_a + task_c + task_d), "
            f"got {mock_executor.execute.call_count}"
        )

    @pytest.mark.zentao("TC-S1707", domain="server/engine", priority="P1")
    async def test_chain_dependency_middle_on_failure_continue(self, mock_session_factory):
        """
        task_a → task_b(on_failure=continue, 失败) → task_c
        task_a 成功, task_b 失败但 on_failure=continue, task_c 应继续
        """
        task_a = ResolvedTask(
            name="task_a", task_type="command", command="echo ok",
        )
        task_b = ResolvedTask(
            name="task_b", task_type="command", command="exit 1",
            depends_on=["task_a"], on_failure="continue",
        )
        task_c = ResolvedTask(
            name="task_c", task_type="command", command="echo ok",
            depends_on=["task_b"],
        )
        sub = _make_subpipeline("sub", [task_a, task_b, task_c])
        pipeline = ResolvedPipeline(name="test", subpipelines=[sub], top_config=PipelineConfig())
        ctx = ExecutionContext(pipeline=pipeline, run_id="bug160_chain")
        runner = PipelineRunner(run_id="bug160_chain", pipeline=pipeline, context=ctx)
        runner._task_run_ids = {
            "sub.task_a": "tr_a", "sub.task_b": "tr_b", "sub.task_c": "tr_c",
        }

        call_count = 0

        async def _execute(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return ExecutorResult(exit_code=0, stdout="ok")
            return ExecutorResult(exit_code=1, stderr="fail")

        mock_executor = AsyncMock()
        mock_executor.execute.side_effect = _execute

        with (
            patch("taskpps.engine.runner.create_executor", return_value=mock_executor),
            patch("taskpps.engine.runner.get_logs_dir"),
            patch("taskpps.engine.runner.get_event_bus"),
            patch("taskpps.engine.runner.get_settings"),
        ):
            await runner.run()

        # task_a 成功(1) + task_b 失败(1) + task_c 应执行(1) = 3
        assert mock_executor.execute.call_count == 3, (
            f"chain dependency: expected 3 calls, got {mock_executor.execute.call_count}"
        )

"""
Bug #202: [BUG] connection lost 时不重连直接执行下一个 task

核心问题:
1. Agent 执行 task 时 WebSocket 断连，cleanup_command() 将 future 以
   {"exit_code": -1, "error": "connection lost"} 结束，但 runner 将其
   当作普通 task 失败处理，不会重连。
2. 即使 on_failure=continue，connection lost 作为基础设施故障也应
   block 后续 task，而非让后续 task 继续执行。

代码路径分析:
- agent_manager.py AgentConnection.cleanup_command():136 → future 解析为 connection lost
- agent_executor.py _execute_command():239-253 → 将 connection lost 作为 stderr 返回
- runner.py _execute_subpipeline():716-748 → 按普通失败处理，on_failure=continue 时下游不 block
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from taskpps.domain.context import ExecutionContext
from taskpps.domain.pipeline import ResolvedPipeline, ResolvedSubPipeline, ResolvedTask
from taskpps.engine.runner import PipelineRunner
from taskpps.executors.agent_executor import AgentExecutor
from taskpps.executors.base import ExecutorResult
from taskpps.schemas.pipeline import PipelineConfig


def _make_subpipeline(
    sub_name: str,
    tasks: list[ResolvedTask],
    on_failure: str = "fail",
    depends_on: list[str] | None = None,
) -> ResolvedSubPipeline:
    """构造测试用 SubPipeline，简化重复代码"""
    return ResolvedSubPipeline(
        name=sub_name,
        tasks=tasks,
        config=PipelineConfig(on_failure=on_failure),
        depends_on=depends_on or [],
    )


@pytest.fixture
def mock_session_factory():
    """最小化 session mock，满足 _execute_subpipeline 数据库写入流程"""
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
class TestConnectionLostNoReconnect:
    """Bug #202 场景1: connection lost 后不重连，直接当作普通失败"""

    @pytest.mark.zentao("TC-S2021", domain="server/engine", priority="P0")
    async def test_connection_lost_treated_as_normal_failure(self, mock_session_factory):
        """
        Bug #202 验证（修复后）:
        task_a 执行中 agent 断连 → cleanup_command 以 connection lost 结束 future
        → ExecutorResult.is_infrastructure_failure=True → runner block 后续 task

        修复后: connection lost 被识别为基础设施故障，即使 on_failure=continue
        也会 block task_b，call_count 应为 1
        """
        task_a = ResolvedTask(
            name="task_a", task_type="command", command="long_running_task",
            on_failure="continue",
        )
        task_b = ResolvedTask(
            name="task_b", task_type="command", command="echo ok",
            depends_on=["task_a"],
        )
        sub = _make_subpipeline("sub", [task_a, task_b], on_failure="continue")
        pipeline = ResolvedPipeline(name="test", subpipelines=[sub], top_config=PipelineConfig())
        ctx = ExecutionContext(pipeline=pipeline, run_id="bug202_1")
        runner = PipelineRunner(run_id="bug202_1", pipeline=pipeline, context=ctx)
        runner._task_run_ids = {"sub.task_a": "tr_a", "sub.task_b": "tr_b"}

        # 模拟 task_a 因 connection lost 失败（exit_code=-1, stderr="connection lost"）
        # task_b 正常执行
        call_count = 0

        async def _execute(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                # task_a: connection lost 导致的失败，标记为基础设施故障
                return ExecutorResult(exit_code=-1, stderr="connection lost", is_infrastructure_failure=True)
            # task_b: 如果被执行则正常返回
            return ExecutorResult(exit_code=0, stdout="ok")

        mock_executor = AsyncMock()
        mock_executor.execute.side_effect = _execute

        with (
            patch("taskpps.engine.runner.create_executor", return_value=mock_executor),
            patch("taskpps.engine.runner.get_logs_dir"),
            patch("taskpps.engine.runner.get_event_bus"),
            patch("taskpps.engine.runner.get_settings"),
        ):
            await runner.run()

        # v2 (2026-07): 修复后 connection lost 被识别为基础设施故障，
        # 即使 on_failure=continue 也会 block，task_b 不应执行
        assert call_count == 1, (
            f"Bug #202 修复验证: connection lost + on_failure=continue 时 "
            f"task_b 不应执行（期望 1 次，实际执行了 {call_count} 次）"
        )

    @pytest.mark.zentao("TC-S2022", domain="server/engine", priority="P0")
    async def test_connection_lost_with_on_failure_continue_still_blocks(self, mock_session_factory):
        """
        Bug #202 场景2（修复后）: on_failure=continue 但 connection lost 仍应 block

        当 task 因 connection lost 失败时，即使 on_failure=continue，
        后续 task 也不应继续执行。因为 connection lost 是基础设施故障，
        后续 task 也会因为同样的连接问题而失败。
        """
        task_a = ResolvedTask(
            name="task_a", task_type="command", command="long_running_task",
        )
        task_b = ResolvedTask(
            name="task_b", task_type="command", command="echo ok",
            depends_on=["task_a"],
            on_failure="continue",
        )
        # subpipeline 级别 on_failure=continue
        sub = ResolvedSubPipeline(
            name="sub",
            tasks=[task_a, task_b],
            config=PipelineConfig(on_failure="continue"),
        )
        pipeline = ResolvedPipeline(name="test", subpipelines=[sub], top_config=PipelineConfig(on_failure="continue"))
        ctx = ExecutionContext(pipeline=pipeline, run_id="bug202_2")
        runner = PipelineRunner(run_id="bug202_2", pipeline=pipeline, context=ctx)
        runner._task_run_ids = {"sub.task_a": "tr_a", "sub.task_b": "tr_b"}

        call_count = 0

        async def _execute(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                # task_a: connection lost，标记为基础设施故障
                return ExecutorResult(exit_code=-1, stderr="connection lost", is_infrastructure_failure=True)
            return ExecutorResult(exit_code=0, stdout="ok")

        mock_executor = AsyncMock()
        mock_executor.execute.side_effect = _execute

        with (
            patch("taskpps.engine.runner.create_executor", return_value=mock_executor),
            patch("taskpps.engine.runner.get_logs_dir"),
            patch("taskpps.engine.runner.get_event_bus"),
            patch("taskpps.engine.runner.get_settings"),
        ):
            await runner.run()

        # v2 (2026-07): 修复后即使 on_failure=continue，基础设施故障也 block
        assert call_count == 1, (
            f"Bug #202 修复验证: connection lost + 全部 on_failure=continue 时 "
            f"task_b 不应执行（期望 1 次，实际执行了 {call_count} 次）"
        )


@pytest.mark.asyncio
class TestConnectionLostAgentExecutor:
    """Bug #202 场景: AgentExecutor 层面 connection lost 处理"""

    @pytest.mark.zentao("TC-S2023", domain="server/executors", priority="P0")
    async def test_connection_lost_no_reconnect_during_execution(self, tmp_path):
        """
        Bug #202 核心路径: 执行中 connection lost 不会触发重连

        当命令已在执行中、WebSocket 断连时，cleanup_command 直接以
        connection lost 结束 future，没有尝试重连后恢复输出流。

        代码路径:
        1. agent_manager.AgentConnection.cleanup_command():136
           → future.set_result({"exit_code": -1, "error": "connection lost"})
        2. agent_executor._execute_command():239-253
           → 解析 result 得到 stderr="connection lost"
        3. 整个 task 以 exit_code=-1 失败，无重连逻辑
        """
        import asyncio

        from taskpps.services.agent_manager import AgentConnection, AgentManager

        # 构造真实的 AgentManager 和 AgentConnection
        manager = AgentManager()
        mock_ws = MagicMock()
        conn = AgentConnection("test-agent", mock_ws, _manager=manager)

        # 注册一个 pending command（模拟正在执行的命令）
        command_id = "cmd-123"
        fut = conn.register_pending(command_id, command="echo hello", status="running")

        # 模拟注册 output callback
        output_received = []

        def on_output(data):
            output_received.append(data)

        conn.register_output_callback(command_id, on_output)

        # 模拟 connection lost: cleanup_command 将 future 解析为 connection lost
        conn.cleanup_command(command_id)

        # 验证: future 以 connection lost 结束，无重连尝试
        result = fut.result()
        assert result["exit_code"] == -1
        assert result["error"] == "connection lost"
        assert len(output_received) == 0, "connection lost 后不应有更多输出"

        # 验证: command 已被清理，output callback 也被移除
        assert command_id not in conn._pending_commands
        assert command_id not in conn._output_callbacks

    @pytest.mark.zentao("TC-S2024", domain="server/executors", priority="P1")
    async def test_connection_lost_result_treated_as_normal_failure(self, tmp_path):
        """
        Bug #202（修复后）: AgentExecutor 将 connection loss 标记为基础设施故障

        验证 AgentExecutor._execute_command() 对 connection lost 的处理:
        返回 ExecutorResult(exit_code=-1, stderr="connection lost",
                            is_infrastructure_failure=True)
        区分了 "基础设施故障" 和 "任务逻辑失败"
        """
        import asyncio

        from unittest.mock import MagicMock, patch

        from taskpps.executors.agent_executor import AgentExecutor

        # mock manager: agent 已连接
        mock_manager = MagicMock()
        mock_manager.is_connected.return_value = True
        mock_manager.acquire_global = AsyncMock()
        mock_manager.release_global = MagicMock()
        mock_manager.acquire_agent = AsyncMock()
        mock_manager.release_agent = MagicMock()
        mock_manager.promote_command_to_running = MagicMock()

        # 创建 pending command future，模拟 connection lost
        loop = asyncio.get_event_loop()
        fut = loop.create_future()
        fut.set_result({"exit_code": -1, "signal_name": "", "error": "connection lost"})
        mock_manager.create_pending.return_value = fut

        # mock connection 和 send_command
        mock_conn = MagicMock()
        mock_conn._pending_commands = {}
        mock_manager.get_connection.return_value = mock_conn
        mock_manager.send_command = AsyncMock()
        mock_manager.cleanup_command = MagicMock()
        mock_manager.register_output_callback = MagicMock()

        executor = AgentExecutor("agent-1", mock_manager, {"agent_work_dir": "/tmp"})
        log_path = tmp_path / "conn_lost.log"

        result = await executor.execute("long_task", {}, log_path, timeout=30)

        # v2 (2026-07): 修复后 connection lost 被标记为基础设施故障
        assert result.exit_code == -1
        assert "connection lost" in result.stderr
        assert not result.success
        assert result.is_infrastructure_failure is True


@pytest.mark.asyncio
class TestConnectionLostAlwaysBlocks:
    """
    Bug #202 期望行为验证: connection lost 应总是 block 后续 task

    修复后这些测试应通过:
    - connection lost 时，无论 on_failure 如何设置，后续 task 都应被 block
    """

    @pytest.mark.zentao("TC-S2025", domain="server/engine", priority="P0")
    async def test_connection_lost_blocks_despite_on_failure_continue(self, mock_session_factory):
        """
        修复后的期望行为:
        task_a 因 connection lost 失败 → 即使 on_failure=continue
        → task_b 也应被 block（不执行）
        """
        task_a = ResolvedTask(
            name="task_a", task_type="command", command="long_running_task",
            on_failure="continue",
        )
        task_b = ResolvedTask(
            name="task_b", task_type="command", command="echo ok",
            depends_on=["task_a"],
        )
        sub = _make_subpipeline("sub", [task_a, task_b], on_failure="continue")
        pipeline = ResolvedPipeline(name="test", subpipelines=[sub], top_config=PipelineConfig())
        ctx = ExecutionContext(pipeline=pipeline, run_id="bug202_fix1")
        runner = PipelineRunner(run_id="bug202_fix1", pipeline=pipeline, context=ctx)
        runner._task_run_ids = {"sub.task_a": "tr_a", "sub.task_b": "tr_b"}

        call_count = 0

        async def _execute(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                # task_a: connection lost，标记为基础设施故障
                return ExecutorResult(exit_code=-1, stderr="connection lost", is_infrastructure_failure=True)
            return ExecutorResult(exit_code=0, stdout="ok")

        mock_executor = AsyncMock()
        mock_executor.execute.side_effect = _execute

        with (
            patch("taskpps.engine.runner.create_executor", return_value=mock_executor),
            patch("taskpps.engine.runner.get_logs_dir"),
            patch("taskpps.engine.runner.get_event_bus"),
            patch("taskpps.engine.runner.get_settings"),
        ):
            await runner.run()

        # v2 (2026-07): 修复后 connection lost 应 block 后续 task
        assert call_count == 1, (
            f"Bug #202 修复验证: connection lost 应 block task_b，"
            f"但执行了 {call_count} 次"
        )

    @pytest.mark.zentao("TC-S2026", domain="server/engine", priority="P0")
    async def test_connection_lost_blocks_all_subsequent_tasks(self, mock_session_factory):
        """
        修复后的期望行为:
        多个 task 串行执行，task_a 因 connection lost 失败
        → task_b 和 task_c 都应被 block
        """
        task_a = ResolvedTask(
            name="task_a", task_type="command", command="long_running_task",
            on_failure="continue",
        )
        task_b = ResolvedTask(
            name="task_b", task_type="command", command="echo b",
            depends_on=["task_a"],
            on_failure="continue",
        )
        task_c = ResolvedTask(
            name="task_c", task_type="command", command="echo c",
            depends_on=["task_b"],
            on_failure="continue",
        )
        sub = _make_subpipeline("sub", [task_a, task_b, task_c], on_failure="continue")
        pipeline = ResolvedPipeline(name="test", subpipelines=[sub], top_config=PipelineConfig(on_failure="continue"))
        ctx = ExecutionContext(pipeline=pipeline, run_id="bug202_fix2")
        runner = PipelineRunner(run_id="bug202_fix2", pipeline=pipeline, context=ctx)
        runner._task_run_ids = {
            "sub.task_a": "tr_a",
            "sub.task_b": "tr_b",
            "sub.task_c": "tr_c",
        }

        call_count = 0

        async def _execute(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                # task_a: connection lost，标记为基础设施故障
                return ExecutorResult(exit_code=-1, stderr="connection lost", is_infrastructure_failure=True)
            return ExecutorResult(exit_code=0, stdout="ok")

        mock_executor = AsyncMock()
        mock_executor.execute.side_effect = _execute

        with (
            patch("taskpps.engine.runner.create_executor", return_value=mock_executor),
            patch("taskpps.engine.runner.get_logs_dir"),
            patch("taskpps.engine.runner.get_event_bus"),
            patch("taskpps.engine.runner.get_settings"),
        ):
            await runner.run()

        # v2 (2026-07): 修复后 connection lost 应 block 所有后续 task
        assert call_count == 1, (
            f"Bug #202 修复验证: connection lost 应 block 所有后续 task，"
            f"但执行了 {call_count} 次"
        )

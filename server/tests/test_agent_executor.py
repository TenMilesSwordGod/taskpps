"""Issue #78: agent 占用排队+超时 + 断开等待重启+超时 测试"""
import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio

from taskpps.executors.agent_executor import AgentExecutor
from taskpps.services.agent_manager import AgentManager


@pytest_asyncio.fixture
async def manager():
    m = AgentManager()
    m.is_connected = MagicMock(return_value=True)
    m.get_connection = MagicMock(return_value=None)
    m.register_output_callback = MagicMock()
    loop = asyncio.get_running_loop()
    m.create_pending = MagicMock(return_value=loop.create_future())
    m.send_command = AsyncMock()
    m.cancel_command = AsyncMock()
    m.cleanup_command = MagicMock()
    yield m


@pytest.fixture
def log_path(tmp_path):
    return tmp_path / "test.log"


class TestAgentSchedulingScenarios:
    """Issue #100: 并发/顺序重试调度场景测试。"""

    @pytest.mark.asyncio
    async def test_sequential_task_waits_for_busy_agent(self, manager, log_path):
        """
        场景 A：一个 task 期望顺序执行，但当前 agent 正在跑一个允许并发的 task，
        后续 task 应等待该 task 释放 agent 槽位后才能执行。
        """
        # 先占满 agent-1 的槽位，模拟有一个并发任务正在执行
        await manager.acquire_agent("agent-1", max_parallel=1, timeout=5)

        executor = AgentExecutor("agent-1", manager, {"max_parallel": 1})
        executor.run_id = "run-seq"
        executor.task_name = "seq-task"

        started = asyncio.Event()

        async def delayed_release():
            await asyncio.sleep(0.1)
            manager.release_agent("agent-1")

        # 让 executor.execute 在 acquire_agent 阻塞期间，先不发送命令；
        # 等外部释放槽位后，再构造 pending future 并返回成功。
        def patched_create_pending(agent_id, command_id, **kwargs):
            started.set()
            loop = asyncio.get_running_loop()
            fut = loop.create_future()
            fut.set_result({"exit_code": 0, "signal_name": "", "error": ""})
            return fut

        manager.create_pending = patched_create_pending
        manager.send_command = AsyncMock()

        # 提前释放槽位，使等待中的 executor 能获取到槽位
        release_task = asyncio.create_task(delayed_release())

        result = await executor.execute("echo seq", {}, log_path)

        await release_task

        assert result.exit_code == 0
        assert started.is_set()
        # 信号量最终释放回 1
        assert manager._agent_semaphores["agent-1"]._value == 1

    @pytest.mark.asyncio
    async def test_queued_task_on_busy_agent_allows_other_agent_to_run(self, manager, log_path):
        """
        场景 B：任务 B 在 agent-1 上排队等待，此时任务 C 在 agent-2 上可立即执行。
        验证不同 agent 之间的信号量互不影响，排队任务继续等待。
        """
        # agent-1 繁忙（槽位占满）
        await manager.acquire_agent("agent-1", max_parallel=1, timeout=5)

        # 模拟任务 C：使用 agent-2，应立即执行
        executor_c = AgentExecutor("agent-2", manager, {"max_parallel": 1})
        executor_c.run_id = "run-c"
        executor_c.task_name = "task-c"

        loop = asyncio.get_running_loop()
        fut_c = loop.create_future()
        fut_c.set_result({"exit_code": 0, "signal_name": "", "error": ""})
        manager.create_pending = MagicMock(return_value=fut_c)
        manager.send_command = AsyncMock()

        result_c = await executor_c.execute("echo c", {}, log_path)
        assert result_c.exit_code == 0

        # agent-1 仍然繁忙，任务 B 无法获取槽位
        with pytest.raises(TimeoutError):
            await manager.acquire_agent("agent-1", max_parallel=1, timeout=0.05)

        manager.release_agent("agent-1")


class TestAcquireAgent:
    @pytest.mark.asyncio
    async def test_acquire_release_basic(self, manager, log_path):
        """基本获取和释放信号量"""
        await manager.acquire_agent("agent-1", max_parallel=2, timeout=5)
        assert "agent-1" in manager._agent_semaphores
        assert manager._agent_semaphores["agent-1"]._value == 1  # 2-1=1
        manager.release_agent("agent-1")
        assert manager._agent_semaphores["agent-1"]._value == 2

    @pytest.mark.asyncio
    async def test_acquire_blocks_when_full(self, manager, log_path):
        """信号量满时排队等待"""
        await manager.acquire_agent("agent-1", max_parallel=1, timeout=5)

        acquired = False

        async def try_acquire():
            nonlocal acquired
            await manager.acquire_agent("agent-1", max_parallel=1, timeout=5)
            acquired = True

        task = asyncio.create_task(try_acquire())
        await asyncio.sleep(0.1)
        assert not acquired

        manager.release_agent("agent-1")
        await asyncio.sleep(0.1)
        assert acquired
        manager.release_agent("agent-1")

    @pytest.mark.asyncio
    async def test_acquire_timeout(self, manager, log_path):
        """排队超时抛出 TimeoutError"""
        await manager.acquire_agent("agent-1", max_parallel=1, timeout=5)

        with pytest.raises(TimeoutError):
            await manager.acquire_agent("agent-1", max_parallel=1, timeout=0.2)

        manager.release_agent("agent-1")

    @pytest.mark.asyncio
    async def test_acquire_zero_timeout_no_wait(self, manager, log_path):
        """timeout=0 时，满则直接失败"""
        await manager.acquire_agent("agent-1", max_parallel=1, timeout=5)

        with pytest.raises(TimeoutError):
            await manager.acquire_agent("agent-1", max_parallel=1, timeout=0)

        manager.release_agent("agent-1")

    @pytest.mark.asyncio
    async def test_release_unknown_agent(self, manager):
        """释放不存在的 agent 不报错"""
        manager.release_agent("nonexistent")


class TestExecutorSemaphore:
    @pytest.mark.asyncio
    async def test_execute_acquires_and_releases(self, manager, log_path):
        """execute 方法正确获取和释放信号量"""
        executor = AgentExecutor("agent-1", manager, {"max_parallel": 2})
        executor.run_id = "test-run"
        executor.task_name = "test-task"

        loop = asyncio.get_running_loop()
        fut = loop.create_future()
        fut.set_result({"exit_code": 0, "signal_name": "", "error": ""})
        manager.create_pending = MagicMock(return_value=fut)

        result = await executor.execute("echo hello", {}, log_path)

        assert result.exit_code == 0
        assert manager._agent_semaphores["agent-1"]._value == 2

    @pytest.mark.asyncio
    async def test_execute_releases_on_failure(self, manager, log_path):
        """execute 失败时也释放信号量"""
        executor = AgentExecutor("agent-1", manager, {"max_parallel": 1})
        executor.run_id = "test-run"
        executor.task_name = "test-task"

        manager.send_command = AsyncMock(side_effect=RuntimeError("connection lost"))

        result = await executor.execute("echo hello", {}, log_path)

        assert result.exit_code == -1
        assert manager._agent_semaphores["agent-1"]._value == 1

    @pytest.mark.asyncio
    async def test_execute_queue_timeout(self, manager, log_path):
        """排队超时返回错误结果"""
        # 先占满信号量
        await manager.acquire_agent("agent-1", max_parallel=1, timeout=5)

        executor = AgentExecutor("agent-1", manager, {"max_parallel": 1})
        executor.run_id = "run-2"
        executor.task_name = "task-2"

        with patch("taskpps.executors.agent_executor.get_settings") as mock_settings:
            settings = MagicMock()
            settings.executor.agent_queue_timeout = 0.2
            settings.executor.agent_offline_timeout = 0
            settings.executor.default_timeout = 60
            mock_settings.return_value = settings

            result = await executor.execute("echo hello", {}, log_path)

        assert result.exit_code == -1
        assert "timeout" in result.stderr.lower() or "busy" in result.stderr.lower()

        manager.release_agent("agent-1")

    @pytest.mark.asyncio
    async def test_cleanup_releases_semaphore(self, manager, log_path):
        """cleanup 方法释放信号量"""
        executor = AgentExecutor("agent-1", manager, {"max_parallel": 1})
        executor.run_id = "test-run"
        executor.task_name = "test-task"

        await manager.acquire_agent("agent-1", max_parallel=1, timeout=5)
        executor._slot_acquired = True

        assert manager._agent_semaphores["agent-1"]._value == 0

        executor.cleanup()

        assert not executor._slot_acquired
        assert manager._agent_semaphores["agent-1"]._value == 1

    @pytest.mark.asyncio
    async def test_not_connected_no_semaphore(self, manager, log_path):
        """agent 未连接时不获取信号量"""
        manager.is_connected = MagicMock(return_value=False)

        executor = AgentExecutor("agent-1", manager)
        with patch("taskpps.executors.agent_executor.get_settings") as mock_settings:
            settings = MagicMock()
            settings.executor.agent_offline_timeout = 0
            mock_settings.return_value = settings

            result = await executor.execute("echo hello", {}, log_path)

        assert result.exit_code == -1
        assert "not connected" in result.stderr.lower()
        assert "agent-1" not in manager._agent_semaphores

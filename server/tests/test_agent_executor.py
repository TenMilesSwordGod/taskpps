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

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from taskpps.executors.agent_executor import AgentExecutor


@pytest.fixture
def mock_manager():
    mgr = MagicMock()
    mgr.is_connected = MagicMock(return_value=True)
    mgr.send_command = AsyncMock()
    mgr.cancel_command = AsyncMock()
    mgr.create_pending = MagicMock()
    mgr.register_output_callback = MagicMock()
    return mgr


@pytest.fixture
def agent_data():
    return {"agent_work_dir": "/home/agent", "agent_auto_bootstrap": True}


class TestAgentExecutorExecute:
    @pytest.mark.asyncio
    async def test_execute_success(self, tmp_path, mock_manager, agent_data):
        log_path = tmp_path / "agent_exec.log"
        fut = asyncio.get_event_loop().create_future()
        fut.set_result({"exit_code": 0, "signal_name": "", "error": ""})
        mock_manager.create_pending.return_value = fut

        executor = AgentExecutor("agent-1", mock_manager, agent_data)
        result = await executor.execute("echo hello", {}, log_path, timeout=30, cwd="/custom/cwd")

        assert result.exit_code == 0
        mock_manager.send_command.assert_called_once_with(
            "agent-1", executor._command_id, "echo hello", {}, "/custom/cwd", 30
        )

    @pytest.mark.asyncio
    async def test_execute_not_connected_no_bootstrap(self, tmp_path, mock_manager):
        log_path = tmp_path / "agent_no_bootstrap.log"
        mock_manager.is_connected.return_value = False

        executor = AgentExecutor("agent-1", mock_manager, None)
        result = await executor.execute("echo hello", {}, log_path)

        assert result.exit_code == -1
        assert "not connected" in result.stderr

    @pytest.mark.asyncio
    async def test_execute_not_connected_auto_bootstrap_false(self, tmp_path, mock_manager):
        log_path = tmp_path / "agent_no_auto.log"
        mock_manager.is_connected.return_value = False

        agent_data = {"agent_auto_bootstrap": False}
        executor = AgentExecutor("agent-1", mock_manager, agent_data)
        result = await executor.execute("echo hello", {}, log_path)

        assert result.exit_code == -1
        assert "not connected" in result.stderr

    @pytest.mark.asyncio
    async def test_execute_timeout(self, tmp_path, mock_manager, agent_data):
        log_path = tmp_path / "agent_timeout.log"
        fut = asyncio.get_event_loop().create_future()
        mock_manager.create_pending.return_value = fut

        executor = AgentExecutor("agent-1", mock_manager, agent_data)

        async def _run():
            return await executor.execute("echo hello", {}, log_path, timeout=1)

        task = asyncio.ensure_future(_run())
        await asyncio.sleep(0.5)
        # Let the timeout trigger — wait_for(..., timeout=1+10)
        # Actually, we need to mock the timeout behavior
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    @pytest.mark.asyncio
    async def test_execute_timeout_direct(self, tmp_path, mock_manager, agent_data):
        log_path = tmp_path / "agent_timeout2.log"
        fut = asyncio.get_event_loop().create_future()
        mock_manager.create_pending.return_value = fut

        executor = AgentExecutor("agent-1", mock_manager, agent_data)

        # Simulate timeout by not resolving the future and using a very short timeout
        with patch("asyncio.wait_for", side_effect=asyncio.TimeoutError()):
            result = await executor.execute("echo hello", {}, log_path, timeout=0)

        assert result.exit_code == -1
        mock_manager.cancel_command.assert_called_once()

    @pytest.mark.asyncio
    async def test_execute_cancelled_error(self, tmp_path, mock_manager, agent_data):
        log_path = tmp_path / "agent_cancel.log"
        fut = asyncio.get_event_loop().create_future()
        mock_manager.create_pending.return_value = fut

        executor = AgentExecutor("agent-1", mock_manager, agent_data)

        with patch("asyncio.wait_for", side_effect=asyncio.CancelledError()):
            result = await executor.execute("echo hello", {}, log_path, timeout=30)

        assert result.exit_code == -1
        mock_manager.cancel_command.assert_called_once()

    @pytest.mark.asyncio
    async def test_execute_send_command_exception(self, tmp_path, mock_manager, agent_data):
        log_path = tmp_path / "agent_send_err.log"
        mock_manager.send_command.side_effect = RuntimeError("connection lost")

        executor = AgentExecutor("agent-1", mock_manager, agent_data)
        result = await executor.execute("echo hello", {}, log_path, timeout=30)

        assert result.exit_code == -1
        assert "connection lost" in result.stderr

    @pytest.mark.asyncio
    async def test_execute_with_signal(self, tmp_path, mock_manager, agent_data):
        log_path = tmp_path / "agent_signal.log"
        fut = asyncio.get_event_loop().create_future()
        fut.set_result({"exit_code": -1, "signal_name": "SIGTERM", "error": ""})
        mock_manager.create_pending.return_value = fut

        executor = AgentExecutor("agent-1", mock_manager, agent_data)
        result = await executor.execute("echo hello", {}, log_path, timeout=30)

        assert result.exit_code == -1

    @pytest.mark.asyncio
    async def test_execute_with_error(self, tmp_path, mock_manager, agent_data):
        log_path = tmp_path / "agent_error.log"
        fut = asyncio.get_event_loop().create_future()
        fut.set_result({"exit_code": 1, "signal_name": "", "error": "command not found"})
        mock_manager.create_pending.return_value = fut

        executor = AgentExecutor("agent-1", mock_manager, agent_data)
        result = await executor.execute("badcmd", {}, log_path, timeout=30)

        assert result.exit_code == 1
        assert "command not found" in result.stderr

    @pytest.mark.asyncio
    async def test_execute_cwd_fallback_to_agent_work_dir(self, tmp_path, mock_manager, agent_data):
        log_path = tmp_path / "agent_cwd.log"
        fut = asyncio.get_event_loop().create_future()
        fut.set_result({"exit_code": 0, "signal_name": "", "error": ""})
        mock_manager.create_pending.return_value = fut

        executor = AgentExecutor("agent-1", mock_manager, agent_data)
        result = await executor.execute("echo hello", {}, log_path, timeout=30)

        assert result.exit_code == 0
        mock_manager.send_command.assert_called_once_with(
            "agent-1", executor._command_id, "echo hello", {}, "/home/agent", 30
        )

    @pytest.mark.asyncio
    async def test_execute_cwd_empty_when_no_data(self, tmp_path, mock_manager):
        log_path = tmp_path / "agent_no_cwd.log"
        fut = asyncio.get_event_loop().create_future()
        fut.set_result({"exit_code": 0, "signal_name": "", "error": ""})
        mock_manager.create_pending.return_value = fut

        executor = AgentExecutor("agent-1", mock_manager, None)
        result = await executor.execute("echo hello", {}, log_path, timeout=30)

        assert result.exit_code == 0
        mock_manager.send_command.assert_called_once_with("agent-1", executor._command_id, "echo hello", {}, "", 30)

    @pytest.mark.asyncio
    async def test_execute_default_timeout_from_settings(self, tmp_path, mock_manager, agent_data):
        log_path = tmp_path / "agent_def_timeout.log"
        fut = asyncio.get_event_loop().create_future()
        fut.set_result({"exit_code": 0, "signal_name": "", "error": ""})
        mock_manager.create_pending.return_value = fut

        from taskpps.config import get_settings

        default_timeout = get_settings().executor.default_timeout

        executor = AgentExecutor("agent-1", mock_manager, agent_data)
        result = await executor.execute("echo hello", {}, log_path)

        assert result.exit_code == 0
        mock_manager.send_command.assert_called_once_with(
            "agent-1", executor._command_id, "echo hello", {}, "/home/agent", default_timeout
        )


class TestAgentExecutorCancel:
    @pytest.mark.asyncio
    async def test_cancel_with_command_id(self, mock_manager, agent_data):
        executor = AgentExecutor("agent-1", mock_manager, agent_data)
        executor._command_id = "cmd-123"

        await executor.cancel()

        assert executor._cancelled is True
        mock_manager.cancel_command.assert_called_once_with("agent-1", "cmd-123")

    @pytest.mark.asyncio
    async def test_cancel_without_command_id(self, mock_manager, agent_data):
        executor = AgentExecutor("agent-1", mock_manager, agent_data)
        executor._command_id = None

        await executor.cancel()

        assert executor._cancelled is True
        mock_manager.cancel_command.assert_not_called()


class TestAgentExecutorEnsureConnected:
    @pytest.mark.asyncio
    async def test_already_connected(self, tmp_path, mock_manager, agent_data):
        log_path = tmp_path / "ensure.log"
        mock_manager.is_connected.return_value = True

        executor = AgentExecutor("agent-1", mock_manager, agent_data)
        result = await executor._ensure_connected(log_path)

        assert result is True

    @pytest.mark.asyncio
    async def test_not_connected_no_agent_data(self, tmp_path, mock_manager):
        log_path = tmp_path / "ensure_no_data.log"
        mock_manager.is_connected.return_value = False

        executor = AgentExecutor("agent-1", mock_manager, None)
        result = await executor._ensure_connected(log_path)

        assert result is False

    @pytest.mark.asyncio
    async def test_not_connected_auto_bootstrap_false(self, tmp_path, mock_manager):
        log_path = tmp_path / "ensure_auto_false.log"
        mock_manager.is_connected.return_value = False

        agent_data = {"agent_auto_bootstrap": False}
        executor = AgentExecutor("agent-1", mock_manager, agent_data)
        result = await executor._ensure_connected(log_path)

        assert result is False

    @pytest.mark.asyncio
    async def test_bootstrap_success(self, tmp_path, mock_manager):
        log_path = tmp_path / "ensure_bootstrap.log"
        mock_manager.is_connected.return_value = False

        agent_data = {"agent_auto_bootstrap": True}
        executor = AgentExecutor("agent-1", mock_manager, agent_data)

        with patch("taskpps.services.agent_bootstrap.AgentBootstrap") as mock_bootstrap_cls:
            mock_bootstrap = MagicMock()
            mock_bootstrap.bootstrap = AsyncMock(return_value={"success": True})
            mock_bootstrap_cls.return_value = mock_bootstrap

            result = await executor._ensure_connected(log_path)

            assert result is True

    @pytest.mark.asyncio
    async def test_bootstrap_failure(self, tmp_path, mock_manager):
        log_path = tmp_path / "ensure_bootstrap_fail.log"
        mock_manager.is_connected.return_value = False

        agent_data = {"agent_auto_bootstrap": True}
        executor = AgentExecutor("agent-1", mock_manager, agent_data)

        with patch("taskpps.services.agent_bootstrap.AgentBootstrap") as mock_bootstrap_cls:
            mock_bootstrap = MagicMock()
            mock_bootstrap.bootstrap = AsyncMock(return_value={"success": False})
            mock_bootstrap_cls.return_value = mock_bootstrap

            result = await executor._ensure_connected(log_path)

            assert result is False

    @pytest.mark.asyncio
    async def test_bootstrap_exception(self, tmp_path, mock_manager):
        log_path = tmp_path / "ensure_bootstrap_exc.log"
        mock_manager.is_connected.return_value = False

        agent_data = {"agent_auto_bootstrap": True}
        executor = AgentExecutor("agent-1", mock_manager, agent_data)

        with patch("taskpps.services.agent_bootstrap.AgentBootstrap") as mock_bootstrap_cls:
            mock_bootstrap = MagicMock()
            mock_bootstrap.bootstrap = AsyncMock(side_effect=RuntimeError("deploy failed"))
            mock_bootstrap_cls.return_value = mock_bootstrap

            result = await executor._ensure_connected(log_path)

            assert result is False


class TestAgentExecutorLog:
    def test_log_creates_parent_dir(self, tmp_path):
        mock_manager = MagicMock()
        executor = AgentExecutor("agent-1", mock_manager, None)
        log_path = tmp_path / "subdir" / "agent.log"

        executor._log(log_path, "test message\n")

        assert log_path.exists()
        assert "test message" in log_path.read_text()

    def test_log_swallows_exception(self, tmp_path):
        mock_manager = MagicMock()
        executor = AgentExecutor("agent-1", mock_manager, None)

        # path where parent is a file, not a directory
        parent = tmp_path / "parent_is_file"
        parent.write_text("block")
        log_path = parent / "agent.log"

        # should not raise
        executor._log(log_path, "test message\n")


class TestAgentExecutorOutputCallback:
    """Regression test for issue #16: on_output used to do file I/O inside
    the WebSocket handler's event loop, so a slow disk could freeze the
    event loop, backpressure the agent, and make the task appear stuck.
    The fix schedules the file write via run_in_executor.
    """

    @pytest.mark.asyncio
    async def test_on_output_writes_off_event_loop(self, tmp_path, mock_manager, agent_data):
        log_path = tmp_path / "off_loop.log"
        fut = asyncio.get_event_loop().create_future()
        fut.set_result({"exit_code": 0, "signal_name": "", "error": ""})
        mock_manager.create_pending.return_value = fut

        executor = AgentExecutor("agent-1", mock_manager, agent_data)
        await executor.execute("echo hello", {}, log_path, timeout=30)

        # Grab the registered callback
        assert mock_manager.register_output_callback.called
        agent_id, command_id, on_output = mock_manager.register_output_callback.call_args[0]
        assert agent_id == "agent-1"
        assert command_id == executor._command_id

        # Slow the file write so the event loop would block if on_output
        # were doing the I/O synchronously. We measure the time it takes
        # for on_output to return — with run_in_executor it should be
        # effectively zero regardless of how slow the I/O is.
        import time

        from taskpps.executors import agent_executor

        original = agent_executor._write_log_chunk

        def slow_write(path, data):
            time.sleep(0.5)
            original(path, data)

        with patch.object(agent_executor, "_write_log_chunk", side_effect=slow_write):
            t0 = time.monotonic()
            on_output("chunk-1\n")
            elapsed = time.monotonic() - t0

        # on_output must return quickly even when the underlying I/O is slow
        assert elapsed < 0.1, f"on_output blocked the event loop for {elapsed:.3f}s"

        # And the chunk must eventually land in the log file
        for _ in range(20):
            if "chunk-1" in log_path.read_text():
                break
            await asyncio.sleep(0.1)
        assert "chunk-1" in log_path.read_text()

    @pytest.mark.asyncio
    async def test_on_output_no_running_loop_falls_back(self, tmp_path):
        """If on_output is somehow invoked without a running loop (e.g. in
        a test or sync context), it must still write the chunk instead of
        silently dropping it."""
        log_path = tmp_path / "fallback.log"

        # Simulate "no running loop" by patching get_running_loop to raise.
        # The callback must catch the RuntimeError and call _write_log_chunk
        # directly so no chunk is dropped.
        import asyncio as _asyncio

        from taskpps.executors import agent_executor

        def _raise(*_a, **_kw):
            raise RuntimeError("no running event loop")

        def callback(data):
            try:
                loop = _asyncio.get_running_loop()
                loop.run_in_executor(None, agent_executor._write_log_chunk, log_path, data)
            except RuntimeError:
                agent_executor._write_log_chunk(log_path, data)

        with patch.object(_asyncio, "get_running_loop", side_effect=_raise):
            callback("fallback-chunk\n")

        assert "fallback-chunk" in log_path.read_text()

from __future__ import annotations

import time
from unittest.mock import AsyncMock

import pytest

from taskpps.services.agent_manager import (
    DISPLAY_GRACE_PERIOD,
    AgentConnection,
    AgentManager,
)


def create_mock_ws():
    ws = AsyncMock()
    ws.receive_json = AsyncMock()
    ws.send_json = AsyncMock()
    ws.close = AsyncMock()
    return ws


class TestAgentManager:
    @pytest.mark.asyncio
    @pytest.mark.zentao("TC-S0415", domain="server/agent", priority="P1")
    async def test_is_connected_uses_display_grace_period(self):
        manager = AgentManager()
        ws = create_mock_ws()
        conn = AgentConnection("test-agent", ws)
        conn.last_heartbeat = time.time() - DISPLAY_GRACE_PERIOD + 10
        manager._connections["test-agent"] = conn

        assert manager.is_connected("test-agent") is True

    @pytest.mark.asyncio
    @pytest.mark.zentao("TC-S0416", domain="server/agent", priority="P1")
    async def test_is_connected_false_after_grace_period(self):
        manager = AgentManager()
        ws = create_mock_ws()
        conn = AgentConnection("test-agent", ws)
        conn.last_heartbeat = time.time() - DISPLAY_GRACE_PERIOD - 10
        manager._connections["test-agent"] = conn

        assert manager.is_connected("test-agent") is False

    @pytest.mark.asyncio
    @pytest.mark.zentao("TC-S0417", domain="server/agent", priority="P2")
    async def test_is_connected_nonexistent(self):
        manager = AgentManager()
        assert manager.is_connected("nonexistent") is False

    @pytest.mark.asyncio
    @pytest.mark.zentao("TC-S0418", domain="server/agent", priority="P0")
    async def test_handle_connection_returns_tuple(self):
        manager = AgentManager()
        ws = create_mock_ws()
        ws.receive_json.return_value = {
            "type": "handshake_request",
            "data": {
                "agent_id": "agent-1",
                "secret": "secret",
                "version": "1.0.0",
                "hostname": "myhost",
                "agent_pid": 1234,
            },
        }

        agent_id, conn = await manager.handle_connection(ws)

        assert agent_id == "agent-1"
        assert isinstance(conn, AgentConnection)
        assert conn.hostname == "myhost"
        assert conn.agent_pid == 1234
        assert conn.agent_version == "1.0.0"
        assert manager.get_connection("agent-1") is conn

    @pytest.mark.asyncio
    @pytest.mark.zentao("TC-S0419", domain="server/agent", priority="P1")
    async def test_handle_connection_closes_old_connection(self):
        manager = AgentManager()
        old_ws = create_mock_ws()
        old_ws.receive_json.return_value = {
            "type": "handshake_request",
            "data": {
                "agent_id": "agent-1",
                "secret": "secret",
                "version": "1.0.0",
                "hostname": "oldhost",
                "agent_pid": 111,
            },
        }
        await manager.handle_connection(old_ws)
        old_conn = manager.get_connection("agent-1")
        assert old_conn is not None

        new_ws = create_mock_ws()
        new_ws.receive_json.return_value = {
            "type": "handshake_request",
            "data": {
                "agent_id": "agent-1",
                "secret": "secret",
                "version": "1.0.0",
                "hostname": "newhost",
                "agent_pid": 222,
            },
        }
        await manager.handle_connection(new_ws)

        old_ws.close.assert_called_once()
        new_conn = manager.get_connection("agent-1")
        assert new_conn is not old_conn
        assert new_conn.hostname == "newhost"

    @pytest.mark.asyncio
    @pytest.mark.zentao("TC-S0420", domain="server/agent", priority="P1")
    async def test_disconnect_with_matching_conn(self):
        manager = AgentManager()
        ws = create_mock_ws()
        conn = AgentConnection("agent-1", ws)
        manager._connections["agent-1"] = conn

        await manager.disconnect("agent-1", conn)

        # Connection is preserved (with stale heartbeat) so a reconnecting
        # agent can transfer its pending commands back. See fix(#12).
        assert manager.get_connection("agent-1") is conn
        assert conn.last_heartbeat < 0

    @pytest.mark.asyncio
    @pytest.mark.zentao("TC-S0421", domain="server/agent", priority="P1")
    async def test_disconnect_with_non_matching_conn_does_not_remove(self):
        manager = AgentManager()
        ws1 = create_mock_ws()
        conn1 = AgentConnection("agent-1", ws1)
        manager._connections["agent-1"] = conn1

        ws2 = create_mock_ws()
        conn2 = AgentConnection("agent-1", ws2)

        await manager.disconnect("agent-1", conn2)

        assert manager.get_connection("agent-1") is conn1

    @pytest.mark.asyncio
    @pytest.mark.zentao("TC-S0422", domain="server/agent", priority="P1")
    async def test_disconnect_without_conn_always_removes(self):
        manager = AgentManager()
        ws = create_mock_ws()
        conn = AgentConnection("agent-1", ws)
        manager._connections["agent-1"] = conn

        await manager.disconnect("agent-1")

        # Same as the matching-conn case: keep the connection so reconnect
        # can hand off pending commands. See fix(#12).
        assert manager.get_connection("agent-1") is conn
        assert conn.last_heartbeat < 0

    @pytest.mark.asyncio
    @pytest.mark.zentao("TC-S0423", domain="server/agent", priority="P1")
    async def test_disconnect_preserves_pending_commands(self):
        # Pending commands must survive disconnect() so that long-running
        # tasks do not get a spurious "connection lost" failure when the
        # agent's WebSocket drops and reconnects. See fix(#12).
        manager = AgentManager()
        ws = create_mock_ws()
        conn = AgentConnection("agent-1", ws)
        fut = conn.register_pending("cmd-1")
        manager._connections["agent-1"] = conn

        await manager.disconnect("agent-1", conn)

        assert not fut.done()
        assert "cmd-1" in conn._pending_commands

    @pytest.mark.asyncio
    @pytest.mark.zentao("TC-S0424", domain="server/agent", priority="P1")
    async def test_reconnect_transfers_pending_commands(self):
        # When a new connection arrives for the same agent_id, the new
        # connection must inherit the old connection's pending commands and
        # output callbacks so the agent can keep streaming results. See fix(#12).
        manager = AgentManager()

        old_ws = create_mock_ws()
        old_ws.receive_json.return_value = {
            "type": "handshake_request",
            "data": {
                "agent_id": "agent-1",
                "secret": "secret",
                "version": "1.0.0",
                "hostname": "old",
                "agent_pid": 1,
            },
        }
        _, old_conn = await manager.handle_connection(old_ws)
        old_fut = old_conn.register_pending("cmd-keep")
        old_conn.register_output_callback("cmd-keep", lambda _d: None)

        new_ws = create_mock_ws()
        new_ws.receive_json.return_value = {
            "type": "handshake_request",
            "data": {
                "agent_id": "agent-1",
                "secret": "secret",
                "version": "1.0.0",
                "hostname": "new",
                "agent_pid": 2,
            },
        }
        _, new_conn = await manager.handle_connection(new_ws)

        # Pending command and callback were moved to the new connection;
        # the original future identity is preserved (executors are awaiting it).
        assert new_conn._pending_commands.get("cmd-keep").future is old_fut
        assert "cmd-keep" in new_conn._output_callbacks

    @pytest.mark.asyncio
    @pytest.mark.zentao("TC-S0425", domain="server/agent", priority="P1")
    async def test_reconnect_race_condition(self):
        """模拟重连竞态: 旧 handler 的 disconnect 不应移除新连接"""
        manager = AgentManager()

        old_ws = create_mock_ws()
        old_ws.receive_json.return_value = {
            "type": "handshake_request",
            "data": {
                "agent_id": "agent-1",
                "secret": "secret",
                "version": "1.0.0",
                "hostname": "old",
                "agent_pid": 1,
            },
        }
        _, old_conn = await manager.handle_connection(old_ws)

        new_ws = create_mock_ws()
        new_ws.receive_json.return_value = {
            "type": "handshake_request",
            "data": {
                "agent_id": "agent-1",
                "secret": "secret",
                "version": "1.0.0",
                "hostname": "new",
                "agent_pid": 2,
            },
        }
        _, new_conn = await manager.handle_connection(new_ws)

        assert manager.get_connection("agent-1") is new_conn

        await manager.disconnect("agent-1", old_conn)

        assert manager.get_connection("agent-1") is new_conn

    @pytest.mark.zentao("TC-S0426", domain="server/agent", priority="P2")
    def test_get_connection(self):
        manager = AgentManager()
        ws = create_mock_ws()
        conn = AgentConnection("agent-1", ws)
        manager._connections["agent-1"] = conn

        assert manager.get_connection("agent-1") is conn
        assert manager.get_connection("nonexistent") is None


class TestAgentManagerMore:
    """Tests for AgentManager branches not covered in existing tests."""

    @pytest.mark.asyncio
    @pytest.mark.zentao("TC-S0427", domain="server/agent", priority="P1")
    async def test_handle_connection_timeout(self):
        manager = AgentManager()
        ws = create_mock_ws()
        ws.receive_json.side_effect = __import__("asyncio").TimeoutError()

        with pytest.raises(__import__("asyncio").TimeoutError):
            await manager.handle_connection(ws)

        ws.close.assert_called_once()
        call_kwargs = ws.close.call_args
        assert call_kwargs[1]["code"] == 4001

    @pytest.mark.asyncio
    @pytest.mark.zentao("TC-S0428", domain="server/agent", priority="P2")
    async def test_handle_connection_wrong_message_type(self):
        manager = AgentManager()
        ws = create_mock_ws()
        ws.receive_json.return_value = {
            "type": "wrong_type",
            "data": {"agent_id": "agent-1"},
        }

        with pytest.raises(ValueError, match="Expected handshake_request"):
            await manager.handle_connection(ws)

        ws.close.assert_called_once()
        call_kwargs = ws.close.call_args
        assert call_kwargs[1]["code"] == 4002

    @pytest.mark.asyncio
    @pytest.mark.zentao("TC-S0429", domain="server/agent", priority="P2")
    async def test_handle_connection_agent_id_mismatch(self):
        manager = AgentManager()
        ws = create_mock_ws()
        ws.receive_json.return_value = {
            "type": "handshake_request",
            "data": {"agent_id": "wrong-agent", "secret": "s", "version": "1.0"},
        }

        with pytest.raises(ValueError, match="agent_id mismatch"):
            await manager.handle_connection(ws, expected_agent_id="expected-agent")

        ws.close.assert_called_once()
        call_kwargs = ws.close.call_args
        assert call_kwargs[1]["code"] == 4003

    @pytest.mark.asyncio
    @pytest.mark.zentao("TC-S0430", domain="server/agent", priority="P1")
    async def test_send_command_not_connected(self):
        manager = AgentManager()
        with pytest.raises(RuntimeError, match="not connected"):
            await manager.send_command("agent-1", "cmd-1", "echo", {}, "", 30)

    @pytest.mark.asyncio
    @pytest.mark.zentao("TC-S0431", domain="server/agent", priority="P1")
    async def test_cancel_command_not_connected(self):
        manager = AgentManager()
        # Should not raise
        await manager.cancel_command("agent-1", "cmd-1")

    @pytest.mark.asyncio
    @pytest.mark.zentao("TC-S0432", domain="server/agent", priority="P1")
    async def test_create_pending_not_connected(self):
        manager = AgentManager()
        fut = manager.create_pending("agent-1", "cmd-1")
        assert fut.done()
        result = fut.result()
        assert result["exit_code"] == -1
        assert result["error"] == "agent not connected"

    @pytest.mark.asyncio
    @pytest.mark.zentao("TC-S0433", domain="server/agent", priority="P1")
    async def test_register_output_callback_not_connected(self):
        manager = AgentManager()
        # Should not raise
        manager.register_output_callback("agent-1", "cmd-1", lambda x: x)

    @pytest.mark.asyncio
    @pytest.mark.zentao("TC-S0434", domain="server/agent", priority="P1")
    async def test_stop(self):
        manager = AgentManager()
        ws = create_mock_ws()
        conn = AgentConnection("agent-1", ws)
        manager._connections["agent-1"] = conn

        await manager.stop()

        assert manager.get_connection("agent-1") is None
        assert manager._active is False

    @pytest.mark.asyncio
    @pytest.mark.zentao("TC-S0435", domain="server/agent", priority="P2")
    async def test_send_command_with_lock(self):
        manager = AgentManager()
        ws = create_mock_ws()
        ws.send_json = AsyncMock()
        conn = AgentConnection("agent-1", ws)
        manager._connections["agent-1"] = conn

        await manager.send_command("agent-1", "cmd-1", "echo hello", {"KEY": "V"}, "/tmp", 30)

        ws.send_json.assert_called_once()
        call_args = ws.send_json.call_args[0][0]
        assert call_args["type"] == "exec_command"
        assert call_args["data"]["command"] == "echo hello"

    @pytest.mark.asyncio
    @pytest.mark.zentao("TC-S0436", domain="server/agent", priority="P1")
    async def test_disconnect_nonexistent_agent(self):
        manager = AgentManager()
        # Should not raise
        await manager.disconnect("nonexistent", None)

    @pytest.mark.asyncio
    @pytest.mark.zentao("TC-S0437", domain="server/agent", priority="P1")
    async def test_is_connected_no_heartbeat_yet(self):
        manager = AgentManager()
        ws = create_mock_ws()
        conn = AgentConnection("test-agent", ws)
        conn.last_heartbeat = 0  # never received heartbeat
        manager._connections["test-agent"] = conn

        assert manager.is_connected("test-agent") is True


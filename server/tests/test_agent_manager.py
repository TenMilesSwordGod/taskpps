from __future__ import annotations

import asyncio
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from taskpps.services.agent_manager import (
    AgentConnection,
    AgentManager,
    DISPLAY_GRACE_PERIOD,
    HEARTBEAT_TIMEOUT,
)


def create_mock_ws():
    ws = AsyncMock()
    ws.receive_json = AsyncMock()
    ws.send_json = AsyncMock()
    ws.close = AsyncMock()
    return ws


class TestAgentManager:
    @pytest.mark.asyncio
    async def test_is_connected_uses_display_grace_period(self):
        manager = AgentManager()
        ws = create_mock_ws()
        conn = AgentConnection("test-agent", ws)
        conn.last_heartbeat = time.time() - DISPLAY_GRACE_PERIOD + 10
        manager._connections["test-agent"] = conn

        assert manager.is_connected("test-agent") is True

    @pytest.mark.asyncio
    async def test_is_connected_false_after_grace_period(self):
        manager = AgentManager()
        ws = create_mock_ws()
        conn = AgentConnection("test-agent", ws)
        conn.last_heartbeat = time.time() - DISPLAY_GRACE_PERIOD - 10
        manager._connections["test-agent"] = conn

        assert manager.is_connected("test-agent") is False

    @pytest.mark.asyncio
    async def test_is_connected_nonexistent(self):
        manager = AgentManager()
        assert manager.is_connected("nonexistent") is False

    @pytest.mark.asyncio
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
    async def test_disconnect_with_matching_conn(self):
        manager = AgentManager()
        ws = create_mock_ws()
        conn = AgentConnection("agent-1", ws)
        manager._connections["agent-1"] = conn

        await manager.disconnect("agent-1", conn)

        assert manager.get_connection("agent-1") is None

    @pytest.mark.asyncio
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
    async def test_disconnect_without_conn_always_removes(self):
        manager = AgentManager()
        ws = create_mock_ws()
        conn = AgentConnection("agent-1", ws)
        manager._connections["agent-1"] = conn

        await manager.disconnect("agent-1")

        assert manager.get_connection("agent-1") is None

    @pytest.mark.asyncio
    async def test_disconnect_cleans_up_pending_commands(self):
        manager = AgentManager()
        ws = create_mock_ws()
        conn = AgentConnection("agent-1", ws)
        fut = conn.register_pending("cmd-1")
        manager._connections["agent-1"] = conn

        await manager.disconnect("agent-1", conn)

        assert fut.done()
        result = fut.result()
        assert result["exit_code"] == -1
        assert result["error"] == "connection lost"

    @pytest.mark.asyncio
    async def test_reconnect_race_condition(self):
        """模拟重连竞态：旧 handler 的 disconnect 不应移除新连接"""
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

    def test_get_connection(self):
        manager = AgentManager()
        ws = create_mock_ws()
        conn = AgentConnection("agent-1", ws)
        manager._connections["agent-1"] = conn

        assert manager.get_connection("agent-1") is conn
        assert manager.get_connection("nonexistent") is None

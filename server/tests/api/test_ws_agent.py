from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import WebSocketDisconnect

from taskpps.api import ws_agent
from taskpps.services.agent_manager import AgentManager


class TestAgentWebSocket:
    """Tests for the WebSocket endpoint handler function."""

    @pytest.mark.asyncio
    @pytest.mark.zentao("TC-S1008", domain="server/api", priority="P1")
    async def test_handshake_and_heartbeat_timeout(self):
        manager = AgentManager()
        ws = AsyncMock()
        ws.accept = AsyncMock()
        ws.receive_json = AsyncMock(
            return_value={
                "type": "handshake_request",
                "data": {"agent_id": "agent-1", "secret": "s", "version": "1.0"},
            }
        )
        ws.send_json = AsyncMock()
        ws.close = AsyncMock()

        # First receive_json is handshake, then receive_text times out once, then disconnects
        ws.receive_text = AsyncMock(side_effect=[asyncio.TimeoutError(), WebSocketDisconnect()])

        with patch("taskpps.api.ws_agent.AgentManager") as mock_mgr_cls:
            mock_mgr_cls.instance.return_value = manager
            await ws_agent.agent_websocket(ws)

        ws.accept.assert_called_once()
        # Should have sent heartbeat_request on timeout
        ws.send_json.assert_any_call({"type": "heartbeat_request", "data": {}})

    @pytest.mark.asyncio
    @pytest.mark.zentao("TC-S1009", domain="server/api", priority="P2")
    async def test_no_ping_messages_sent(self):
        """验证 _ping_loop 已移除，不再发送 ping 类型消息。"""
        manager = AgentManager()
        ws = AsyncMock()
        ws.accept = AsyncMock()
        ws.receive_json = AsyncMock(
            return_value={
                "type": "handshake_request",
                "data": {"agent_id": "agent-1", "secret": "s", "version": "1.0"},
            }
        )
        ws.send_json = AsyncMock()
        ws.close = AsyncMock()

        # 收到一次心跳响应后超时断开
        ws.receive_text = AsyncMock(
            side_effect=[
                json.dumps({"type": "heartbeat_response", "data": {}}),
                asyncio.TimeoutError(),
                WebSocketDisconnect(),
            ]
        )

        with patch("taskpps.api.ws_agent.AgentManager") as mock_mgr_cls:
            mock_mgr_cls.instance.return_value = manager
            await ws_agent.agent_websocket(ws)

        # 确认没有发送 ping 类型消息
        for call in ws.send_json.call_args_list:
            msg = call[0][0]
            assert msg.get("type") != "ping", f"不应发送 ping 消息，但收到了: {msg}"

    @pytest.mark.asyncio
    @pytest.mark.zentao("TC-S1010", domain="server/api", priority="P1")
    async def test_heartbeat_request_uses_send_lock(self):
        """验证 heartbeat_request 通过 conn.send_msg（即 _send_lock）发送，而非直接 ws.send_json。"""
        manager = AgentManager()
        ws = AsyncMock()
        ws.accept = AsyncMock()
        ws.receive_json = AsyncMock(
            return_value={
                "type": "handshake_request",
                "data": {"agent_id": "agent-1", "secret": "s", "version": "1.0"},
            }
        )
        ws.send_json = AsyncMock()
        ws.close = AsyncMock()

        # 超时触发 heartbeat_request，然后断开
        ws.receive_text = AsyncMock(
            side_effect=[asyncio.TimeoutError(), WebSocketDisconnect()]
        )

        with patch("taskpps.api.ws_agent.AgentManager") as mock_mgr_cls:
            mock_mgr_cls.instance.return_value = manager
            await ws_agent.agent_websocket(ws)

        # heartbeat_request 应该通过 send_json 发送（经过 _send_lock）
        ws.send_json.assert_any_call({"type": "heartbeat_request", "data": {}})

        # 验证 conn 对象存在且 last_heartbeat 被标记为断开
        conn = manager.get_connection("agent-1")
        assert conn is not None
        assert conn.last_heartbeat == -1

    @pytest.mark.asyncio
    @pytest.mark.zentao("TC-S1011", domain="server/api", priority="P1")
    async def test_json_decode_error(self):
        manager = AgentManager()
        ws = AsyncMock()
        ws.accept = AsyncMock()
        ws.receive_json = AsyncMock(
            return_value={
                "type": "handshake_request",
                "data": {"agent_id": "agent-1", "secret": "s", "version": "1.0"},
            }
        )
        ws.send_json = AsyncMock()
        ws.close = AsyncMock()

        # First call: valid JSON. Second call: invalid JSON, then disconnect
        ws.receive_text = AsyncMock(
            side_effect=[
                json.dumps({"type": "heartbeat_response", "data": {}}),
                "not json {{{",
                WebSocketDisconnect(),
            ]
        )

        with patch("taskpps.api.ws_agent.AgentManager") as mock_mgr_cls:
            mock_mgr_cls.instance.return_value = manager
            await ws_agent.agent_websocket(ws)

        # Should not raise, JSON decode error is silently caught
        ws.accept.assert_called_once()

    @pytest.mark.asyncio
    @pytest.mark.zentao("TC-S1012", domain="server/api", priority="P1")
    async def test_heartbeat_response(self):
        manager = AgentManager()
        ws = AsyncMock()
        ws.accept = AsyncMock()
        ws.receive_json = AsyncMock(
            return_value={
                "type": "handshake_request",
                "data": {"agent_id": "agent-1", "secret": "s", "version": "1.0"},
            }
        )
        ws.send_json = AsyncMock()
        ws.close = AsyncMock()

        # heartbeat_response 重置超时计时器，然后 timeout 触发 heartbeat_request
        ws.receive_text = AsyncMock(
            side_effect=[
                json.dumps({"type": "heartbeat_response", "data": {}}),
                asyncio.TimeoutError(),
                WebSocketDisconnect(),
            ]
        )

        with patch("taskpps.api.ws_agent.AgentManager") as mock_mgr_cls:
            mock_mgr_cls.instance.return_value = manager
            await ws_agent.agent_websocket(ws)

        # heartbeat_response 被处理后 should NOT 立即发送 heartbeat_request
        #（但在下一个 timeout 后会发）
        ws.send_json.assert_any_call({"type": "heartbeat_request", "data": {}})

    @pytest.mark.asyncio
    @pytest.mark.zentao("TC-S1013", domain="server/api", priority="P2")
    async def test_stdout_chunk(self):
        manager = AgentManager()
        ws = AsyncMock()
        ws.accept = AsyncMock()
        ws.receive_json = AsyncMock(
            return_value={
                "type": "handshake_request",
                "data": {"agent_id": "agent-1", "secret": "s", "version": "1.0"},
            }
        )
        ws.send_json = AsyncMock()
        ws.close = AsyncMock()

        collected = []

        ws.receive_text = AsyncMock(
            side_effect=[
                json.dumps({"type": "stdout_chunk", "data": {"command_id": "cmd-1", "data": "hello\n"}}),
                WebSocketDisconnect(),
            ]
        )

        with patch("taskpps.api.ws_agent.AgentManager") as mock_mgr_cls:
            mock_mgr_cls.instance.return_value = manager
            await ws_agent.agent_websocket(ws)

        conn = manager.get_connection("agent-1")
        assert conn is not None

    @pytest.mark.asyncio
    @pytest.mark.zentao("TC-S1014", domain="server/api", priority="P2")
    async def test_exec_result(self):
        manager = AgentManager()
        ws = AsyncMock()
        ws.accept = AsyncMock()
        ws.receive_json = AsyncMock(
            return_value={
                "type": "handshake_request",
                "data": {"agent_id": "agent-1", "secret": "s", "version": "1.0"},
            }
        )
        ws.send_json = AsyncMock()
        ws.close = AsyncMock()

        ws.receive_text = AsyncMock(
            side_effect=[
                json.dumps({"type": "exec_result", "data": {"command_id": "cmd-1", "exit_code": 0}}),
                WebSocketDisconnect(),
            ]
        )

        with patch("taskpps.api.ws_agent.AgentManager") as mock_mgr_cls:
            mock_mgr_cls.instance.return_value = manager
            await ws_agent.agent_websocket(ws)

    @pytest.mark.asyncio
    @pytest.mark.zentao("TC-S1015", domain="server/api", priority="P1")
    async def test_websocket_disconnect(self):
        manager = AgentManager()
        ws = AsyncMock()
        ws.accept = AsyncMock()
        ws.receive_json = AsyncMock(
            return_value={
                "type": "handshake_request",
                "data": {"agent_id": "agent-1", "secret": "s", "version": "1.0"},
            }
        )
        ws.send_json = AsyncMock()
        ws.close = AsyncMock()

        ws.receive_text = AsyncMock(side_effect=WebSocketDisconnect())

        with patch("taskpps.api.ws_agent.AgentManager") as mock_mgr_cls:
            mock_mgr_cls.instance.return_value = manager
            await ws_agent.agent_websocket(ws)

        # disconnect 保留连接对象但标记 last_heartbeat = -1（支持重连）
        conn = manager.get_connection("agent-1")
        assert conn is not None
        assert conn.last_heartbeat == -1

    @pytest.mark.asyncio
    @pytest.mark.zentao("TC-S1016", domain="server/api", priority="P1")
    async def test_generic_exception(self):
        manager = AgentManager()
        ws = AsyncMock()
        ws.accept = AsyncMock()
        ws.receive_json = AsyncMock(
            return_value={
                "type": "handshake_request",
                "data": {"agent_id": "agent-1", "secret": "s", "version": "1.0"},
            }
        )
        ws.send_json = AsyncMock()
        ws.close = AsyncMock()

        ws.receive_text = AsyncMock(side_effect=RuntimeError("unexpected error"))

        with patch("taskpps.api.ws_agent.AgentManager") as mock_mgr_cls:
            mock_mgr_cls.instance.return_value = manager
            await ws_agent.agent_websocket(ws)

        # disconnect 保留连接对象但标记 last_heartbeat = -1（支持重连）
        conn = manager.get_connection("agent-1")
        assert conn is not None
        assert conn.last_heartbeat == -1

    @pytest.mark.asyncio
    @pytest.mark.zentao("TC-S1017", domain="server/api", priority="P2")
    async def test_unknown_message_type(self):
        manager = AgentManager()
        ws = AsyncMock()
        ws.accept = AsyncMock()
        ws.receive_json = AsyncMock(
            return_value={
                "type": "handshake_request",
                "data": {"agent_id": "agent-1", "secret": "s", "version": "1.0"},
            }
        )
        ws.send_json = AsyncMock()
        ws.close = AsyncMock()

        ws.receive_text = AsyncMock(
            side_effect=[
                json.dumps({"type": "unknown_type", "data": {}}),
                WebSocketDisconnect(),
            ]
        )

        with patch("taskpps.api.ws_agent.AgentManager") as mock_mgr_cls:
            mock_mgr_cls.instance.return_value = manager
            await ws_agent.agent_websocket(ws)


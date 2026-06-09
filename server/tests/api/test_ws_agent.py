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

        ws.receive_text = AsyncMock(
            side_effect=[
                json.dumps({"type": "heartbeat_response", "data": {}}),
                WebSocketDisconnect(),
            ]
        )

        with patch("taskpps.api.ws_agent.AgentManager") as mock_mgr_cls:
            mock_mgr_cls.instance.return_value = manager
            await ws_agent.agent_websocket(ws)

        conn = manager.get_connection("agent-1")
        assert conn is not None
        assert conn.last_heartbeat > 0

    @pytest.mark.asyncio
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

        # Should disconnect the agent
        assert manager.get_connection("agent-1") is None

    @pytest.mark.asyncio
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

        # Should disconnect the agent
        assert manager.get_connection("agent-1") is None

    @pytest.mark.asyncio
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

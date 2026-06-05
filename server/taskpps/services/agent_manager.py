from __future__ import annotations

import asyncio
import json
import logging
import uuid
from collections.abc import Callable

from fastapi import WebSocket

from taskpps.i18n import t

logger = logging.getLogger(__name__)

HEARTBEAT_INTERVAL = 15
HEARTBEAT_TIMEOUT = 45
HANDSHAKE_TIMEOUT = 10


class AgentConnection:
    def __init__(self, agent_id: str, ws: WebSocket):
        self.agent_id = agent_id
        self.ws = ws
        self.hostname = ""
        self.agent_version = ""
        self.agent_pid = 0
        self.connected_at = 0.0
        self.last_heartbeat = 0.0
        self._pending_commands: dict[str, "asyncio.Future[dict]"] = {}
        self._output_callbacks: dict[str, Callable] = {}
        self._send_lock = asyncio.Lock()

    async def send_msg(self, msg_type: str, data: dict) -> None:
        async with self._send_lock:
            await self.ws.send_json({"type": msg_type, "data": data})

    async def send_command(self, command_id: str, command: str, env: dict[str, str], cwd: str, timeout: int) -> None:
        await self.send_msg("exec_command", {
            "command_id": command_id,
            "command": command,
            "env": env,
            "cwd": cwd,
            "timeout": timeout,
        })

    async def send_cancel(self, command_id: str) -> None:
        await self.send_msg("cancel_command", {"command_id": command_id})

    def register_pending(self, command_id: str) -> "asyncio.Future[dict]":
        fut: asyncio.Future[dict] = asyncio.get_event_loop().create_future()
        self._pending_commands[command_id] = fut
        return fut

    def resolve_pending(self, command_id: str, result: dict) -> None:
        fut = self._pending_commands.pop(command_id, None)
        self._output_callbacks.pop(command_id, None)
        if fut and not fut.done():
            fut.set_result(result)

    def register_output_callback(self, command_id: str, callback: Callable) -> None:
        self._output_callbacks[command_id] = callback

    def handle_output(self, command_id: str, data: str) -> None:
        cb = self._output_callbacks.get(command_id)
        if cb:
            cb(data)

    def cleanup_command(self, command_id: str) -> None:
        fut = self._pending_commands.pop(command_id, None)
        self._output_callbacks.pop(command_id, None)
        if fut and not fut.done():
            fut.set_result({"exit_code": -1, "signal_name": "", "error": "connection lost"})


class AgentManager:
    _instance: "AgentManager | None" = None

    def __init__(self):
        self._connections: dict[str, AgentConnection] = {}
        self._active = True

    @classmethod
    def instance(cls) -> "AgentManager":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @property
    def connections(self) -> dict[str, AgentConnection]:
        return self._connections

    def is_connected(self, agent_id: str) -> bool:
        conn = self._connections.get(agent_id)
        if conn is None:
            return False
        age = asyncio.get_event_loop().time() - conn.last_heartbeat
        return age < HEARTBEAT_TIMEOUT

    async def handle_connection(self, ws: WebSocket, expected_agent_id: str | None = None) -> str:
        try:
            data = await asyncio.wait_for(ws.receive_json(), timeout=HANDSHAKE_TIMEOUT)
        except asyncio.TimeoutError:
            await ws.close(code=4001, reason="handshake timeout")
            raise

        msg_type = data.get("type", "")
        payload = data.get("data", {})

        if msg_type != "handshake_request":
            await ws.close(code=4002, reason="expected handshake_request")
            raise ValueError(t("Expected handshake_request, got {type}", type=msg_type))

        agent_id = payload.get("agent_id", "")
        secret = payload.get("secret", "")
        version = payload.get("version", "")

        if expected_agent_id and agent_id != expected_agent_id:
            await ws.close(code=4003, reason=f"agent_id mismatch: expected {expected_agent_id}")
            raise ValueError(f"agent_id mismatch: {agent_id} != {expected_agent_id}")

        import os
        hostname_info = payload.get("hostname", "") or ""
        agent_pid = payload.get("agent_pid", 0) or 0

        await ws.send_json({
            "type": "handshake_response",
            "data": {
                "agent_id": agent_id,
                "hostname": hostname_info,
                "agent_version": version,
                "agent_pid": agent_pid,
            },
        })

        loop = asyncio.get_event_loop()
        now = loop.time()

        conn = AgentConnection(agent_id, ws)
        conn.hostname = hostname_info
        conn.agent_version = version
        conn.agent_pid = agent_pid
        conn.connected_at = now
        conn.last_heartbeat = now

        old = self._connections.pop(agent_id, None)
        if old:
            for cid in list(old._pending_commands.keys()):
                old.cleanup_command(cid)

        self._connections[agent_id] = conn
        logger.info("Agent '%s' connected (hostname=%s, version=%s, pid=%d)", agent_id, hostname_info, version, agent_pid)
        return agent_id

    async def disconnect(self, agent_id: str) -> None:
        conn = self._connections.pop(agent_id, None)
        if conn:
            for cid in list(conn._pending_commands.keys()):
                conn.cleanup_command(cid)
            logger.info("Agent '%s' disconnected", agent_id)

    def get_connection(self, agent_id: str) -> AgentConnection | None:
        return self._connections.get(agent_id)

    async def send_command(self, agent_id: str, command_id: str,
                           command: str, env: dict[str, str], cwd: str, timeout: int) -> None:
        conn = self._connections.get(agent_id)
        if conn is None:
            raise RuntimeError(t("Agent '{agent_id}' not connected", agent_id=agent_id))
        await conn.send_command(command_id, command, env, cwd, timeout)

    async def cancel_command(self, agent_id: str, command_id: str) -> None:
        conn = self._connections.get(agent_id)
        if conn is None:
            return
        await conn.send_cancel(command_id)

    def create_pending(self, agent_id: str, command_id: str) -> "asyncio.Future[dict]":
        conn = self._connections.get(agent_id)
        if conn is None:
            fut: asyncio.Future[dict] = asyncio.get_event_loop().create_future()
            fut.set_result({"exit_code": -1, "signal_name": "", "error": "agent not connected"})
            return fut
        return conn.register_pending(command_id)

    def register_output_callback(self, agent_id: str, command_id: str, callback: Callable) -> None:
        conn = self._connections.get(agent_id)
        if conn:
            conn.register_output_callback(command_id, callback)

    async def stop(self) -> None:
        self._active = False
        for agent_id in list(self._connections.keys()):
            await self.disconnect(agent_id)

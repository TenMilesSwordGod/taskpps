from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import time

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from taskpps.services.agent_manager import AgentManager

logger = logging.getLogger(__name__)

router = APIRouter()


@router.websocket("/ws/agent")
async def agent_websocket(ws: WebSocket):
    await ws.accept()
    manager = AgentManager.instance()
    agent_id = None
    conn = None
    _ping_task: asyncio.Task | None = None

    async def _ping_loop() -> None:
        """发送 WebSocket 协议级 ping 帧，快速检测连接断开。"""
        try:
            while True:
                await asyncio.sleep(15)
                try:
                    await ws.send_json({"type": "ping", "data": {}})
                except Exception:
                    break
        except asyncio.CancelledError:
            pass

    try:
        agent_id, conn = await manager.handle_connection(ws)
        _ping_task = asyncio.create_task(_ping_loop())

        while True:
            try:
                raw = await asyncio.wait_for(ws.receive_text(), timeout=45)
            except asyncio.TimeoutError:
                await ws.send_json({"type": "heartbeat_request", "data": {}})
                continue

            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                continue

            msg_type = data.get("type", "")
            payload = data.get("data", {})

            if msg_type == "heartbeat_response":
                conn.last_heartbeat = time.time()

            elif msg_type == "stdout_chunk" or msg_type == "stderr_chunk":
                conn.handle_output(payload.get("command_id", ""), payload.get("data", ""))

            elif msg_type == "exec_result":
                conn.resolve_pending(payload.get("command_id", ""), payload)

    except WebSocketDisconnect:
        logger.info("Agent WebSocket disconnected")
    except Exception:
        logger.exception("Agent WebSocket error")
    finally:
        if _ping_task and not _ping_task.done():
            _ping_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await _ping_task
        if agent_id:
            await manager.disconnect(agent_id, conn)

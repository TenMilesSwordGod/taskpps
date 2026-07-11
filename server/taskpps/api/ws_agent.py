from __future__ import annotations

import asyncio
import json
import logging
import time

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from taskpps.services.agent_manager import HEARTBEAT_TIMEOUT, AgentManager

logger = logging.getLogger(__name__)

router = APIRouter()


@router.websocket("/ws/agent")
async def agent_websocket(ws: WebSocket):
    await ws.accept()
    manager = AgentManager.instance()
    agent_id = None
    conn = None

    try:
        agent_id, conn = await manager.handle_connection(ws)

        while True:
            try:
                raw = await asyncio.wait_for(ws.receive_text(), timeout=45)
            except asyncio.TimeoutError:
                now = time.time()
                # 检测心跳是否过期：如果发了心跳请求但没收到回复，关闭连接
                if conn._heartbeat_sent_at > 0 and (now - conn._heartbeat_sent_at) > HEARTBEAT_TIMEOUT:
                    logger.warning(
                        "Agent '%s' heartbeat timeout (%.0fs), closing connection",
                        agent_id, now - conn._heartbeat_sent_at,
                    )
                    await ws.close(code=4004, reason="heartbeat timeout")
                    break
                try:
                    await conn.send_msg("heartbeat_request", {})
                    conn._heartbeat_sent_at = now
                except Exception:
                    logger.warning("Agent '%s' heartbeat request send failed", agent_id)
                    break
                continue

            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                continue

            msg_type = data.get("type", "")
            payload = data.get("data", {})

            if msg_type == "heartbeat_response":
                conn.last_heartbeat = time.time()
                conn._heartbeat_sent_at = 0.0

            elif msg_type == "stdout_chunk" or msg_type == "stderr_chunk":
                conn.handle_output(payload.get("command_id", ""), payload.get("data", ""))

            elif msg_type == "exec_result":
                conn.resolve_pending(payload.get("command_id", ""), payload)

    except WebSocketDisconnect:
        logger.info("Agent WebSocket disconnected")
    except Exception:
        logger.exception("Agent WebSocket error")
    finally:
        if agent_id:
            await manager.disconnect(agent_id, conn)

from __future__ import annotations

import asyncio
import contextlib
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, field

from fastapi import WebSocket

from taskpps.i18n import t

logger = logging.getLogger(__name__)

HEARTBEAT_INTERVAL = 15
HEARTBEAT_TIMEOUT = 45
HANDSHAKE_TIMEOUT = 10
DISPLAY_GRACE_PERIOD = 300


@dataclass
class PendingCommandInfo:
    """正在执行的命令元数据"""
    command_id: str
    command: str = ""
    env: dict[str, str] = field(default_factory=dict)
    cwd: str = ""
    timeout: int = 0
    run_id: str = ""
    task_name: str = ""
    started_at: float = 0.0
    future: asyncio.Future[dict] = field(default_factory=lambda: asyncio.get_event_loop().create_future())


class AgentConnection:
    def __init__(self, agent_id: str, ws: WebSocket):
        self.agent_id = agent_id
        self.ws = ws
        self.hostname = ""
        self.platform = ""
        self.system = ""
        self.arch = ""
        self.ip = ""
        self.agent_version = ""
        self.agent_pid = 0
        self.connected_at = 0.0
        self.last_heartbeat = 0.0
        self._pending_commands: dict[str, PendingCommandInfo] = {}
        self._output_callbacks: dict[str, Callable] = {}
        self._send_lock = asyncio.Lock()

    async def send_msg(self, msg_type: str, data: dict) -> None:
        async with self._send_lock:
            await self.ws.send_json({"type": msg_type, "data": data})

    async def send_command(self, command_id: str, command: str, env: dict[str, str], cwd: str, timeout: int) -> None:
        await self.send_msg(
            "exec_command",
            {
                "command_id": command_id,
                "command": command,
                "env": env,
                "cwd": cwd,
                "timeout": timeout,
            },
        )

    async def send_cancel(self, command_id: str) -> None:
        await self.send_msg("cancel_command", {"command_id": command_id})

    def register_pending(
        self,
        command_id: str,
        command: str = "",
        env: dict[str, str] | None = None,
        cwd: str = "",
        timeout: int = 0,
        run_id: str = "",
        task_name: str = "",
    ) -> asyncio.Future[dict]:
        fut: asyncio.Future[dict] = asyncio.get_event_loop().create_future()
        self._pending_commands[command_id] = PendingCommandInfo(
            command_id=command_id,
            command=command,
            env=env or {},
            cwd=cwd,
            timeout=timeout,
            run_id=run_id,
            task_name=task_name,
            started_at=time.time(),
            future=fut,
        )
        return fut

    def resolve_pending(self, command_id: str, result: dict) -> None:
        info = self._pending_commands.pop(command_id, None)
        self._output_callbacks.pop(command_id, None)
        if info and not info.future.done():
            info.future.set_result(result)

    def register_output_callback(self, command_id: str, callback: Callable) -> None:
        self._output_callbacks[command_id] = callback

    def handle_output(self, command_id: str, data: str) -> None:
        cb = self._output_callbacks.get(command_id)
        if cb:
            cb(data)

    def cleanup_command(self, command_id: str) -> None:
        info = self._pending_commands.pop(command_id, None)
        self._output_callbacks.pop(command_id, None)
        if info and not info.future.done():
            info.future.set_result({"exit_code": -1, "signal_name": "", "error": "connection lost"})


class AgentManager:
    _instance: AgentManager | None = None

    def __init__(self):
        self._connections: dict[str, AgentConnection] = {}
        self._active = True
        # Issue #78: per-agent 信号量，限制并发命令数
        self._agent_semaphores: dict[str, asyncio.Semaphore] = {}

    @classmethod
    def instance(cls) -> AgentManager:
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
        if conn.last_heartbeat < 0:
            return False
        if conn.last_heartbeat <= 0:
            return True
        age = time.time() - conn.last_heartbeat
        return age < DISPLAY_GRACE_PERIOD

    async def handle_connection(
        self, ws: WebSocket, expected_agent_id: str | None = None
    ) -> tuple[str, AgentConnection]:
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
        _secret = payload.get("secret", "")
        version = payload.get("version", "")

        if expected_agent_id and agent_id != expected_agent_id:
            await ws.close(code=4003, reason=f"agent_id mismatch: expected {expected_agent_id}")
            raise ValueError(f"agent_id mismatch: {agent_id} != {expected_agent_id}")

        hostname_info = payload.get("hostname", "") or ""
        agent_pid = payload.get("agent_pid", 0) or 0
        os_name = payload.get("os", "") or ""
        arch_name = payload.get("arch", "") or ""

        await ws.send_json(
            {
                "type": "handshake_response",
                "data": {
                    "agent_id": agent_id,
                    "hostname": hostname_info,
                    "agent_version": version,
                    "agent_pid": agent_pid,
                },
            }
        )

        now = time.time()

        conn = AgentConnection(agent_id, ws)
        conn.hostname = hostname_info
        conn.system = os_name
        conn.arch = arch_name
        conn.platform = f"{os_name}/{arch_name}" if os_name or arch_name else ""
        conn.agent_version = version
        conn.agent_pid = agent_pid
        conn.connected_at = now
        conn.last_heartbeat = now
        # 提取客户端 IP（取代理链中第一个非 trust 头）
        try:
            client = ws.client
            if client and client.host:
                conn.ip = client.host
        except Exception:
            conn.ip = ""

        old = self._connections.pop(agent_id, None)
        if old:
            conn._pending_commands = old._pending_commands
            conn._output_callbacks = old._output_callbacks
            with contextlib.suppress(Exception):
                await old.ws.close(code=4000, reason="replaced by new connection")

        self._connections[agent_id] = conn
        logger.info(
            "Agent '%s' connected (hostname=%s, platform=%s, version=%s, pid=%d)",
            agent_id,
            hostname_info,
            conn.platform,
            version,
            agent_pid,
        )
        return agent_id, conn

    async def disconnect(self, agent_id: str, conn: AgentConnection | None = None) -> None:
        current = self._connections.get(agent_id)
        if conn is not None and current is not conn:
            return
        if current is None:
            return
        current.last_heartbeat = -1
        logger.info("Agent '%s' disconnected (pending commands preserved for reconnect)", agent_id)

        # 启动延迟清理任务：如果 agent 在 DISPLAY_GRACE_PERIOD 内未重连，
        # 清理残留的 pending commands 和 output callbacks，避免内存泄漏
        self._schedule_disconnect_cleanup(agent_id)

    def _schedule_disconnect_cleanup(self, agent_id: str) -> None:
        """安排断连 agent 的延迟清理任务。"""
        import asyncio

        async def _cleanup_after_grace():
            await asyncio.sleep(DISPLAY_GRACE_PERIOD)
            conn = self._connections.get(agent_id)
            # 如果 agent 已重连（last_heartbeat > 0），跳过清理
            if conn and conn.last_heartbeat > 0:
                return
            # 清理残留的 pending commands 和 output callbacks
            if conn:
                stale_commands = list(conn._pending_commands.keys())
                if stale_commands:
                    logger.warning(
                        "Agent '%s' did not reconnect within grace period, cleaning %d stale commands",
                        agent_id,
                        len(stale_commands),
                    )
                    for cid in stale_commands:
                        try:
                            conn.cleanup_command(cid)
                        except Exception:
                            logger.exception("Failed to cleanup command %s for agent '%s'", cid, agent_id)
                # 从 _connections 中移除，释放 WebSocket 引用
                self._connections.pop(agent_id, None)
                logger.info("Agent '%s' removed from connections after grace period", agent_id)

        try:
            asyncio.create_task(_cleanup_after_grace())
        except RuntimeError:
            pass  # 事件循环已关闭（服务器关闭期间）

    def get_connection(self, agent_id: str) -> AgentConnection | None:
        return self._connections.get(agent_id)

    # Issue #78: per-agent 并发控制
    async def acquire_agent(self, agent_id: str, max_parallel: int = 1, timeout: float = 300) -> None:
        """获取 agent 的执行槽位。如果 agent 已满，等待直到有空位或超时。

        Args:
            agent_id: agent 标识
            max_parallel: 最大并发命令数（来自 agent YAML 的 max_parallel）
            timeout: 等待超时（秒），0 表示不等待

        Raises:
            TimeoutError: 等待超时
        """
        if agent_id not in self._agent_semaphores:
            self._agent_semaphores[agent_id] = asyncio.Semaphore(max_parallel)
        sem = self._agent_semaphores[agent_id]
        if timeout <= 0:
            if not sem.locked() and sem._value > 0:
                # 快速路径：有可用槽位
                await sem.acquire()
                return
            raise TimeoutError(t("Agent '{agent}' is busy (max_parallel={max})", agent=agent_id, max=max_parallel))
        try:
            await asyncio.wait_for(sem.acquire(), timeout=timeout)
        except asyncio.TimeoutError:
            raise TimeoutError(t("Agent '{agent}' queue timeout ({timeout}s)", agent=agent_id, timeout=timeout))

    def release_agent(self, agent_id: str) -> None:
        """释放 agent 的执行槽位。"""
        sem = self._agent_semaphores.get(agent_id)
        if sem:
            sem.release()

    async def send_command(
        self, agent_id: str, command_id: str, command: str, env: dict[str, str], cwd: str, timeout: int
    ) -> None:
        conn = self._connections.get(agent_id)
        if conn is None:
            raise RuntimeError(t("Agent '{agent_id}' not connected", agent_id=agent_id))
        await conn.send_command(command_id, command, env, cwd, timeout)

    async def cancel_command(self, agent_id: str, command_id: str) -> None:
        conn = self._connections.get(agent_id)
        if conn is None:
            return
        await conn.send_cancel(command_id)

    def cleanup_command(self, agent_id: str, command_id: str) -> None:
        """Issue #66: 清理 pending command，避免 agent 永远显示 running。

        cancel_command 只发取消消息，不清理 _pending_commands。如果 agent
        断连/重启/结果丢失，pending command 永久残留，running_commands 计数
        永不归零。超时/取消/发送失败路径必须调用此方法。
        """
        conn = self._connections.get(agent_id)
        if conn is None:
            return
        conn.cleanup_command(command_id)

    def create_pending(
        self,
        agent_id: str,
        command_id: str,
        command: str = "",
        env: dict[str, str] | None = None,
        cwd: str = "",
        timeout: int = 0,
        run_id: str = "",
        task_name: str = "",
    ) -> asyncio.Future[dict]:
        conn = self._connections.get(agent_id)
        if conn is None:
            fut: asyncio.Future[dict] = asyncio.get_event_loop().create_future()
            fut.set_result({"exit_code": -1, "signal_name": "", "error": "agent not connected"})
            return fut
        return conn.register_pending(command_id, command, env, cwd, timeout, run_id, task_name)

    def register_output_callback(self, agent_id: str, command_id: str, callback: Callable) -> None:
        conn = self._connections.get(agent_id)
        if conn:
            conn.register_output_callback(command_id, callback)

    async def stop(self) -> None:
        self._active = False
        # On server shutdown there is no chance of an agent reconnecting,
        # so we must actually drop the connections and fail any in-flight
        # pending commands instead of leaving them dangling for a safety-net
        # timeout to catch.
        for agent_id in list(self._connections.keys()):
            conn = self._connections.pop(agent_id, None)
            if conn is None:
                continue
            for cid in list(conn._pending_commands.keys()):
                conn.cleanup_command(cid)

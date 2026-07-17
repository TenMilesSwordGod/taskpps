from __future__ import annotations

import asyncio
import logging
import uuid
from pathlib import Path

from taskpps.config import get_settings
from taskpps.executors.base import BaseExecutor, ExecutorResult
from taskpps.services.agent_manager import AgentManager

logger = logging.getLogger(__name__)


def _write_log_chunk(log_path: Path, data: str) -> None:
    """Append a single chunk to the task log file.

    Called from a thread pool by ``AgentExecutor.execute``'s ``on_output``
    callback so the WebSocket handler's event loop is never blocked on
    file I/O (see issue #16 for the deadlock this avoids).
    """
    try:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with open(log_path, "a", encoding="utf-8", errors="replace") as f:
            f.write(data)
            f.flush()
    except Exception:
        pass


class AgentExecutor(BaseExecutor):
    def __init__(self, agent_id: str, manager: AgentManager, agent_data: dict | None = None):
        self._agent_id = agent_id
        self._manager = manager
        self._agent_data = agent_data
        self._command_id: str | None = None
        self._cancelled = False
        self._bootstrapped = False
        self._slot_acquired = False
        self.run_id: str = ""
        self.task_name: str = ""

    async def _ensure_connected(self, log_path: Path) -> bool:
        if self._manager.is_connected(self._agent_id):
            return True

        # Issue #78: agent 断连时等待重连，而非直接失败
        settings = get_settings()
        offline_timeout = settings.executor.agent_offline_timeout

        if offline_timeout <= 0:
            if not self._agent_data or not self._agent_data.get("agent_auto_bootstrap", True):
                self._log(log_path, f"[ERROR] Agent '{self._agent_id}' not connected\n")
                return False
            return await self._try_bootstrap(log_path)

        self._log(
            log_path,
            f"[INFO] Agent '{self._agent_id}' not connected, waiting up to {offline_timeout}s for reconnect...\n",
        )
        deadline = asyncio.get_event_loop().time() + offline_timeout
        poll_interval = 5

        while asyncio.get_event_loop().time() < deadline:
            remaining = deadline - asyncio.get_event_loop().time()
            if remaining <= 0:
                break
            wait = min(poll_interval, remaining)
            await asyncio.sleep(wait)

            if self._manager.is_connected(self._agent_id):
                self._log(log_path, f"[INFO] Agent '{self._agent_id}' reconnected\n")
                return True

        # 等待超时后尝试 bootstrap
        if self._agent_data and self._agent_data.get("agent_auto_bootstrap", True):
            self._log(log_path, f"[INFO] Agent '{self._agent_id}' did not reconnect, attempting bootstrap...\n")
            return await self._try_bootstrap(log_path)

        self._log(log_path, f"[ERROR] Agent '{self._agent_id}' offline timeout ({offline_timeout}s)\n")
        return False

    async def _try_bootstrap(self, log_path: Path) -> bool:
        self._log(log_path, f"[INFO] Agent '{self._agent_id}' not connected, bootstrapping...\n")
        try:
            from taskpps.services.agent_bootstrap import AgentBootstrap

            bootstrap = AgentBootstrap()
            result = await bootstrap.bootstrap(self._agent_id)
            self._log(log_path, f"[INFO] Agent bootstrap result: {result}\n")
            return result.get("success", False)
        except Exception as e:
            self._log(log_path, f"[ERROR] Agent bootstrap failed: {e}\n")
            return False

    async def execute(
        self,
        command: str,
        env: dict[str, str],
        log_path: Path,
        timeout: int | None = None,
        cwd: str | None = None,
    ) -> ExecutorResult:
        self._cancelled = False
        command_id = str(uuid.uuid4())
        self._command_id = command_id

        if not await self._ensure_connected(log_path):
            return ExecutorResult(
                exit_code=-1,
                stderr=f"Agent '{self._agent_id}' is not connected",
            )

        # Issue #103: 在排队前先注册为 queued，便于 UI 展示等待中的任务
        self._manager.create_pending(
            self._agent_id,
            command_id,
            command=command,
            env=env,
            cwd=cwd or "",
            timeout=timeout or 0,
            run_id=self.run_id,
            task_name=self.task_name,
            status="queued",
        )

        # Issue #78: 获取 agent 执行槽位，排队等待
        max_parallel = (self._agent_data or {}).get("max_parallel", 1)
        queue_timeout = get_settings().executor.agent_queue_timeout

        # Issue #106: 获取全局并发槽位
        global_acquired = False
        try:
            await self._manager.acquire_global(queue_timeout)
            global_acquired = True
        except TimeoutError as e:
            self._log(log_path, f"[ERROR] Global concurrency limit reached: {e}\n")
            self._manager.cleanup_command(self._agent_id, command_id)
            return ExecutorResult(exit_code=-1, stderr=str(e))

        try:
            await self._manager.acquire_agent(self._agent_id, max_parallel, queue_timeout)
            self._slot_acquired = True
        except TimeoutError as e:
            self._log(log_path, f"[ERROR] Agent slot acquisition failed: {e}\n")
            self._manager.cleanup_command(self._agent_id, command_id)
            if global_acquired:
                self._manager.release_global()
                global_acquired = False
            return ExecutorResult(exit_code=-1, stderr=str(e))

        # 获得槽位后提升为 running
        self._manager.promote_command_to_running(self._agent_id, command_id)

        try:
            return await self._execute_command(command, env, log_path, timeout, cwd, command_id)
        finally:
            if self._slot_acquired:
                self._manager.release_agent(self._agent_id)
                self._slot_acquired = False
            if global_acquired:
                self._manager.release_global()

    async def _execute_command(
        self,
        command: str,
        env: dict[str, str],
        log_path: Path,
        timeout: int | None,
        cwd: str | None,
        command_id: str,
    ) -> ExecutorResult:
        effective_timeout = timeout or get_settings().executor.default_timeout
        if cwd:
            effective_cwd = cwd
        elif self._agent_data and self._agent_data.get("agent_work_dir"):
            effective_cwd = self._agent_data["agent_work_dir"]
        else:
            effective_cwd = ""

        self._log(log_path, f"[INFO] AgentExecutor: agent={self._agent_id} command_id={command_id}\n")
        self._log(log_path, f"[INFO] Command: {command[:500]}\n")
        self._log(log_path, f"[INFO] Timeout: {effective_timeout}s\n")
        self._log(log_path, f"[INFO] CWD: {effective_cwd}\n")

        output_lines: list[str] = []

        def on_output(data: str):
            output_lines.append(data)
            try:
                loop = asyncio.get_running_loop()
                loop.run_in_executor(None, _write_log_chunk, log_path, data)
            except RuntimeError:
                _write_log_chunk(log_path, data)

        self._manager.register_output_callback(self._agent_id, command_id, on_output)

        # Issue #103: 优先复用 execute() 中预先注册的 queued command，避免覆盖状态
        conn = self._manager.get_connection(self._agent_id)
        info = conn._pending_commands.get(command_id) if conn else None
        if info is not None:
            info.command = command
            info.cwd = effective_cwd
            info.timeout = effective_timeout
            fut = info.future
        else:
            fut = self._manager.create_pending(
                self._agent_id,
                command_id,
                command=command,
                env=env,
                cwd=effective_cwd,
                timeout=effective_timeout,
                run_id=self.run_id,
                task_name=self.task_name,
                status="running",
            )

        try:
            await self._manager.send_command(self._agent_id, command_id, command, env, effective_cwd, effective_timeout)
        except Exception as e:
            logger.exception("Failed to send command to agent '%s'", self._agent_id)
            self._manager.cleanup_command(self._agent_id, command_id)
            return ExecutorResult(exit_code=-1, stderr=str(e))

        try:
            result = await asyncio.wait_for(fut, timeout=effective_timeout + 10)
        except asyncio.TimeoutError:
            self._log(log_path, f"[ERROR] Task exceeded timeout of {effective_timeout}s\n")
            await self._manager.cancel_command(self._agent_id, command_id)
            self._manager.cleanup_command(self._agent_id, command_id)
            return ExecutorResult(exit_code=-1, stdout="".join(output_lines))
        except asyncio.CancelledError:
            self._log(log_path, "[WARN] Task was cancelled\n")
            await self._manager.cancel_command(self._agent_id, command_id)
            self._manager.cleanup_command(self._agent_id, command_id)
            return ExecutorResult(exit_code=-1, stdout="".join(output_lines))

        exit_code = result.get("exit_code", -1)
        signal_name = result.get("signal_name", "")
        error = result.get("error", "")

        # v2 (2026-07): 判断是否为基础设施故障（connection lost）。
        # 基础设施故障意味着 agent 连接断开而非任务本身逻辑失败，
        # 后续 task 同样会因为连接断开而无法执行，必须 block（Issue #202）。
        is_infra_failure = error == "connection lost"

        self._log(log_path, f"[INFO] Exit code: {exit_code}\n")
        if signal_name:
            self._log(log_path, f"[ERROR] Process killed by {signal_name} (exit_code={exit_code})\n")
        if error:
            self._log(log_path, f"[ERROR] {error}\n")

        return ExecutorResult(
            exit_code=exit_code,
            stdout="".join(output_lines),
            stderr=error,
            is_infrastructure_failure=is_infra_failure,
        )

    async def cancel(self) -> None:
        self._cancelled = True
        if self._command_id:
            await self._manager.cancel_command(self._agent_id, self._command_id)
            self._manager.cleanup_command(self._agent_id, self._command_id)

    def cleanup(self) -> None:
        """清理 executor 注册的 output callback，防止内存泄漏。

        当 executor 被外部取消（如 CancelledError 传播）时，execute() 的
        try/except 不会执行，on_output callback 残留在 AgentConnection 中。
        调用方应在 finally 块中调用此方法。
        """
        if self._command_id:
            conn = self._manager.get_connection(self._agent_id)
            if conn:
                conn._output_callbacks.pop(self._command_id, None)
        # Issue #78: 确保信号量被释放
        if self._slot_acquired:
            self._manager.release_agent(self._agent_id)
            self._slot_acquired = False

    def _log(self, log_path: Path, message: str) -> None:
        try:
            log_path.parent.mkdir(parents=True, exist_ok=True)
            with open(log_path, "a", encoding="utf-8", errors="replace") as f:
                f.write(message)
                f.flush()
        except Exception:
            pass

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
        self.run_id: str = ""
        self.task_name: str = ""

    async def _ensure_connected(self, log_path: Path) -> bool:
        if self._manager.is_connected(self._agent_id):
            return True

        if not self._agent_data or not self._agent_data.get("agent_auto_bootstrap", True):
            self._log(log_path, f"[ERROR] Agent '{self._agent_id}' not connected\n")
            return False

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
            # 文件 I/O 必须在事件循环外执行。原因：readPipeBinary 读取子
            # 进程 stdout/stderr 的管道后会通过 WebSocket 把每一行推上来；
            # 如果 on_output 在事件循环里同步 open+write+flush+close，
            # 单条卡顿就会让整个 WebSocket handler 不能继续读消息，agent
            # 的 sendMsg 反压、streamOutput 回调卡住、channel 写满、管道
            # 没法被排空 → 子进程 write 阻塞 → 任务看起来"卡住"，超时前
            # exec_result 永远到不了 (issue #16)。
            try:
                loop = asyncio.get_running_loop()
                loop.run_in_executor(None, _write_log_chunk, log_path, data)
            except RuntimeError:
                _write_log_chunk(log_path, data)

        self._manager.register_output_callback(self._agent_id, command_id, on_output)

        fut = self._manager.create_pending(
            self._agent_id, command_id,
            command=command, env=env, cwd=effective_cwd, timeout=effective_timeout,
            run_id=self.run_id, task_name=self.task_name,
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

        self._log(log_path, f"[INFO] Exit code: {exit_code}\n")
        if signal_name:
            self._log(log_path, f"[ERROR] Process killed by {signal_name} (exit_code={exit_code})\n")
        if error:
            self._log(log_path, f"[ERROR] {error}\n")

        return ExecutorResult(
            exit_code=exit_code,
            stdout="".join(output_lines),
            stderr=error,
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

    def _log(self, log_path: Path, message: str) -> None:
        try:
            log_path.parent.mkdir(parents=True, exist_ok=True)
            with open(log_path, "a", encoding="utf-8", errors="replace") as f:
                f.write(message)
                f.flush()
        except Exception:
            pass

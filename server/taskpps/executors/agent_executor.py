from __future__ import annotations

import asyncio
import logging
import os
import uuid
from pathlib import Path

from taskpps.config import get_settings
from taskpps.executors.base import BaseExecutor, ExecutorResult
from taskpps.services.agent_manager import AgentManager

logger = logging.getLogger(__name__)


class AgentExecutor(BaseExecutor):
    def __init__(self, agent_id: str, manager: AgentManager):
        self._agent_id = agent_id
        self._manager = manager
        self._command_id: str | None = None
        self._cancelled = False

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

        effective_timeout = timeout or get_settings().executor.default_timeout
        effective_cwd = cwd or os.getcwd()

        self._log(log_path, f"[INFO] AgentExecutor: agent={self._agent_id} command_id={command_id}\n")
        self._log(log_path, f"[INFO] Command: {command[:500]}\n")
        self._log(log_path, f"[INFO] Timeout: {effective_timeout}s\n")
        self._log(log_path, f"[INFO] CWD: {effective_cwd}\n")

        output_lines: list[str] = []

        def on_output(data: str):
            output_lines.append(data)
            with open(log_path, "a") as f:
                f.write(data)
                f.flush()

        self._manager.register_output_callback(self._agent_id, command_id, on_output)

        fut = self._manager.create_pending(self._agent_id, command_id)

        try:
            await self._manager.send_command(
                self._agent_id, command_id, command, env, effective_cwd, effective_timeout
            )
        except Exception as e:
            logger.exception("Failed to send command to agent '%s'", self._agent_id)
            return ExecutorResult(exit_code=-1, stderr=str(e))

        try:
            result = await asyncio.wait_for(fut, timeout=effective_timeout + 10)
        except asyncio.TimeoutError:
            self._log(log_path, f"[ERROR] Task exceeded timeout of {effective_timeout}s\n")
            await self._manager.cancel_command(self._agent_id, command_id)
            return ExecutorResult(exit_code=-1, stdout="".join(output_lines))
        except asyncio.CancelledError:
            self._log(log_path, "[WARN] Task was cancelled\n")
            await self._manager.cancel_command(self._agent_id, command_id)
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

    def _log(self, log_path: Path, message: str) -> None:
        try:
            log_path.parent.mkdir(parents=True, exist_ok=True)
            with open(log_path, "a") as f:
                f.write(message)
                f.flush()
        except Exception:
            pass

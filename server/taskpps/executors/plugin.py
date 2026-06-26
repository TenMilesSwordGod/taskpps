from __future__ import annotations

import asyncio
import contextlib
import logging
from pathlib import Path

from taskpps.executors.base import BaseExecutor, ExecutorResult

logger = logging.getLogger(__name__)


class PluginExecutor(BaseExecutor):
    def __init__(self, command: str, delegate: BaseExecutor | None = None):
        self._command = command
        self._delegate = delegate
        self._process: asyncio.subprocess.Process | None = None

    async def execute(
        self,
        command: str,
        env: dict[str, str],
        log_path: Path,
        timeout: int | None = None,
        cwd: str | None = None,
    ) -> ExecutorResult:
        if self._delegate is not None:
            return await self._delegate.execute(
                command=self._command,
                env=env,
                log_path=log_path,
                timeout=timeout,
                cwd=cwd,
            )

        from taskpps.executors.local import LocalExecutor

        executor = LocalExecutor()
        return await executor.execute(
            command=self._command,
            env=env,
            log_path=log_path,
            timeout=timeout,
            cwd=cwd,
        )

    async def cancel(self) -> None:
        if self._delegate is not None:
            await self._delegate.cancel()
            return
        if self._process is not None and self._process.returncode is None:
            with contextlib.suppress(ProcessLookupError):
                self._process.kill()
            await self._process.wait()
        self._process = None

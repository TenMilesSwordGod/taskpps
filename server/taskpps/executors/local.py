from __future__ import annotations

import asyncio
import os
import re
from pathlib import Path

from taskpps.config import get_settings
from taskpps.executors.base import BaseExecutor, ExecutorResult
from taskpps.i18n import t

_DANGEROUS_PATTERNS = re.compile(
    r"(\brm\s+-rf\s+/|"
    r":\(\)\{.*\}|"
    r"`.*`|"
    r"\$\(.*\)|"
    r"\bdd\s+.*\bof=/dev/|"
    r"\bmkfs\b|"
    r"\bchmod\s+-R\s+777\s+/|"
    r"\bshutdown\b|\breboot\b|\bhalt\b|\bpoweroff\b|"
    r"(?:wget|curl)\s+\S+\s*\|\s*(?:bash|sh)\b)",
    re.DOTALL,
)


class LocalExecutor(BaseExecutor):
    def __init__(self):
        self._process: asyncio.subprocess.Process | None = None
        self._cancelled = False

    async def execute(
        self,
        command: str,
        env: dict[str, str],
        log_path: Path,
        timeout: int | None = None,
        cwd: str | None = None,
    ) -> ExecutorResult:
        self._ensure_log_dir(log_path)
        self._cancelled = False

        if _DANGEROUS_PATTERNS.search(command):
            return ExecutorResult(exit_code=1, stderr=t("Command contains dangerous pattern"))

        merged_env = {**os.environ, **env}

        # Use shell from config
        shell = get_settings().executor.shell
        self._process = await asyncio.create_subprocess_exec(
            shell,
            "-c",
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            env=merged_env,
            cwd=cwd,
        )

        output_lines = []

        async def _read_and_write():
            while True:
                line = await self._process.stdout.readline()
                if not line:
                    break
                decoded = line.decode("utf-8", errors="replace")
                output_lines.append(decoded)
                with open(log_path, "a") as f:
                    f.write(decoded)

        try:
            read_task = asyncio.create_task(_read_and_write())
            if timeout is not None:
                await asyncio.wait_for(self._process.wait(), timeout=timeout)
            else:
                await self._process.wait()
            await read_task
            exit_code = self._process.returncode
        except asyncio.TimeoutError:
            self._process.kill()
            await self._process.wait()
            msg = t("Task exceeded timeout of {timeout}s", timeout=timeout)
            output_lines.append(msg)
            with open(log_path, "a") as f:
                f.write(msg)
            return ExecutorResult(exit_code=-1, stdout="".join(output_lines))
        except asyncio.CancelledError:
            if self._process.returncode is None:
                self._process.kill()
                await self._process.wait()
            msg = t("Task was cancelled")
            output_lines.append(msg)
            with open(log_path, "a") as f:
                f.write(msg)
            return ExecutorResult(exit_code=-1, stdout="".join(output_lines))
        finally:
            self._process = None

        return ExecutorResult(
            exit_code=exit_code if exit_code is not None else -1,
            stdout="".join(output_lines),
        )

    async def cancel(self) -> None:
        self._cancelled = True
        if self._process and self._process.returncode is None:
            self._process.kill()

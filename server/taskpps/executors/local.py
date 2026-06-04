from __future__ import annotations

import asyncio
import os
import re
import signal
from datetime import datetime, timezone
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
            error_msg = t("Command contains dangerous pattern")
            self._write_log(log_path, f"[ERROR] {error_msg}\n[ERROR] Command: {command[:200]}\n")
            return ExecutorResult(exit_code=1, stderr=error_msg)

        merged_env = {**os.environ, **env}

        shell = get_settings().executor.shell
        
        self._write_log(log_path, f"[INFO] {datetime.now(timezone.utc).isoformat()} Starting command execution\n")
        self._write_log(log_path, f"[INFO] Shell: {shell}\n")
        self._write_log(log_path, f"[INFO] Working Directory: {cwd or os.getcwd()}\n")
        self._write_log(log_path, f"[INFO] Timeout: {timeout or 'none'}s\n")
        if env:
            self._write_log(log_path, f"[INFO] Environment Variables: {list(env.keys())}\n")
        
        try:
            self._process = await asyncio.create_subprocess_exec(
                shell,
                "-c",
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
                env=merged_env,
                cwd=cwd,
                preexec_fn=os.setsid,
            )
        except Exception as e:
            error_msg = f"Failed to create subprocess: {str(e)}"
            self._write_log(log_path, f"[ERROR] {error_msg}\n")
            return ExecutorResult(exit_code=1, stderr=error_msg)

        output_lines = []

        async def _read_and_write():
            try:
                while True:
                    line = await self._process.stdout.readline()
                    if not line:
                        break
                    decoded = line.decode("utf-8", errors="replace")
                    output_lines.append(decoded)
                    with open(log_path, "a") as f:
                        f.write(decoded)
            except Exception as e:
                self._write_log(log_path, f"[ERROR] Error reading process output: {str(e)}\n")

        try:
            read_task = asyncio.create_task(_read_and_write())
            if timeout is not None and timeout > 0:
                try:
                    await asyncio.wait_for(self._process.wait(), timeout=timeout)
                except asyncio.TimeoutError:
                    self._write_log(log_path, f"[ERROR] Process timed out after {timeout}s\n")
                    try:
                        if self._process.returncode is None:
                            os.killpg(os.getpgid(self._process.pid), signal.SIGKILL)
                            await asyncio.wait_for(self._process.wait(), timeout=5)
                    except Exception as kill_err:
                        self._write_log(log_path, f"[ERROR] Failed to kill timed out process: {kill_err}\n")
                    
                    msg = t("Task exceeded timeout of {timeout}s", timeout=timeout)
                    output_lines.append(msg)
                    self._write_log(log_path, msg + "\n")
                    return ExecutorResult(exit_code=-1, stdout="".join(output_lines))
            else:
                await self._process.wait()
            
            await read_task
            exit_code = self._process.returncode
            
            self._write_log(log_path, f"[INFO] Process exited with code: {exit_code}\n")
            
            if exit_code is None:
                self._write_log(log_path, "[ERROR] Process did not complete properly (exit code is None)\n")
                return ExecutorResult(exit_code=-1, stdout="".join(output_lines))
                
        except asyncio.CancelledError:
            self._write_log(log_path, "[WARN] Task was cancelled\n")
            if self._process and self._process.returncode is None:
                try:
                    os.killpg(os.getpgid(self._process.pid), signal.SIGTERM)
                    await asyncio.wait_for(self._process.wait(), timeout=5)
                except Exception:
                    try:
                        os.killpg(os.getpgid(self._process.pid), signal.SIGKILL)
                        await self._process.wait()
                    except Exception:
                        pass
            msg = t("Task was cancelled")
            output_lines.append(msg)
            self._write_log(log_path, msg + "\n")
            return ExecutorResult(exit_code=-1, stdout="".join(output_lines))
        except Exception as e:
            error_msg = f"Unexpected execution error: {str(e)}"
            self._write_log(log_path, f"[ERROR] {error_msg}\n")
            return ExecutorResult(exit_code=1, stderr=error_msg)
        finally:
            self._process = None

        return ExecutorResult(
            exit_code=exit_code,
            stdout="".join(output_lines),
        )

    def _write_log(self, log_path: Path, message: str) -> None:
        """Write a message to the log file with proper error handling."""
        try:
            with open(log_path, "a") as f:
                f.write(message)
        except Exception as e:
            pass  # Ignore log write errors to avoid masking original errors

    async def cancel(self) -> None:
        self._cancelled = True
        if self._process and self._process.returncode is None:
            try:
                os.killpg(os.getpgid(self._process.pid), signal.SIGTERM)
            except Exception:
                pass

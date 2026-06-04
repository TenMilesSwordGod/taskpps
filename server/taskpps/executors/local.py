from __future__ import annotations

import asyncio
import logging
import os
import re
import signal
import sys
from datetime import datetime, timezone
from pathlib import Path

from taskpps.config import get_settings
from taskpps.executors.base import BaseExecutor, ExecutorResult
from taskpps.i18n import t

logger = logging.getLogger(__name__)

_EXECUTOR_VERSION = "v4-direct"

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


def _collect_descendants(pid: int) -> list[int]:
    descendants: list[int] = []
    try:
        for entry in os.scandir("/proc"):
            if not entry.name.isdigit():
                continue
            try:
                child_pid = int(entry.name)
                if child_pid == pid:
                    continue
                stat_path = f"/proc/{child_pid}/stat"
                with open(stat_path) as f:
                    stat = f.read()
                ppid = int(stat.split(") ")[1].split(" ")[1])
                if ppid == pid:
                    descendants.append(child_pid)
                    descendants.extend(_collect_descendants(child_pid))
            except (OSError, ValueError, IndexError):
                continue
    except OSError:
        pass
    return descendants


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

        self._log_direct(log_path, f"[VERSION] executor={_EXECUTOR_VERSION} "
                         f"python={sys.version.split()[0]} "
                         f"time={datetime.now(timezone.utc).isoformat()}\n")
        self._log_direct(log_path, f"[INFO] Command length: {len(command)} chars\n")
        self._log_direct(log_path, f"[INFO] Command: {command[:500]}\n")
        self._log_direct(log_path, f"[INFO] Timeout: {timeout}s\n")
        self._log_direct(log_path, f"[INFO] CWD: {cwd or os.getcwd()}\n")
        self._log_direct(log_path, f"[INFO] Env keys: {list(env.keys())}\n")

        if _DANGEROUS_PATTERNS.search(command):
            error_msg = t("Command contains dangerous pattern")
            self._log_direct(log_path, f"[ERROR] {error_msg}\n")
            return ExecutorResult(exit_code=1, stderr=error_msg)

        merged_env = {**os.environ, **env}
        merged_env["TASKPPS_EXECUTOR_VERSION"] = _EXECUTOR_VERSION

        shell = get_settings().executor.shell

        wrapped_command = f"trap '' HUP; {command}"

        self._log_direct(log_path, f"[INFO] Shell: {shell} -c <command>\n")
        try:
            self._process = await asyncio.create_subprocess_exec(
                shell,
                "-c",
                wrapped_command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
                env=merged_env,
                cwd=cwd,
            )
            self._log_direct(log_path, f"[INFO] Process started, PID: {self._process.pid}\n")
        except Exception as e:
            error_msg = f"Failed to create subprocess: {e}"
            self._log_direct(log_path, f"[ERROR] {error_msg}\n")
            return ExecutorResult(exit_code=1, stderr=error_msg)

        output_lines: list[str] = []

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
                        f.flush()
            except Exception:
                pass

        try:
            read_task = asyncio.create_task(_read_and_write())

            if timeout is not None and timeout > 0:
                deadline = asyncio.get_event_loop().time() + timeout
                while self._process.returncode is None:
                    if self._cancelled:
                        raise asyncio.CancelledError()
                    if asyncio.get_event_loop().time() >= deadline:
                        raise asyncio.TimeoutError()
                    await asyncio.sleep(0.1)
            else:
                while self._process.returncode is None:
                    if self._cancelled:
                        raise asyncio.CancelledError()
                    await asyncio.sleep(0.1)

            exit_code = self._process.returncode

        except asyncio.TimeoutError:
            self._log_direct(log_path,
                             f"[ERROR] Task exceeded timeout of {timeout}s\n")
            self._kill_process_tree(self._process.pid, signal.SIGKILL)
            try:
                await asyncio.wait_for(self._process.wait(), timeout=5)
            except Exception:
                pass
            msg = t("Task exceeded timeout of {timeout}s", timeout=timeout)
            output_lines.append(msg)
            self._log_direct(log_path, msg + "\n")
            return ExecutorResult(exit_code=-1, stdout="".join(output_lines))

        except asyncio.CancelledError:
            self._log_direct(log_path, "[WARN] Task was cancelled\n")
            if self._process.returncode is None:
                self._kill_process_tree(self._process.pid, signal.SIGTERM)
                try:
                    await asyncio.wait_for(self._process.wait(), timeout=5)
                except Exception:
                    self._kill_process_tree(self._process.pid, signal.SIGKILL)
                    try:
                        await self._process.wait()
                    except Exception:
                        pass
            msg = t("Task was cancelled")
            output_lines.append(msg)
            self._log_direct(log_path, msg + "\n")
            return ExecutorResult(exit_code=-1, stdout="".join(output_lines))

        finally:
            await read_task
            self._process = None

        self._log_direct(log_path, f"[INFO] Exit code: {exit_code}\n")
        return ExecutorResult(
            exit_code=exit_code if exit_code is not None else -1,
            stdout="".join(output_lines),
        )

    def _kill_process_tree(self, pid: int, sig: int) -> None:
        pids = [pid] + _collect_descendants(pid)
        for p in reversed(pids):
            try:
                os.kill(p, sig)
            except (ProcessLookupError, PermissionError, OSError):
                pass

    def _log_direct(self, log_path: Path, message: str) -> None:
        try:
            with open(log_path, "a") as f:
                f.write(message)
                f.flush()
        except Exception:
            pass

    @staticmethod
    def _ensure_log_dir(log_path: Path) -> None:
        log_path.parent.mkdir(parents=True, exist_ok=True)

    async def cancel(self) -> None:
        self._cancelled = True
        if self._process and self._process.returncode is None:
            self._kill_process_tree(self._process.pid, signal.SIGTERM)

from __future__ import annotations

import asyncio
import contextlib
import logging
import os
import re
import signal
import sys
from datetime import datetime, timezone
from pathlib import Path

from taskpps.config import get_data_dir, get_settings
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

        self._log_direct(
            log_path,
            f"[VERSION] executor={_EXECUTOR_VERSION} "
            f"python={sys.version.split()[0]} "
            f"time={datetime.now(timezone.utc).isoformat()}\n",
        )
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
        uv_cache_dir = get_data_dir() / "uv-cache"
        uv_cache_dir.mkdir(parents=True, exist_ok=True)
        merged_env.setdefault("UV_CACHE_DIR", str(uv_cache_dir))

        shell = get_settings().executor.shell

        wrapped_command = f"trap '' HUP; {command}"

        self._log_direct(log_path, f"[INFO] Shell: {shell} -c <command>\n")
        logger.info(
            "LocalExecutor: starting subprocess, shell=%s, timeout=%s, cwd=%s", shell, timeout, cwd or os.getcwd()
        )
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
            logger.info("LocalExecutor: subprocess started PID=%d", self._process.pid)
        except Exception as e:
            error_msg = f"Failed to create subprocess: {e}"
            self._log_direct(log_path, f"[ERROR] {error_msg}\n")
            logger.error("LocalExecutor: subprocess creation failed: %s", e)
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

            await self._process.wait()
            exit_code = -1 if self._cancelled else self._process.returncode
            logger.info(
                "LocalExecutor: process finished PID=%d exit_code=%s (cancelled=%s)",
                self._process.pid,
                exit_code,
                self._cancelled,
            )

        except asyncio.TimeoutError:
            self._log_direct(log_path, f"[ERROR] Task exceeded timeout of {timeout}s\n")
            logger.warning("LocalExecutor: timeout PID=%d after %ds", self._process.pid, timeout)
            self._kill_process_tree(self._process.pid, signal.SIGKILL)
            with contextlib.suppress(Exception):
                await asyncio.wait_for(self._process.wait(), timeout=5)
            msg = t("Task exceeded timeout of {timeout}s", timeout=timeout)
            output_lines.append(msg)
            self._log_direct(log_path, msg + "\n")
            return ExecutorResult(exit_code=-1, stdout="".join(output_lines))

        except asyncio.CancelledError:
            self._log_direct(log_path, "[WARN] Task was cancelled\n")
            logger.info("LocalExecutor: cancelled PID=%d returncode=%s", self._process.pid, self._process.returncode)
            if self._process.returncode is None:
                self._kill_process_tree(self._process.pid, signal.SIGTERM)
                try:
                    await asyncio.wait_for(self._process.wait(), timeout=5)
                except Exception:
                    self._kill_process_tree(self._process.pid, signal.SIGKILL)
                    logger.warning("LocalExecutor: SIGTERM failed, escalating to SIGKILL PID=%d", self._process.pid)
                    with contextlib.suppress(Exception):
                        await self._process.wait()
            msg = t("Task was cancelled")
            output_lines.append(msg)
            self._log_direct(log_path, msg + "\n")
            return ExecutorResult(exit_code=-1, stdout="".join(output_lines))

        except Exception as e:
            self._log_direct(log_path, f"[ERROR] Unexpected error in executor: {e}\n")
            logger.exception(
                "LocalExecutor: unexpected error in executor PID=%s", self._process.pid if self._process else "N/A"
            )
            if self._process is not None and self._process.returncode is None:
                try:
                    self._kill_process_tree(self._process.pid, signal.SIGKILL)
                    await asyncio.wait_for(self._process.wait(), timeout=5)
                except Exception:
                    pass
            return ExecutorResult(exit_code=1, stderr=str(e))

        finally:
            await read_task
            self._process = None

        if exit_code is None:
            self._log_direct(
                log_path, "[WARN] Process exited with no return code, assuming signal death (exit_code=-1)\n"
            )
            logger.warning("LocalExecutor: exit_code is None, assuming signal death")
            return ExecutorResult(exit_code=-1, stdout="".join(output_lines))

        if exit_code < 0:
            signal_num = -exit_code
            signal_names = {
                1: "SIGHUP",
                2: "SIGINT",
                3: "SIGQUIT",
                4: "SIGILL",
                6: "SIGABRT",
                8: "SIGFPE",
                9: "SIGKILL",
                11: "SIGSEGV",
                13: "SIGPIPE",
                14: "SIGALRM",
                15: "SIGTERM",
                17: "SIGCHLD",
            }
            sig_name = signal_names.get(signal_num, f"signal {signal_num}")
            self._log_direct(log_path, f"[ERROR] Process killed by {sig_name} (exit_code={exit_code})\n")
            logger.warning("LocalExecutor: process killed by %s exit_code=%d", sig_name, exit_code)

        self._log_direct(log_path, f"[INFO] Exit code: {exit_code}\n")
        return ExecutorResult(
            exit_code=exit_code,
            stdout="".join(output_lines),
        )

    def _kill_process_tree(self, pid: int, sig: int) -> None:
        pids = [pid, *_collect_descendants(pid)]
        for p in reversed(pids):
            with contextlib.suppress(ProcessLookupError, PermissionError, OSError):
                os.kill(p, sig)

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
        logger.info(
            "LocalExecutor.cancel: cancelled=True, process=%s returncode=%s",
            self._process.pid if self._process else "None",
            self._process.returncode if self._process else "N/A",
        )
        if self._process and self._process.returncode is None:
            self._kill_process_tree(self._process.pid, signal.SIGTERM)

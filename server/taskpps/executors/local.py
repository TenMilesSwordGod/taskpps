from __future__ import annotations

import asyncio
import base64
import logging
import os
import re
import signal
import sys
import traceback
import uuid
from datetime import datetime, timezone
from pathlib import Path

from taskpps.config import get_settings
from taskpps.executors.base import BaseExecutor, ExecutorResult
from taskpps.i18n import t

logger = logging.getLogger(__name__)

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

_WRAPPER_TEMPLATE = """\
#!/bin/bash
set -o pipefail

trap '' HUP

__taskpps_exit_code_file="{exit_code_file}"

__taskpps_cleanup() {{
    local rc=$?
    echo "$rc" > "$__taskpps_exit_code_file"
}}

trap __taskpps_cleanup EXIT

__taskpps_src=$(mktemp)
base64 -d <<< "{command_b64}" > "$__taskpps_src"
source "$__taskpps_src"
__taskpps_rc=$?
rm -f "$__taskpps_src"
exit $__taskpps_rc
"""


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
        self._exit_code_file: Path | None = None
        self._wrapper_script: Path | None = None

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

        print(
            f"[DEBUG-EXECUTOR] execute() called | log_path={log_path} | "
            f"command_len={len(command)} | timeout={timeout} | cwd={cwd}",
            file=sys.stderr,
            flush=True,
        )
        logger.debug(
            f"[DEBUG-EXECUTOR] execute() called | log_path={log_path} | "
            f"command_len={len(command)} | timeout={timeout} | cwd={cwd}"
        )

        self._write_log(
            log_path,
            f"[DEBUG] ===== LocalExecutor.execute() START =====\n",
        )
        self._write_log(
            log_path,
            f"[DEBUG] {datetime.now(timezone.utc).isoformat()} execute() called\n",
        )
        self._write_log(log_path, f"[DEBUG] command length: {len(command)} chars\n")
        self._write_log(
            log_path,
            f"[DEBUG] command first 500 chars: {command[:500]}\n",
        )
        self._write_log(log_path, f"[DEBUG] timeout: {timeout}\n")
        self._write_log(log_path, f"[DEBUG] cwd: {cwd}\n")
        self._write_log(log_path, f"[DEBUG] env keys: {list(env.keys())}\n")
        self._write_log(log_path, f"[DEBUG] log_path: {log_path}\n")

        if _DANGEROUS_PATTERNS.search(command):
            error_msg = t("Command contains dangerous pattern")
            self._write_log(log_path, f"[ERROR] {error_msg}\n[ERROR] Command: {command[:200]}\n")
            return ExecutorResult(exit_code=1, stderr=error_msg)

        merged_env = {**os.environ, **env}
        run_id = env.get("TASKPPS_RUN_ID", uuid.uuid4().hex[:12])
        task_id = env.get("TASKPPS_TASK_ID", uuid.uuid4().hex[:8])
        merged_env["TASKPPS_RUN_ID"] = run_id
        merged_env["TASKPPS_TASK_ID"] = task_id
        merged_env["TASKPPS_PID"] = str(os.getpid())

        log_dir = log_path.parent
        log_dir.mkdir(parents=True, exist_ok=True)
        self._exit_code_file = log_dir / f".taskpps_exit_{task_id}"
        self._wrapper_script = log_dir / f".taskpps_wrapper_{task_id}.sh"

        command_b64 = base64.b64encode(command.encode("utf-8")).decode("ascii")
        wrapper_content = _WRAPPER_TEMPLATE.format(
            exit_code_file=str(self._exit_code_file),
            command_b64=command_b64,
        )
        self._wrapper_script.write_text(wrapper_content, encoding="utf-8")
        self._wrapper_script.chmod(0o755)

        self._write_log(
            log_path,
            f"[DEBUG] wrapper_script: {self._wrapper_script}\n",
        )
        self._write_log(
            log_path,
            f"[DEBUG] wrapper_script exists: {self._wrapper_script.exists()}\n",
        )
        self._write_log(
            log_path,
            f"[DEBUG] wrapper_script size: {self._wrapper_script.stat().st_size} bytes\n",
        )
        self._write_log(
            log_path,
            f"[DEBUG] exit_code_file: {self._exit_code_file}\n",
        )

        if self._exit_code_file.exists():
            self._exit_code_file.unlink()
            self._write_log(
                log_path,
                f"[DEBUG] removed pre-existing exit_code_file\n",
            )

        shell = get_settings().executor.shell

        self._write_log(
            log_path,
            f"[INFO] {datetime.now(timezone.utc).isoformat()} Starting command execution\n",
        )
        self._write_log(log_path, f"[INFO] Shell: {shell}\n")
        self._write_log(log_path, f"[INFO] Working Directory: {cwd or os.getcwd()}\n")
        self._write_log(log_path, f"[INFO] Timeout: {timeout or 'none'}s\n")
        self._write_log(log_path, f"[INFO] Run ID: {run_id}\n")
        self._write_log(log_path, f"[INFO] Task ID: {task_id}\n")
        if env:
            self._write_log(
                log_path,
                f"[INFO] Environment Variables: {list(env.keys())}\n",
            )

        try:
            self._write_log(
                log_path,
                f"[DEBUG] about to create_subprocess_exec: {shell} {self._wrapper_script}\n",
            )
            self._process = await asyncio.create_subprocess_exec(
                shell,
                str(self._wrapper_script),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
                env=merged_env,
                cwd=cwd,
            )
            self._write_log(
                log_path,
                f"[DEBUG] create_subprocess_exec returned, PID: {self._process.pid}\n",
            )
            self._write_log(
                log_path,
                f"[DEBUG] process.returncode immediately: {self._process.returncode}\n",
            )
        except Exception as e:
            error_msg = f"Failed to create subprocess: {e}"
            self._write_log(log_path, f"[ERROR] {error_msg}\n")
            self._write_log(
                log_path, f"[DEBUG] traceback:\n{traceback.format_exc()}\n"
            )
            self._cleanup_temp_files()
            return ExecutorResult(exit_code=1, stderr=error_msg)

        self._write_log(
            log_path, f"[INFO] Process started with PID: {self._process.pid}\n"
        )

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
            except Exception as e:
                self._write_log(
                    log_path,
                    f"[ERROR] Error reading process output: {e}\n",
                )
                self._write_log(
                    log_path,
                    f"[DEBUG] _read_and_write traceback:\n{traceback.format_exc()}\n",
                )

        try:
            read_task = asyncio.create_task(_read_and_write())
            self._write_log(
                log_path,
                f"[DEBUG] read_task created, entering wait phase\n",
            )

            if timeout is not None and timeout > 0:
                self._write_log(
                    log_path,
                    f"[DEBUG] waiting for process with timeout={timeout}s\n",
                )
                try:
                    deadline = asyncio.get_event_loop().time() + timeout
                    while self._process.returncode is None:
                        if asyncio.get_event_loop().time() >= deadline:
                            raise asyncio.TimeoutError()
                        await asyncio.sleep(0.1)
                    self._write_log(
                        log_path,
                        f"[DEBUG] process completed, returncode={self._process.returncode}\n",
                    )
                except asyncio.TimeoutError:
                    self._write_log(
                        log_path,
                        f"[ERROR] Process timed out after {timeout}s\n",
                    )
                    self._write_log(
                        log_path,
                        f"[DEBUG] process.returncode at timeout: {self._process.returncode}\n",
                    )
                    self._kill_process_tree(self._process.pid, signal.SIGKILL)
                    try:
                        await asyncio.wait_for(self._process.wait(), timeout=5)
                    except Exception:
                        pass

                    msg = t("Task exceeded timeout of {timeout}s", timeout=timeout)
                    output_lines.append(msg)
                    self._write_log(log_path, msg + "\n")
                    self._cleanup_temp_files()
                    return ExecutorResult(
                        exit_code=-1, stdout="".join(output_lines)
                    )
            else:
                self._write_log(
                    log_path,
                    f"[DEBUG] waiting for process (no timeout)\n",
                )
                while self._process.returncode is None:
                    await asyncio.sleep(0.1)
                self._write_log(
                    log_path,
                    f"[DEBUG] process completed (no timeout path), returncode={self._process.returncode}\n",
                )

            self._write_log(
                log_path,
                f"[DEBUG] about to await read_task\n",
            )
            await read_task
            self._write_log(
                log_path,
                f"[DEBUG] read_task completed\n",
            )

            exit_code = self._process.returncode

            self._write_log(
                log_path,
                f"[DEBUG] process.returncode = {exit_code!r} (type={type(exit_code).__name__})\n",
            )

            if exit_code is None:
                self._write_log(
                    log_path,
                    f"[DEBUG] returncode is None, checking exit_code_file\n",
                )
                self._write_log(
                    log_path,
                    f"[DEBUG] exit_code_file exists: {self._exit_code_file.exists()}\n",
                )
                if self._exit_code_file.exists():
                    try:
                        raw = self._exit_code_file.read_text()
                        self._write_log(
                            log_path,
                            f"[DEBUG] exit_code_file content: {raw!r}\n",
                        )
                    except Exception as e:
                        self._write_log(
                            log_path,
                            f"[DEBUG] failed to read exit_code_file: {e}\n",
                        )
                exit_code = await self._poll_exit_code_file(
                    timeout=10, log_path=log_path
                )
                self._write_log(
                    log_path,
                    f"[DEBUG] _poll_exit_code_file returned: {exit_code!r}\n",
                )

            if exit_code is None:
                self._write_log(
                    log_path,
                    "[ERROR] Process did not complete properly (exit code is None)\n",
                )
                self._write_log(
                    log_path,
                    f"[DEBUG] final fallback: exit_code_file exists={self._exit_code_file.exists()}\n",
                )
                exit_code = -1

            self._write_log(
                log_path,
                f"[INFO] Process exited with code: {exit_code}\n",
            )
            self._write_log(
                log_path,
                f"[DEBUG] output_lines count: {len(output_lines)}\n",
            )

        except asyncio.CancelledError:
            self._write_log(
                log_path,
                f"[DEBUG] CancelledError caught\n",
            )
            self._write_log(log_path, "[WARN] Task was cancelled\n")
            if self._process and self._process.returncode is None:
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
            self._write_log(log_path, msg + "\n")
            self._cleanup_temp_files()
            return ExecutorResult(exit_code=-1, stdout="".join(output_lines))
        except Exception as e:
            error_msg = f"Unexpected execution error: {e}"
            self._write_log(log_path, f"[ERROR] {error_msg}\n")
            self._write_log(
                log_path,
                f"[DEBUG] unexpected exception traceback:\n{traceback.format_exc()}\n",
            )
            self._cleanup_temp_files()
            return ExecutorResult(exit_code=1, stderr=error_msg)
        finally:
            self._write_log(
                log_path,
                f"[DEBUG] finally block: setting self._process = None\n",
            )
            self._process = None

        self._write_log(
            log_path,
            f"[DEBUG] about to cleanup_temp_files\n",
        )
        self._cleanup_temp_files()

        self._write_log(
            log_path,
            f"[DEBUG] returning ExecutorResult(exit_code={exit_code})\n",
        )
        self._write_log(
            log_path,
            f"[DEBUG] ===== LocalExecutor.execute() END =====\n",
        )

        return ExecutorResult(
            exit_code=exit_code,
            stdout="".join(output_lines),
        )

    async def _poll_exit_code_file(
        self, timeout: int = 10, log_path: Path | None = None
    ) -> int | None:
        if not self._exit_code_file:
            if log_path:
                self._write_log(
                    log_path,
                    f"[DEBUG] _poll_exit_code_file: self._exit_code_file is None\n",
                )
            return None
        if not self._exit_code_file.exists():
            if log_path:
                self._write_log(
                    log_path,
                    f"[DEBUG] _poll_exit_code_file: file does not exist: {self._exit_code_file}\n",
                )
            return None

        if log_path:
            self._write_log(
                log_path,
                f"[DEBUG] _poll_exit_code_file: starting poll, timeout={timeout}s, file={self._exit_code_file}\n",
            )

        deadline = asyncio.get_event_loop().time() + timeout
        poll_count = 0
        while asyncio.get_event_loop().time() < deadline:
            poll_count += 1
            try:
                content = self._exit_code_file.read_text().strip()
                if log_path and poll_count <= 3:
                    self._write_log(
                        log_path,
                        f"[DEBUG] _poll_exit_code_file: poll#{poll_count} content={content!r}\n",
                    )
                if content:
                    result = int(content)
                    if log_path:
                        self._write_log(
                            log_path,
                            f"[DEBUG] _poll_exit_code_file: got exit code {result} after {poll_count} polls\n",
                        )
                    return result
            except (ValueError, OSError) as e:
                if log_path:
                    self._write_log(
                        log_path,
                        f"[DEBUG] _poll_exit_code_file: poll#{poll_count} exception: {e}\n",
                    )
            await asyncio.sleep(0.5)

        if log_path:
            self._write_log(
                log_path,
                f"[DEBUG] _poll_exit_code_file: timed out after {poll_count} polls\n",
            )
            try:
                final_content = self._exit_code_file.read_text()
                self._write_log(
                    log_path,
                    f"[DEBUG] _poll_exit_code_file: final file content={final_content!r}\n",
                )
            except Exception as e:
                self._write_log(
                    log_path,
                    f"[DEBUG] _poll_exit_code_file: final read failed: {e}\n",
                )

        return None

    def _kill_process_tree(self, pid: int, sig: int) -> None:
        pids = [pid] + _collect_descendants(pid)
        for p in reversed(pids):
            try:
                os.kill(p, sig)
            except (ProcessLookupError, PermissionError, OSError):
                pass

    def _cleanup_temp_files(self) -> None:
        for f in (self._wrapper_script, self._exit_code_file):
            if f and f.exists():
                try:
                    f.unlink()
                except OSError:
                    pass
        self._wrapper_script = None
        self._exit_code_file = None

    def _write_log(self, log_path: Path, message: str) -> None:
        try:
            with open(log_path, "a") as f:
                f.write(message)
                f.flush()
                os.fsync(f.fileno())
        except Exception as e:
            print(
                f"[DEBUG-EXECUTOR] _write_log FAILED: {e} | path={log_path}",
                file=sys.stderr,
                flush=True,
            )

    async def cancel(self) -> None:
        self._cancelled = True
        if self._process and self._process.returncode is None:
            self._kill_process_tree(self._process.pid, signal.SIGTERM)

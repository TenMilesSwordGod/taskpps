from __future__ import annotations

import asyncio
import base64
import os
import re
import signal
import uuid
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

_WRAPPER_TEMPLATE = """\
#!/bin/bash
set -o pipefail

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

        if self._exit_code_file.exists():
            self._exit_code_file.unlink()

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
            self._process = await asyncio.create_subprocess_exec(
                shell,
                str(self._wrapper_script),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
                env=merged_env,
                cwd=cwd,
                preexec_fn=os.setsid,
            )
        except Exception as e:
            error_msg = f"Failed to create subprocess: {e}"
            self._write_log(log_path, f"[ERROR] {error_msg}\n")
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
                    log_path, f"[ERROR] Error reading process output: {e}\n"
                )

        try:
            read_task = asyncio.create_task(_read_and_write())
            if timeout is not None and timeout > 0:
                try:
                    await asyncio.wait_for(self._process.wait(), timeout=timeout)
                except asyncio.TimeoutError:
                    self._write_log(
                        log_path,
                        f"[ERROR] Process timed out after {timeout}s\n",
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
                await self._process.wait()

            await read_task

            exit_code = self._process.returncode

            if exit_code is None:
                exit_code = await self._poll_exit_code_file(timeout=10)

            if exit_code is None:
                self._write_log(
                    log_path,
                    "[ERROR] Process did not complete properly (exit code is None)\n",
                )
                exit_code = -1

            self._write_log(
                log_path, f"[INFO] Process exited with code: {exit_code}\n"
            )

        except asyncio.CancelledError:
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
            self._cleanup_temp_files()
            return ExecutorResult(exit_code=1, stderr=error_msg)
        finally:
            self._process = None

        self._cleanup_temp_files()

        return ExecutorResult(
            exit_code=exit_code,
            stdout="".join(output_lines),
        )

    async def _poll_exit_code_file(self, timeout: int = 10) -> int | None:
        if not self._exit_code_file or not self._exit_code_file.exists():
            return None

        deadline = asyncio.get_event_loop().time() + timeout
        while asyncio.get_event_loop().time() < deadline:
            try:
                content = self._exit_code_file.read_text().strip()
                if content:
                    return int(content)
            except (ValueError, OSError):
                pass
            await asyncio.sleep(0.5)

        return None

    def _kill_process_tree(self, pid: int, sig: int) -> None:
        try:
            pgid = os.getpgid(pid)
            os.killpg(pgid, sig)
        except (ProcessLookupError, PermissionError, OSError):
            try:
                os.kill(pid, sig)
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
        except Exception:
            pass

    async def cancel(self) -> None:
        self._cancelled = True
        if self._process and self._process.returncode is None:
            self._kill_process_tree(self._process.pid, signal.SIGTERM)

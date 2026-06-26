from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import shlex
from pathlib import Path

from taskpps.executors.base import BaseExecutor, ExecutorResult

logger = logging.getLogger(__name__)


class PluginExecutor(BaseExecutor):
    def __init__(
        self,
        binary_path: Path | None = None,
        params: dict | None = None,
        delegate: BaseExecutor | None = None,
    ):
        self._binary_path = binary_path
        self._params = params or {}
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
        if self._delegate is not None and self._binary_path is not None:
            remote_cmd = _build_plugin_remote_command(self._binary_path, self._params)
            return await self._delegate.execute(
                command=remote_cmd,
                env=env,
                log_path=log_path,
                timeout=timeout,
                cwd=cwd,
            )

        return await self._execute_local(command, env, log_path, timeout, cwd)

    async def _execute_local(
        self,
        command: str,
        env: dict[str, str],
        log_path: Path,
        timeout: int | None = None,
        cwd: str | None = None,
    ) -> ExecutorResult:
        if self._binary_path is None:
            return ExecutorResult(exit_code=-1, stderr="Plugin binary path is None")

        self._ensure_log_dir(log_path)

        request = json.dumps(
            {"jsonrpc": "2.0", "method": "execute", "params": self._params, "id": 1}
        )

        try:
            self._process = await asyncio.create_subprocess_exec(
                str(self._binary_path),
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env,
                cwd=cwd,
            )
        except OSError as e:
            error_msg = f"Failed to spawn plugin binary {self._binary_path}: {e}"
            logger.error(error_msg)
            with open(log_path, "a") as f:
                f.write(f"{error_msg}\n")
            return ExecutorResult(exit_code=-1, stderr=error_msg)

        try:
            if self._process.stdin is None:
                return ExecutorResult(exit_code=-1, stderr="Plugin stdin is None")
            self._process.stdin.write((request + "\n").encode())
            await self._process.stdin.drain()
        except (BrokenPipeError, ConnectionResetError, OSError) as e:
            logger.error("Failed to send execute request to plugin %s: %s", self._binary_path, e)
            return ExecutorResult(exit_code=-1, stderr=str(e))
        finally:
            if self._process.stdin is not None:
                with contextlib.suppress(Exception):
                    self._process.stdin.close()

        effective_timeout = timeout if timeout else 3600
        try:
            if self._process.stdout is None:
                return ExecutorResult(exit_code=-1, stderr="Plugin stdout is None")
            line = await asyncio.wait_for(
                self._process.stdout.readline(), timeout=effective_timeout
            )
        except asyncio.TimeoutError:
            logger.error("Plugin executor %s timed out after %ss", self._binary_path, effective_timeout)
            with contextlib.suppress(ProcessLookupError):
                self._process.kill()
            await self._process.wait()
            return ExecutorResult(
                exit_code=-1,
                stderr=f"Plugin execution timed out after {effective_timeout}s",
            )

        stderr_output = ""
        if self._process.stderr is not None:
            try:
                stderr_bytes = await asyncio.wait_for(
                    self._process.stderr.read(), timeout=5
                )
                stderr_output = stderr_bytes.decode("utf-8", errors="replace")
            except asyncio.TimeoutError:
                pass

        await self._process.wait()
        exit_code = self._process.returncode or -1

        if not line:
            with open(log_path, "a") as f:
                f.write(f"[ERROR] No response from plugin (EOF), stderr: {stderr_output}\n")
            return ExecutorResult(
                exit_code=exit_code,
                stdout="",
                stderr=f"Plugin process exited with code {exit_code}, stderr: {stderr_output}",
            )

        try:
            raw = json.loads(line.decode().strip())
        except json.JSONDecodeError as e:
            logger.error("Failed to parse plugin response: %s", e)
            with open(log_path, "a") as f:
                f.write(f"[ERROR] Invalid JSON response: {e}\n")
            return ExecutorResult(exit_code=-1, stderr=f"Invalid JSON response: {e}")

        result_data = raw.get("result", {})
        success = result_data.get("success", exit_code == 0)
        stdout = result_data.get("stdout", "")
        stderr = result_data.get("stderr", stderr_output)
        rpc_exit_code = result_data.get("exit_code", exit_code)

        with open(log_path, "a") as f:
            f.write(f"[INFO] Plugin executor finished, exit_code={rpc_exit_code}\n")
            if stdout:
                f.write(f"[STDOUT]\n{stdout}\n")
            if stderr:
                f.write(f"[STDERR]\n{stderr}\n")

        return ExecutorResult(
            exit_code=rpc_exit_code if success else (rpc_exit_code or 1),
            stdout=stdout,
            stderr=stderr,
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


def _build_plugin_remote_command(binary_path: Path, params: dict) -> str:
    request = json.dumps(
        {"jsonrpc": "2.0", "method": "execute", "params": params, "id": 1}
    )
    return f"echo {shlex.quote(request)} | {shlex.quote(str(binary_path))}"

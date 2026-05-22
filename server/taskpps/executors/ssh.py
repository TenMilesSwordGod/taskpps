from __future__ import annotations

import asyncio
import shlex
from pathlib import Path
from typing import Any, Dict, Optional

import paramiko

from taskpps.config import get_settings
from taskpps.executors.base import BaseExecutor, ExecutorResult


class SSHExecutor(BaseExecutor):
    def __init__(self, host: str, port: int = 22, username: str = "root", password: Optional[str] = None, key_path: Optional[str] = None):
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.key_path = key_path
        self._client: Optional[paramiko.SSHClient] = None
        self._channel = None

    async def execute(
        self,
        command: str,
        env: Dict[str, str],
        log_path: Path,
        timeout: Optional[int] = None,
        cwd: Optional[str] = None,
    ) -> ExecutorResult:
        self._ensure_log_dir(log_path)

        shell = get_settings().executor.shell
        parts = []
        if cwd:
            parts.append(f"cd {shlex.quote(cwd)}")
        for k, v in env.items():
            parts.append(f"export {shlex.quote(k)}={shlex.quote(v)}")
        parts.append(command)
        inner_script = " && ".join(parts)
        full_command = f"{shell} -c {shlex.quote(inner_script)}"

        def _run_ssh():
            client = paramiko.SSHClient()
            client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            self._client = client

            connect_kwargs = {
                "hostname": self.host,
                "port": self.port,
                "username": self.username,
            }
            if self.key_path:
                connect_kwargs["key_filename"] = self.key_path
            elif self.password:
                connect_kwargs["password"] = self.password

            client.connect(timeout=30, **connect_kwargs)

            stdin, stdout, stderr = client.exec_command(full_command, timeout=timeout)  # pragma: no cover
            self._channel = stdout.channel  # pragma: no cover

            output = stdout.read().decode("utf-8", errors="replace")  # pragma: no cover
            error = stderr.read().decode("utf-8", errors="replace")  # pragma: no cover
            exit_code = stdout.channel.recv_exit_status()  # pragma: no cover

            client.close()  # pragma: no cover
            self._client = None  # pragma: no cover
            self._channel = None  # pragma: no cover

            return exit_code, output, error  # pragma: no cover

        try:
            loop = asyncio.get_event_loop()
            exit_code, output, error = await loop.run_in_executor(None, _run_ssh)
        except Exception as e:
            exit_code = -1
            output = ""
            error = str(e)
        except asyncio.CancelledError:  # pragma: no cover
            if self._channel:  # pragma: no cover
                self._channel.close()  # pragma: no cover
            if self._client:  # pragma: no cover
                self._client.close()  # pragma: no cover
            return ExecutorResult(exit_code=-1, stderr="Task cancelled")  # pragma: no cover

        combined = output + error
        with open(log_path, "w") as f:
            f.write(combined)

        return ExecutorResult(exit_code=exit_code, stdout=combined)

    async def cancel(self) -> None:
        if self._channel:
            try:
                self._channel.close()
            except Exception:
                pass
        if self._client:
            try:
                self._client.close()
            except Exception:
                pass

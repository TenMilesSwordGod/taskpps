from __future__ import annotations

import asyncio
import shlex
import uuid
from pathlib import Path
from typing import Any, Dict, Optional

import paramiko

from taskpps.config import get_settings
from taskpps.executors.base import BaseExecutor, ExecutorResult
from taskpps.i18n import t


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

        def _build_script_content():
            lines = ["#!/bin/sh", "set -e"]
            if cwd:
                lines.append(f"cd {shlex.quote(cwd)}")
            for k, v in env.items():
                lines.append(f"export {shlex.quote(k)}={shlex.quote(v)}")
            lines.append(command)
            return "\n".join(lines) + "\n"

        def _run_ssh():
            client = paramiko.SSHClient()
            client.load_system_host_keys()
            client.set_missing_host_key_policy(paramiko.WarningPolicy())
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

            try:
                client.connect(timeout=30, **connect_kwargs)

                script_id = uuid.uuid4().hex[:12]
                remote_script = f"/tmp/.taskpps_{script_id}.sh"
                try:
                    with client.open_sftp() as sftp:
                        with sftp.file(remote_script, "w") as f:
                            f.write(_build_script_content())
                        sftp.chmod(remote_script, 0o700)

                    exec_cmd = f"{shell} {shlex.quote(remote_script)}"
                    stdin, stdout, stderr = client.exec_command(exec_cmd, timeout=timeout)
                    self._channel = stdout.channel

                    output = stdout.read().decode("utf-8", errors="replace")
                    error = stderr.read().decode("utf-8", errors="replace")
                    exit_code = stdout.channel.recv_exit_status()

                    with client.open_sftp() as sftp:
                        try:
                            sftp.remove(remote_script)
                        except OSError:
                            pass

                    return exit_code, output, error
                finally:
                    self._channel = None
            finally:
                client.close()
                self._client = None

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
            return ExecutorResult(exit_code=-1, stderr=t("Task was cancelled"))  # pragma: no cover

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

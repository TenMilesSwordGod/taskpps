from __future__ import annotations

import asyncio
import contextlib
import logging
import select
import shlex
from pathlib import Path

import paramiko

from taskpps.executors.base import BaseExecutor, ExecutorResult
from taskpps.i18n import t

logger = logging.getLogger(__name__)


class SSHExecutor(BaseExecutor):
    def __init__(
        self,
        host: str,
        port: int = 22,
        username: str = "root",
        password: str | None = None,
        key_path: str | None = None,
    ):
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.key_path = key_path
        self._client: paramiko.SSHClient | None = None
        self._channel: paramiko.Channel | None = None

    def _make_connect_kwargs(self) -> dict:
        kwargs: dict = {}
        if self.key_path:
            kwargs["key_filename"] = self.key_path
        elif self.password:
            kwargs["password"] = self.password
        return kwargs

    async def execute(
        self,
        command: str,
        env: dict[str, str],
        log_path: Path,
        timeout: int | None = None,
        cwd: str | None = None,
    ) -> ExecutorResult:
        self._ensure_log_dir(log_path)

        def _run_ssh():
            connect_kwargs = self._make_connect_kwargs()
            try:
                client = paramiko.SSHClient()
                client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
                client.connect(
                    hostname=self.host,
                    port=self.port,
                    username=self.username,
                    timeout=30,
                    **connect_kwargs,
                )
                self._client = client
                logger.info("SSHExecutor: connected to %s@%s:%d", self.username, self.host, self.port)

                env_exports = " ".join(f"export {shlex.quote(k)}={shlex.quote(v)}" for k, v in env.items())
                effective_cwd = cwd or "."
                profile_setup = (
                    "source /etc/profile 2>/dev/null; "
                    "[ -f ~/.bash_profile ] && source ~/.bash_profile 2>/dev/null; "
                    "[ -f ~/.bashrc ] && source ~/.bashrc 2>/dev/null"
                )
                full_command = f"{profile_setup}; cd {shlex.quote(effective_cwd)} && {env_exports} && {command}"

                transport = client.get_transport()
                if transport is None:
                    raise RuntimeError("SSH transport is None")
                channel = transport.open_session()
                channel.settimeout(1.0)
                channel.exec_command(full_command)
                self._channel = channel
                logger.info("SSHExecutor: channel opened on %s, cmd=%s...", self.host, full_command[:200])

                combined_output = ""
                current_line = ""
                with open(log_path, "w") as f:
                    while True:
                        if self._client is None:
                            channel.close()
                            return -1, combined_output, combined_output

                        readable, _, _ = select.select([channel], [], [], 0.5)
                        if readable:
                            data = channel.recv(4096)
                            if not data:
                                break
                            chunk = data.decode("utf-8", errors="replace")
                            current_line += chunk
                            while "\n" in current_line:
                                line, current_line = current_line.split("\n", 1)
                                f.write(line + "\n")
                                f.flush()
                                combined_output += line + "\n"

                        if channel.exit_status_ready() and not channel.recv_ready():
                            break

                    if channel.recv_ready():
                        remaining = channel.recv(65536)
                        if remaining:
                            chunk = remaining.decode("utf-8", errors="replace")
                            current_line += chunk

                    while channel.recv_stderr_ready():
                        data = channel.recv_stderr(4096)
                        if data:
                            chunk = data.decode("utf-8", errors="replace")
                            current_line += chunk
                            while "\n" in current_line:
                                line, current_line = current_line.split("\n", 1)
                                f.write(line + "\n")
                                f.flush()
                                combined_output += line + "\n"

                    if current_line:
                        f.write(current_line)
                        f.flush()
                        combined_output += current_line

                    exit_code = channel.recv_exit_status()
                    logger.info("SSHExecutor: command finished on %s exit_code=%d", self.host, exit_code)
                    return exit_code, combined_output, combined_output

            except Exception as e:
                error_msg = str(e)
                logger.error("SSHExecutor: execution failed on %s: %s", self.host, error_msg)
                with open(log_path, "a") as f:
                    f.write(error_msg)
                return -1, error_msg, error_msg
            finally:
                with contextlib.suppress(Exception):
                    if self._channel:
                        self._channel.close()
                self._channel = None
                with contextlib.suppress(Exception):
                    if self._client:
                        self._client.close()
                self._client = None

        try:
            loop = asyncio.get_event_loop()
            exit_code, output, error = await loop.run_in_executor(None, _run_ssh)
        except asyncio.CancelledError:
            logger.info("SSHExecutor: task cancelled on %s", self.host)
            self._channel = None
            with contextlib.suppress(Exception):
                if self._client:
                    self._client.close()
            self._client = None
            return ExecutorResult(exit_code=-1, stderr=t("Task was cancelled"))

        return ExecutorResult(exit_code=exit_code, stdout=output, stderr=error)

    async def cancel(self) -> None:
        logger.info("SSHExecutor.cancel: closing connection to %s", self.host)
        self._channel = None
        with contextlib.suppress(Exception):
            if self._client:
                self._client.close()
        self._client = None

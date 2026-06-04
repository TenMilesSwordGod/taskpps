from __future__ import annotations

import asyncio
import contextlib
import shlex
from pathlib import Path

from fabric import Connection

from taskpps.config import get_settings
from taskpps.executors.base import BaseExecutor, ExecutorResult
from taskpps.i18n import t


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
        self._connection: Connection | None = None

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

        shell = get_settings().executor.shell
        host_str = f"{self.host}:{self.port}"

        def _run_ssh():
            connect_kwargs = self._make_connect_kwargs()
            try:
                conn = Connection(
                    host=host_str,
                    user=self.username,
                    connect_kwargs=connect_kwargs,
                    connect_timeout=30,
                )
                self._connection = conn

                env_exports = " ".join(f"export {shlex.quote(k)}={shlex.quote(v)}" for k, v in env.items())
                full_command = f"{env_exports} && {command}"

                with conn.cd(cwd or "."):
                    result = conn.run(
                        full_command,
                        shell=shell,
                        warn=True,
                        hide=True,
                        timeout=timeout,
                    )

                output = result.stdout or ""
                error = result.stderr or ""
                exit_code = result.exited

                combined = output + error
                with open(log_path, "w") as f:
                    f.write(combined)

                return exit_code, combined, error
            except Exception as e:
                # 异常时也要保存日志
                error_msg = str(e)
                with open(log_path, "w") as f:
                    f.write(error_msg)
                return -1, error_msg, error_msg
            finally:
                try:
                    if self._connection:
                        self._connection.close()
                except Exception:
                    pass
                self._connection = None

        try:
            loop = asyncio.get_event_loop()
            exit_code, output, error = await loop.run_in_executor(None, _run_ssh)
        except asyncio.CancelledError:
            if self._connection:
                with contextlib.suppress(Exception):
                    self._connection.close()
            return ExecutorResult(exit_code=-1, stderr=t("Task was cancelled"))

        return ExecutorResult(exit_code=exit_code, stdout=output, stderr=error)

    async def cancel(self) -> None:
        if self._connection:
            with contextlib.suppress(Exception):
                self._connection.close()

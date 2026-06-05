from __future__ import annotations

import asyncio
import logging
import os
import time

from taskpps.i18n import t
from taskpps.loaders.agent_loader import AgentLoader
from taskpps.loaders.credential_loader import CredentialLoader
from taskpps.services.agent_manager import AgentManager

logger = logging.getLogger(__name__)

BOOTSTRAP_TIMEOUT = 30


class AgentBootstrapError(Exception):
    pass


class AgentBootstrap:
    def __init__(self):
        self._agent_loader = AgentLoader()
        self._credential_loader = CredentialLoader()

    async def bootstrap(self, agent_id: str) -> dict:
        agent_data = self._agent_loader.get(agent_id)
        if agent_data is None:
            raise AgentBootstrapError(t("Agent not found: {id}", id=agent_id))

        if not agent_data.get("agent_auto_bootstrap", True):
            raise AgentBootstrapError(t("Agent '{id}' has agent_auto_bootstrap disabled", id=agent_id))

        host = agent_data.get("host", "")
        port = agent_data.get("port", 22)
        credential_id = agent_data.get("credential_id", "")
        agent_binary_path = agent_data.get("agent_binary_path", "/usr/local/bin/taskpps-agent")
        agent_secret = agent_data.get("agent_secret", "")

        if not host or host in ("localhost", "127.0.0.1", "::1"):
            return {"success": True, "agent_pid": 0, "message": "local agent"}

        username = "root"
        password = None
        key_path = None

        if credential_id:
            cred_data = self._credential_loader.get(credential_id)
            if cred_data:
                username = cred_data.get("username", username)
                password = cred_data.get("password")
                key_path = cred_data.get("key_path")

        ssh = await self._ssh_connect(host, port, username, password, key_path)
        try:
            installed = await self._check_binary(ssh, agent_binary_path)
            if not installed:
                logger.info("Agent binary not found on %s, deploying...", host)
                await self._deploy_binary(ssh, host, agent_binary_path)
                await self._ssh_exec(ssh, f"chmod 755 {agent_binary_path}")

            server_url = f"ws://{self._get_server_host()}:{self._get_ws_port()}"

            pid = await self._start_agent_daemon(
                ssh, agent_binary_path, agent_id, agent_secret, server_url, agent_data
            )
            if pid:
                logger.info("Agent '%s' started on %s with PID %d", agent_id, host, pid)
        finally:
            await self._ssh_close(ssh)

        manager = AgentManager.instance()
        try:
            await asyncio.wait_for(
                self._wait_for_handshake(manager, agent_id),
                timeout=BOOTSTRAP_TIMEOUT,
            )
            logger.info("Agent '%s' handshake completed", agent_id)
            return {"success": True, "agent_pid": 0}
        except asyncio.TimeoutError as e:
            raise AgentBootstrapError(t("Agent '{id}' handshake timeout after bootstrap", id=agent_id)) from e

    async def _ssh_connect(self, host: str, port: int, username: str,
                           password: str | None, key_path: str | None):
        import paramiko
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

        connect_kwargs: dict = {"timeout": 10}
        if key_path:
            connect_kwargs["key_filename"] = key_path
        elif password:
            connect_kwargs["password"] = password

        await asyncio.to_thread(
            client.connect, hostname=host, port=port, username=username, **connect_kwargs
        )
        return client

    async def _ssh_close(self, client) -> None:
        try:
            client.close()
        except Exception:
            pass

    async def _ssh_exec(self, client, command: str) -> tuple[int, str, str]:
        def _run():
            _stdin, stdout, stderr = client.exec_command(command, timeout=10)
            return stdout.channel.recv_exit_status(), stdout.read().decode(), stderr.read().decode()
        return await asyncio.to_thread(_run)

    async def _check_binary(self, client, path: str) -> bool:
        exit_code, _, _ = await self._ssh_exec(client, f"test -x {path}")
        return exit_code == 0

    async def _deploy_binary(self, client, host: str, dest_path: str) -> None:
        import platform
        arch = platform.machine()
        if arch == "x86_64":
            arch = "amd64"
        elif arch == "aarch64":
            arch = "arm64"

        local_binary = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
            "execution_agent", "build", f"taskpps-agent-linux-{arch}",
        )

        if not os.path.exists(local_binary):
            local_binary = os.path.join(
                os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
                "execution_agent", "taskpps-agent",
            )

        if not os.path.exists(local_binary):
            raise AgentBootstrapError(t("Agent binary not found at {path}", path=local_binary))

        sftp = client.open_sftp()
        try:
            sftp.put(local_binary, dest_path)
        finally:
            sftp.close()

    async def _start_agent_daemon(self, client, binary_path: str,
                                   agent_id: str, secret: str, server_url: str,
                                   agent_data: dict) -> int:
        log_file = agent_data.get("agent_log_dir", "/var/log/taskpps") + "/agent.log"
        pid_file = agent_data.get("agent_pid_file", "/var/run/taskpps-agent.pid")

        cmd = (
            f"mkdir -p $(dirname {pid_file}) $(dirname {log_file}) && "
            f"{binary_path} run --server {server_url} --agent-id {agent_id}"
        )
        if secret:
            cmd += f" --secret {secret}"
        cmd += f" --log-file {log_file} --daemon --pid-file {pid_file}"

        exit_code, stdout, stderr = await self._ssh_exec(client, cmd)
        if exit_code != 0:
            raise AgentBootstrapError(t("Failed to start agent: {error}", error=stderr or stdout))

        time.sleep(2)
        exit_code, pid_str, _ = await self._ssh_exec(client, f"cat {pid_file}")
        if exit_code != 0:
            raise AgentBootstrapError(t("Failed to read PID file"))
        return int(pid_str.strip())

    def _get_server_host(self) -> str:
        settings = __import__("taskpps.config", fromlist=["get_settings"]).get_settings()
        host = settings.server.host
        if host == "0.0.0.0":
            import socket
            return socket.gethostbyname(socket.gethostname())
        return host if host != "127.0.0.1" else "localhost"

    def _get_ws_port(self) -> int:
        try:
            from taskpps.config import get_settings
            settings = get_settings()
            agent_config = getattr(settings, "agent", None)
            if agent_config:
                return getattr(agent_config, "ws_port", 28765)
        except Exception:
            pass
        return 28765

    async def _wait_for_handshake(self, manager: AgentManager, agent_id: str) -> None:
        while True:
            if manager.is_connected(agent_id):
                return
            await asyncio.sleep(0.5)

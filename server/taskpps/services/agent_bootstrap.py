from __future__ import annotations

import asyncio
import logging
import os

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

        if not host or host in ("localhost", "127.0.0.1", "::1"):
            return {"success": True, "agent_pid": 0, "message": "local agent"}

        username = agent_data.get("username", "root")
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
            remote_home, is_root = await self._get_remote_user_info(ssh)

            if is_root:
                default_binary = "/usr/local/bin/taskpps-agent"
                default_log_dir = "/var/log/taskpps"
                default_pid_file = "/var/run/taskpps-agent.pid"
            else:
                work_dir = f"{remote_home}/.taskpps"
                default_binary = f"{work_dir}/taskpps-agent"
                default_log_dir = f"{work_dir}/logs"
                default_pid_file = f"{work_dir}/agent.pid"

            agent_binary_path = agent_data.get("agent_binary_path", default_binary)
            agent_log_dir = agent_data.get("agent_log_dir", default_log_dir)
            agent_pid_file = agent_data.get("agent_pid_file", default_pid_file)
            agent_secret = agent_data.get("agent_secret", "")

            installed = await self._check_binary(ssh, agent_binary_path)
            if not installed:
                logger.info("Agent binary not found on %s, deploying to %s ...", host, agent_binary_path)
                await self._ensure_remote_dir(ssh, agent_binary_path)
                await self._ensure_remote_dir(ssh, f"{agent_log_dir}/_")
                await self._deploy_binary(ssh, host, agent_binary_path)
                await self._ssh_exec(ssh, f"chmod 755 {agent_binary_path}")

            server_url = f"ws://{self._get_server_host(agent_data)}:{self._get_ws_port()}/api/ws/agent"

            pid = await self._start_agent_daemon(
                ssh, agent_binary_path, agent_log_dir, agent_pid_file,
                agent_id, agent_secret, server_url, agent_data
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

    async def _get_remote_user_info(self, client) -> tuple[str, bool]:
        exit_code, home, _ = await self._ssh_exec(client, "echo $HOME")
        if exit_code != 0 or not home.strip():
            home = "/root"
        home = home.strip()

        exit_code, uid, _ = await self._ssh_exec(client, "id -u")
        is_root = (exit_code == 0 and uid.strip() == "0")
        return home, is_root

    async def _ensure_remote_dir(self, client, file_path: str) -> None:
        import posixpath
        parent = posixpath.dirname(file_path)
        if parent and parent != "/":
            await self._ssh_exec(client, f"mkdir -p {parent}")

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

        project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
        local_binary = os.path.join(
            project_root,
            "execution_agent", "build", f"taskpps-agent-linux-{arch}",
        )

        if not os.path.exists(local_binary):
            local_binary = os.path.join(
                project_root,
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
                                   log_dir: str, pid_file: str,
                                   agent_id: str, secret: str, server_url: str,
                                   agent_data: dict) -> int:
        log_file = f"{log_dir}/agent.log"

        cmd = (
            f"mkdir -p {log_dir} && "
            f"{binary_path} run --server {server_url} --agent-id {agent_id}"
        )
        if secret:
            cmd += f" --secret {secret}"
        cmd += f" --log-file {log_file} --daemon --pid-file {pid_file}"

        exit_code, stdout, stderr = await self._ssh_exec(client, cmd)
        if exit_code != 0:
            raise AgentBootstrapError(t("Failed to start agent: {error}", error=stderr or stdout))

        await asyncio.sleep(2)
        exit_code, pid_str, _ = await self._ssh_exec(client, f"cat {pid_file}")
        if exit_code != 0:
            raise AgentBootstrapError(t("Failed to read PID file"))
        return int(pid_str.strip())

    def _get_server_host(self, agent_data: dict = None) -> str:
        if agent_data:
            explicit = agent_data.get("server_ws_host", "")
            if explicit:
                return explicit

        settings = __import__("taskpps.config", fromlist=["get_settings"]).get_settings()
        host = settings.server.host
        if host == "0.0.0.0":
            import socket
            hostname = socket.gethostname()
            try:
                return socket.gethostbyname(hostname)
            except Exception:
                return hostname
        if host == "127.0.0.1":
            import socket
            hostname = socket.gethostname()
            try:
                ip = socket.gethostbyname(hostname)
                if ip != "127.0.0.1":
                    return ip
            except Exception:
                pass
            return socket.gethostbyname(socket.gethostname())
        return host

    def _get_ws_port(self) -> int:
        try:
            from taskpps.config import get_settings
            settings = get_settings()
            return settings.server.port
        except Exception:
            return 26521

    async def _wait_for_handshake(self, manager: AgentManager, agent_id: str) -> None:
        while True:
            if manager.is_connected(agent_id):
                return
            await asyncio.sleep(0.5)

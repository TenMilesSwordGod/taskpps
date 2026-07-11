from __future__ import annotations

import asyncio
import contextlib
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

    async def bootstrap(self, agent_id: str, agent_loader: AgentLoader | None = None, credential_loader: CredentialLoader | None = None) -> dict:
        loader = agent_loader or self._agent_loader
        if credential_loader is not None:
            self._credential_loader = credential_loader
        agent_data = loader.get(agent_id)
        if agent_data is None:
            raise AgentBootstrapError(t("Agent not found: {id}", id=agent_id))

        if not agent_data.get("agent_auto_bootstrap", True):
            raise AgentBootstrapError(t("Agent '{id}' has agent_auto_bootstrap disabled", id=agent_id))

        host = agent_data.get("host", "")
        port = agent_data.get("port", 22)
        credential_id = agent_data.get("credential_id", "")

        if not host or host in ("localhost", "127.0.0.1", "::1"):
            # Issue #107: 本地 agent 也需要等待 WebSocket 握手完成
            manager = AgentManager.instance()
            if manager.is_connected(agent_id):
                return {"success": True, "agent_pid": 0, "message": "local agent"}
            deploy_started_at = time.time()
            try:
                await asyncio.wait_for(
                    self._wait_for_handshake(manager, agent_id, deploy_started_at),
                    timeout=BOOTSTRAP_TIMEOUT,
                )
                return {"success": True, "agent_pid": 0, "message": "local agent"}
            except asyncio.TimeoutError:
                raise AgentBootstrapError(
                    t("Local agent '{id}' did not connect within {timeout}s", id=agent_id, timeout=BOOTSTRAP_TIMEOUT)
                )

        username = None
        password = None
        key_path = None

        if credential_id:
            cred_data = self._credential_loader.get(credential_id)
            if cred_data:
                username = cred_data.get("username")
                password = cred_data.get("password")
                key_path = cred_data.get("key_path")

        # 仅在 credential 未提供 username 时回退到 agent 配置或默认值
        if username is None:
            username = agent_data.get("username", "root")

        if not password and not key_path:
            raise AgentBootstrapError(
                t(
                    "No authentication method for agent '{id}' (host={host}). "
                    "Set credential_id with password or key_path in agent config.",
                    id=agent_id,
                    host=host,
                )
            )

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

            server_host = self._get_server_host(agent_data)
            server_port = self._get_ws_port()
            server_url = f"ws://{server_host}:{server_port}/api/ws/agent"

            self._check_server_reachability(ssh, host, server_host, server_port)

            installed = await self._check_binary(ssh, agent_binary_path)
            if not installed:
                logger.info("Agent binary not found on %s, deploying to %s ...", host, agent_binary_path)
                await self._ensure_remote_dir(ssh, agent_binary_path)
                await self._ensure_remote_dir(ssh, f"{agent_log_dir}/_")
                await self._deploy_binary(ssh, host, agent_binary_path)
                await self._ssh_exec(ssh, f"chmod 755 {agent_binary_path}")

            logger.info("Agent will connect to: %s", server_url)

            # Issue #70: 部署前清除残留连接，避免 _wait_for_handshake 误判旧连接为成功
            manager = AgentManager.instance()
            await manager.disconnect(agent_id)

            pid = await self._start_agent_daemon(
                ssh, agent_binary_path, agent_log_dir, agent_pid_file, agent_id, agent_secret, server_url, agent_data
            )
            if pid:
                logger.info("Agent '%s' started on %s with PID %d", agent_id, host, pid)
        finally:
            await self._ssh_close(ssh)

        deploy_started_at = time.time()
        try:
            await asyncio.wait_for(
                self._wait_for_handshake(manager, agent_id, deploy_started_at),
                timeout=BOOTSTRAP_TIMEOUT,
            )
            logger.info("Agent '%s' handshake completed", agent_id)
            return {"success": True, "agent_pid": 0}
        except asyncio.TimeoutError as e:
            agent_log_path = f"{agent_log_dir}/agent.log"
            log_tail = ""
            try:
                ssh2 = await self._ssh_connect(host, port, username, password, key_path)
                try:
                    _, log_out, _ = await self._ssh_exec(
                        ssh2, f"tail -n 30 {agent_log_path} 2>/dev/null || echo '(no log file)"
                    )
                    if log_out.strip():
                        log_tail = log_out.strip()
                finally:
                    await self._ssh_close(ssh2)
            except Exception as log_err:
                log_tail = f"(could not fetch logs: {log_err})"

            error_msg = (
                f"Agent '{agent_id}' failed to connect to {server_url} "
                f"after {BOOTSTRAP_TIMEOUT}s. Check: "
                f"Verify server is reachable from {host} and not bound to 127.0.0.1. "
                f"Agent log tail:\n{log_tail}"
            )
            raise AgentBootstrapError(error_msg) from e

    def _check_server_reachability(self, ssh, remote_host: str, server_host: str, server_port: int) -> None:
        settings = __import__("taskpps.config", fromlist=["get_settings"]).get_settings()
        bind_host = settings.server.host

        if bind_host in ("127.0.0.1", "::1"):
            logger.warning(
                "Server binds to %s but agent on %s may not reach it. "
                "Set server.host to 0.0.0.0 or a reachable IP for remote agents.",
                bind_host,
                remote_host,
            )

        if server_host in ("127.0.0.1", "::1", "localhost"):
            logger.warning(
                "Agent will try to connect to %s:%s — this address is local-only and not reachable from %s",
                server_host,
                server_port,
                remote_host,
            )

    async def _ssh_connect(self, host: str, port: int, username: str, password: str | None, key_path: str | None):
        import paramiko

        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

        connect_kwargs: dict = {"timeout": 10}
        if key_path:
            connect_kwargs["key_filename"] = key_path
        elif password:
            connect_kwargs["password"] = password

        await asyncio.to_thread(client.connect, hostname=host, port=port, username=username, **connect_kwargs)
        return client

    async def _ssh_close(self, client) -> None:
        with contextlib.suppress(Exception):
            client.close()

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
        is_root = exit_code == 0 and uid.strip() == "0"
        return home, is_root

    async def _ensure_remote_dir(self, client, file_path: str) -> None:
        import posixpath

        parent = posixpath.dirname(file_path)
        if parent and parent != "/":
            await self._ssh_exec(client, f"mkdir -p {parent}")

    async def _check_binary(self, client, path: str) -> bool:
        # Issue #69: 不仅检查文件存在，还要验证可执行（避免错误架构二进制残留）
        # 错误架构的二进制 test -x 通过，但执行时报 "Exec format error"
        exit_code, _, _ = await self._ssh_exec(client, f"{path} --help >/dev/null 2>&1")
        return exit_code == 0

    async def _deploy_binary(self, client, host: str, dest_path: str) -> None:
        exit_code, remote_arch_out, _ = await self._ssh_exec(client, "uname -m")
        if exit_code != 0 or not remote_arch_out.strip():
            raise AgentBootstrapError(t("Failed to detect remote architecture on {host}", host=host))
        remote_arch = remote_arch_out.strip()
        logger.info("Remote host %s architecture: %s", host, remote_arch)

        arch_map: dict[str, str] = {
            "x86_64": "amd64",
            "amd64": "amd64",
            "aarch64": "arm64",
            "arm64": "arm64",
            "armv8l": "arm64",
            "armv7l": "arm",
            "armv6l": "arm",
        }
        arch = arch_map.get(remote_arch)
        if arch is None:
            raise AgentBootstrapError(
                t("Unsupported remote architecture '{arch}' on {host}. "
                  "Supported: x86_64/amd64, aarch64/arm64",
                  arch=remote_arch, host=host)
            )

        project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
        local_binary = os.path.join(
            project_root,
            "execution_agent",
            "build",
            f"taskpps-agent-linux-{arch}",
        )

        # Issue #69: 不再 fallback 到本地默认二进制（通常是 x86），避免发送错误架构
        if not os.path.exists(local_binary):
            raise AgentBootstrapError(
                t("Agent binary for arch '{arch}' (uname={remote_arch}) not found at {path}. "
                  "Build it with: cd execution_agent && ./build/build.sh",
                  arch=arch, remote_arch=remote_arch, path=local_binary)
            )

        logger.info("Deploying binary %s to %s:%s", local_binary, host, dest_path)
        sftp = client.open_sftp()
        try:
            sftp.put(local_binary, dest_path)
        except Exception:
            logger.exception("SFTP put 失败: local=%s, remote=%s:%s", local_binary, host, dest_path)
            raise
        finally:
            sftp.close()

    async def _start_agent_daemon(
        self,
        client,
        binary_path: str,
        log_dir: str,
        pid_file: str,
        agent_id: str,
        secret: str,
        server_url: str,
        agent_data: dict,
    ) -> int:
        log_file = f"{log_dir}/agent.log"
        work_dir = agent_data.get("agent_work_dir", "")

        # Issue #68: 先检查远程主机上是否已有 agent 在运行，避免重复部署多个实例
        existing_pid = await self._check_existing_agent(client, pid_file)
        if existing_pid:
            logger.info(
                "Agent '%s' already running on remote host with PID %d, skipping deploy",
                agent_id,
                existing_pid,
            )
            return existing_pid

        cmd = f"mkdir -p {log_dir} && {binary_path} run --server {server_url} --agent-id {agent_id}"
        if secret:
            cmd += f" --secret {secret}"
        if work_dir:
            cmd += f" --work-dir {work_dir}"
        cmd += f" --log-file {log_file} --daemon --pid-file {pid_file}"

        exit_code, stdout, stderr = await self._ssh_exec(client, cmd)
        if exit_code != 0:
            raise AgentBootstrapError(t("Failed to start agent: {error}", error=stderr or stdout))

        await asyncio.sleep(2)
        exit_code, pid_str, _ = await self._ssh_exec(client, f"cat {pid_file}")
        if exit_code != 0:
            raise AgentBootstrapError(t("Failed to read PID file"))
        pid = int(pid_str.strip())

        # Issue #70: 验证子进程确实存活（父进程 fork 后立即 exit 0，子进程可能已崩溃）
        exit_code, _, _ = await self._ssh_exec(client, f"kill -0 {pid} 2>/dev/null")
        if exit_code != 0:
            # 进程已死，读取日志帮助诊断
            _, log_tail, _ = await self._ssh_exec(client, f"tail -n 10 {log_file} 2>/dev/null || true")
            raise AgentBootstrapError(
                t("Agent process (PID {pid}) died immediately after start. Log tail:\n{log}",
                  pid=pid, log=log_tail.strip() or "(no log)")
            )
        return pid

    async def _check_existing_agent(self, client, pid_file: str) -> int | None:
        """检查远程主机上是否已有 agent 进程在运行。

        通过 PID 文件和进程存活检查判断。如果 PID 文件存在且对应进程
        仍在运行，返回该 PID；否则清理残留 PID 文件并返回 None。
        """
        # 1. 检查 PID 文件是否存在
        exit_code, pid_str, _ = await self._ssh_exec(client, f"cat {pid_file} 2>/dev/null")
        if exit_code != 0 or not pid_str.strip():
            return None

        try:
            pid = int(pid_str.strip())
        except ValueError:
            # PID 文件内容无效，清理
            await self._ssh_exec(client, f"rm -f {pid_file}")
            return None

        if pid <= 0:
            return None

        # 2. 检查该 PID 的进程是否仍在运行
        exit_code, _, _ = await self._ssh_exec(client, f"kill -0 {pid} 2>/dev/null")
        if exit_code == 0:
            # 进程存活，进一步确认是 taskpps-agent 进程
            exit_code, cmdline, _ = await self._ssh_exec(client, f"cat /proc/{pid}/cmdline 2>/dev/null")
            if exit_code == 0 and "taskpps-agent" in cmdline:
                return pid
            # PID 被其他进程占用，不是我们的 agent
            logger.warning(
                "PID %d exists but is not taskpps-agent, cleaning stale pid file %s",
                pid,
                pid_file,
            )

        # 进程不存在或 PID 被复用，清理残留 PID 文件
        await self._ssh_exec(client, f"rm -f {pid_file}")
        return None

    def _get_server_host(self, agent_data: dict | None = None) -> str:
        if agent_data:
            explicit = agent_data.get("server_ws_host", "")
            if explicit:
                return explicit

        settings = __import__("taskpps.config", fromlist=["get_settings"]).get_settings()
        host = settings.server.host

        if host not in ("0.0.0.0", "127.0.0.1", "::1", ""):
            return host

        external_ip = self._get_external_ip()
        if external_ip:
            return external_ip

        import socket

        hostname = socket.gethostname()
        try:
            ip = socket.gethostbyname(hostname)
            if ip not in ("127.0.0.1", "::1"):
                return ip
        except Exception:
            pass
        logger.warning(
            "Server listens on %s but no external IP found. Remote agents may fail to connect. "
            "Set 'server_ws_host' in agent config or use a reachable bind address.",
            host,
        )
        return socket.gethostbyname(socket.gethostname())

    def _get_external_ip(self) -> str | None:
        import socket

        try:
            import netifaces
        except ImportError:
            netifaces = None

        if netifaces is not None:
            try:
                for iface in netifaces.interfaces():
                    if iface.startswith(("lo", "docker", "veth", "br-")):
                        continue
                    addrs = netifaces.ifaddresses(iface)
                    for af in (netifaces.AF_INET,):
                        if af not in addrs:
                            continue
                        for addr_info in addrs[af]:
                            ip = addr_info.get("addr", "")
                            if ip and not ip.startswith("127."):
                                return ip
            except Exception:
                pass

        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            try:
                s.connect(("8.8.8.8", 80))
                ip = s.getsockname()[0]
                if ip and not ip.startswith("127."):
                    return ip
            finally:
                s.close()
        except Exception:
            pass
        return None

    def _get_ws_port(self) -> int:
        try:
            from taskpps.config import get_settings

            settings = get_settings()
            return settings.server.port
        except Exception:
            return 26521

    async def update_deploy(self, agent_id: str, agent_loader: AgentLoader | None = None, credential_loader: CredentialLoader | None = None) -> dict:
        """强制更新部署 agent：重新上传二进制、终止旧进程、重启并等待新握手。"""
        loader = agent_loader or self._agent_loader
        if credential_loader is not None:
            self._credential_loader = credential_loader
        agent_data = loader.get(agent_id)
        if agent_data is None:
            raise AgentBootstrapError(t("Agent not found: {id}", id=agent_id))

        if not agent_data.get("agent_auto_bootstrap", True):
            raise AgentBootstrapError(t("Agent '{id}' has agent_auto_bootstrap disabled", id=agent_id))

        host = agent_data.get("host", "")
        port = agent_data.get("port", 22)
        credential_id = agent_data.get("credential_id", "")

        if not host or host in ("localhost", "127.0.0.1", "::1"):
            raise AgentBootstrapError(t("Update deploy is not supported for local agents"))

        username = None
        password = None
        key_path = None

        if credential_id:
            cred_data = self._credential_loader.get(credential_id)
            if cred_data:
                username = cred_data.get("username")
                password = cred_data.get("password")
                key_path = cred_data.get("key_path")

        if username is None:
            username = agent_data.get("username", "root")

        if not password and not key_path:
            raise AgentBootstrapError(
                t(
                    "No authentication method for agent '{id}' (host={host}). "
                    "Set credential_id with password or key_path in agent config.",
                    id=agent_id,
                    host=host,
                )
            )

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

            server_host = self._get_server_host(agent_data)
            server_port = self._get_ws_port()
            server_url = f"ws://{server_host}:{server_port}/api/ws/agent"

            self._check_server_reachability(ssh, host, server_host, server_port)

            # 1. 强制重新上传二进制（忽略 _check_binary 跳过逻辑）
            logger.info("Force-updating agent binary on %s to %s ...", host, agent_binary_path)
            await self._ensure_remote_dir(ssh, agent_binary_path)
            await self._ensure_remote_dir(ssh, f"{agent_log_dir}/_")
            try:
                await self._deploy_binary(ssh, host, agent_binary_path)
            except Exception as e:
                logger.exception("更新部署: 上传二进制失败(agent=%s, host=%s)", agent_id, host)
                raise AgentBootstrapError(t("上传二进制失败: {error}", error=str(e))) from e
            await self._ssh_exec(ssh, f"chmod 755 {agent_binary_path}")

            # 2. 终止旧进程并清理 PID 文件
            try:
                existing_pid = await self._check_existing_agent(ssh, agent_pid_file)
                if existing_pid:
                    logger.info("Terminating existing agent (PID %d) on %s for update", existing_pid, host)
                    await self._ssh_exec(ssh, f"kill {existing_pid} 2>/dev/null; rm -f {agent_pid_file}")
                    await asyncio.sleep(1)
                else:
                    await self._ssh_exec(ssh, f"rm -f {agent_pid_file}")
            except Exception as e:
                logger.exception("更新部署: 终止旧进程失败(agent=%s)", agent_id)
                raise AgentBootstrapError(t("终止旧进程失败: {error}", error=str(e))) from e

            # 3. 断开旧 WebSocket 连接
            manager = AgentManager.instance()
            await manager.disconnect(agent_id)

            # 4. 启动新 agent 进程
            try:
                pid = await self._start_agent_daemon(
                    ssh, agent_binary_path, agent_log_dir, agent_pid_file, agent_id, agent_secret, server_url, agent_data
                )
            except Exception as e:
                logger.exception("更新部署: 启动新 agent 进程失败(agent=%s)", agent_id)
                raise AgentBootstrapError(t("启动新 agent 进程失败: {error}", error=str(e))) from e
            if pid:
                logger.info("Agent '%s' updated on %s with PID %d", agent_id, host, pid)
        finally:
            await self._ssh_close(ssh)

        # 5. 等待新握手
        deploy_started_at = time.time()
        try:
            await asyncio.wait_for(
                self._wait_for_handshake(manager, agent_id, deploy_started_at),
                timeout=BOOTSTRAP_TIMEOUT,
            )
            logger.info("Agent '%s' update handshake completed", agent_id)
            return {"success": True, "agent_pid": 0}
        except asyncio.TimeoutError as e:
            agent_log_path = f"{agent_log_dir}/agent.log"
            log_tail = ""
            try:
                ssh2 = await self._ssh_connect(host, port, username, password, key_path)
                try:
                    _, log_out, _ = await self._ssh_exec(
                        ssh2, f"tail -n 30 {agent_log_path} 2>/dev/null || echo '(no log file)'"
                    )
                    if log_out.strip():
                        log_tail = log_out.strip()
                finally:
                    await self._ssh_close(ssh2)
            except Exception as log_err:
                log_tail = f"(could not fetch logs: {log_err})"

            error_msg = (
                f"Agent '{agent_id}' update deploy failed to connect to {server_url} "
                f"after {BOOTSTRAP_TIMEOUT}s. Check: "
                f"Verify server is reachable from {host} and not bound to 127.0.0.1. "
                f"Agent log tail:\n{log_tail}"
            )
            raise AgentBootstrapError(error_msg) from e

    async def _wait_for_handshake(self, manager: AgentManager, agent_id: str, since: float) -> None:
        # Issue #70: 检查本次部署后的新连接，而非 is_connected()（有 5 分钟 grace period，
        # 会把残留旧连接误判为成功）。只有 connected_at >= since 才是本次部署产生的新连接。
        while True:
            conn = manager.get_connection(agent_id)
            if conn is not None and conn.connected_at >= since and conn.last_heartbeat > 0:
                return
            await asyncio.sleep(0.5)

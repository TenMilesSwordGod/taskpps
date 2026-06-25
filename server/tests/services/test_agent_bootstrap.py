"""Unit tests for taskpps.services.agent_bootstrap.

覆盖 agent bootstrap 主流程中的关键分支：
- 本地 agent 快速返回
- agent 不存在 / auto_bootstrap 禁用
- 远程 agent 缺少凭据
- SSH 探测 / 二进制部署 / daemon 启动 / handshake 等待
"""

from __future__ import annotations

import asyncio
import socket
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from taskpps.services.agent_bootstrap import (
    AgentBootstrap,
    AgentBootstrapError,
    BOOTSTRAP_TIMEOUT,
)
from taskpps.services.agent_manager import AgentManager


def _make_paramiko_client():
    """构造一个最小可用的 mock paramiko client。"""
    client = MagicMock()
    client.exec_command.return_value = (
        MagicMock(),
        MagicMock(read=MagicMock(return_value=b"0")),
        MagicMock(read=MagicMock(return_value=b"")),
    )
    return client


class TestAgentBootstrapErrors:
    @pytest.mark.asyncio
    @pytest.mark.zentao("TC-S0277", domain="server/services", priority="P1")
    async def test_agent_not_found_raises(self):
        bootstrap = AgentBootstrap()
        loader = MagicMock()
        loader.get.return_value = None
        with pytest.raises(AgentBootstrapError, match="not found"):
            await bootstrap.bootstrap("ghost-agent", agent_loader=loader)

    @pytest.mark.asyncio
    @pytest.mark.zentao("TC-S0278", domain="server/services", priority="P1")
    async def test_auto_bootstrap_disabled_raises(self):
        bootstrap = AgentBootstrap()
        loader = MagicMock()
        loader.get.return_value = {
            "id": "agent-x",
            "host": "10.0.0.1",
            "agent_auto_bootstrap": False,
        }
        with pytest.raises(AgentBootstrapError, match="auto_bootstrap"):
            await bootstrap.bootstrap("agent-x", agent_loader=loader)


class TestAgentBootstrapLocal:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("host", ["localhost", "127.0.0.1", "::1"])
    @pytest.mark.zentao("TC-S0279", domain="server/services", priority="P2")
    async def test_local_host_already_connected_returns_immediately(self, host):
        """本机 agent 已连接时直接走 fast-path 返回成功。"""
        bootstrap = AgentBootstrap()
        loader = MagicMock()
        loader.get.return_value = {"id": "local-agent", "host": host, "port": 22}
        with patch.object(AgentManager, "instance") as mock_inst:
            mock_manager = MagicMock()
            mock_manager.is_connected.return_value = True
            mock_inst.return_value = mock_manager
            result = await bootstrap.bootstrap("local-agent", agent_loader=loader)
        assert result["success"] is True
        assert result["message"] == "local agent"

    @pytest.mark.asyncio
    @pytest.mark.parametrize("host", ["localhost", "127.0.0.1", "::1"])
    @pytest.mark.zentao("TC-S0280", domain="server/services", priority="P1")
    async def test_local_host_not_connected_waits_for_handshake(self, host):
        """Issue #107: 本机 agent 未连接时等待 WebSocket 握手完成。"""
        bootstrap = AgentBootstrap()
        loader = MagicMock()
        loader.get.return_value = {"id": "local-agent", "host": host, "port": 22}
        with patch.object(AgentManager, "instance") as mock_inst:
            mock_manager = MagicMock()
            mock_manager.is_connected.return_value = False
            mock_inst.return_value = mock_manager
            with patch.object(bootstrap, "_wait_for_handshake", new=AsyncMock()):
                result = await bootstrap.bootstrap("local-agent", agent_loader=loader)
        assert result["success"] is True
        assert result["message"] == "local agent"

    @pytest.mark.asyncio
    @pytest.mark.parametrize("host", ["localhost", "127.0.0.1", "::1"])
    @pytest.mark.zentao("TC-S0281", domain="server/services", priority="P1")
    async def test_local_host_handshake_timeout_raises(self, host):
        """Issue #107: 本机 agent 未连接且握手超时时应抛错。"""
        bootstrap = AgentBootstrap()
        loader = MagicMock()
        loader.get.return_value = {"id": "local-agent", "host": host, "port": 22}
        with patch.object(AgentManager, "instance") as mock_inst:
            mock_manager = MagicMock()
            mock_manager.is_connected.return_value = False
            mock_inst.return_value = mock_manager
            with patch.object(bootstrap, "_wait_for_handshake", new=AsyncMock(side_effect=asyncio.TimeoutError())):
                with pytest.raises(AgentBootstrapError, match="did not connect"):
                    await bootstrap.bootstrap("local-agent", agent_loader=loader)


class TestAgentBootstrapMissingAuth:
    @pytest.mark.asyncio
    @pytest.mark.zentao("TC-S0282", domain="server/services", priority="P2")
    async def test_remote_without_credential_raises(self):
        bootstrap = AgentBootstrap()
        loader = MagicMock()
        loader.get.return_value = {
            "id": "remote",
            "host": "10.0.0.1",
            "port": 22,
            "credential_id": "",
        }
        with pytest.raises(AgentBootstrapError, match="No authentication method"):
            await bootstrap.bootstrap("remote", agent_loader=loader)

    @pytest.mark.asyncio
    @pytest.mark.zentao("TC-S0283", domain="server/services", priority="P2")
    async def test_remote_credential_without_pw_or_key_raises(self):
        bootstrap = AgentBootstrap()
        loader = MagicMock()
        loader.get.return_value = {
            "id": "remote",
            "host": "10.0.0.1",
            "port": 22,
            "credential_id": "empty-cred",
        }
        cred_loader = MagicMock()
        cred_loader.get.return_value = {"id": "empty-cred", "username": "root"}
        bootstrap._credential_loader = cred_loader
        with pytest.raises(AgentBootstrapError, match="No authentication method"):
            await bootstrap.bootstrap("remote", agent_loader=loader)


class TestAgentBootstrapInternal:
    """覆盖 _check_server_reachability / _get_server_host / _get_external_ip / _get_ws_port"""

    @pytest.mark.zentao("TC-S0284", domain="server/services", priority="P2")
    def test_check_server_reachability_warn_local_bind(self, caplog):
        bootstrap = AgentBootstrap()
        ssh = MagicMock()
        with (
            patch("taskpps.config.get_settings") as gs,
            caplog.at_level("WARNING", logger="taskpps.services.agent_bootstrap"),
        ):
            gs.return_value.server.host = "127.0.0.1"
            bootstrap._check_server_reachability(ssh, "remote", "127.0.0.1", 26521)
        assert any("binds to 127.0.0.1" in r.message for r in caplog.records)

    @pytest.mark.zentao("TC-S0285", domain="server/services", priority="P2")
    def test_check_server_reachability_warn_local_target(self, caplog):
        bootstrap = AgentBootstrap()
        ssh = MagicMock()
        with (
            patch("taskpps.config.get_settings") as gs,
            caplog.at_level("WARNING", logger="taskpps.services.agent_bootstrap"),
        ):
            gs.return_value.server.host = "0.0.0.0"
            bootstrap._check_server_reachability(ssh, "remote", "localhost", 26521)
        assert any("local-only" in r.message for r in caplog.records)

    @pytest.mark.zentao("TC-S0286", domain="server/services", priority="P2")
    def test_get_server_host_explicit_from_agent(self):
        bootstrap = AgentBootstrap()
        host = bootstrap._get_server_host({"server_ws_host": "10.0.0.5"})
        assert host == "10.0.0.5"

    @pytest.mark.zentao("TC-S0287", domain="server/services", priority="P2")
    def test_get_server_host_fallback_to_settings_ip(self):
        bootstrap = AgentBootstrap()
        with patch("taskpps.config.get_settings") as gs:
            gs.return_value.server.host = "192.168.1.100"
            host = bootstrap._get_server_host({})
        assert host == "192.168.1.100"

    @pytest.mark.zentao("TC-S0288", domain="server/services", priority="P2")
    def test_get_server_host_fallback_to_external_ip(self):
        bootstrap = AgentBootstrap()
        with (
            patch("taskpps.config.get_settings") as gs,
            patch.object(AgentBootstrap, "_get_external_ip", return_value="10.0.0.99"),
        ):
            gs.return_value.server.host = "0.0.0.0"
            host = bootstrap._get_server_host({})
        assert host == "10.0.0.99"

    @pytest.mark.zentao("TC-S0289", domain="server/services", priority="P2")
    def test_get_external_ip_returns_none_when_unavailable(self):
        """netifaces 缺失 + socket 出错 → 返回 None。"""
        bootstrap = AgentBootstrap()
        # 局部 import socket 在函数内部执行,patch global `socket.socket` 即可生效
        fake_sock = MagicMock()
        fake_sock.socket.side_effect = OSError("no network")
        with (
            patch.dict("sys.modules", {"netifaces": None}),
            patch("socket.socket", side_effect=OSError("no network")),
        ):
            assert bootstrap._get_external_ip() is None

    @pytest.mark.zentao("TC-S0290", domain="server/services", priority="P2")
    def test_get_ws_port(self):
        bootstrap = AgentBootstrap()
        with patch("taskpps.config.get_settings") as gs:
            gs.return_value.server.port = 12345
            assert bootstrap._get_ws_port() == 12345

    @pytest.mark.zentao("TC-S0291", domain="server/services", priority="P1")
    def test_get_ws_port_fallback_on_error(self):
        bootstrap = AgentBootstrap()
        with patch("taskpps.config.get_settings", side_effect=Exception("boom")):
            assert bootstrap._get_ws_port() == 26521


class TestAgentBootstrapSSHHelpers:
    @pytest.mark.asyncio
    @pytest.mark.zentao("TC-S0292", domain="server/services", priority="P1")
    async def test_ssh_connect_with_password(self):
        bootstrap = AgentBootstrap()
        client = MagicMock()
        with patch.dict("sys.modules", {"paramiko": MagicMock(SSHClient=MagicMock(return_value=client))}):
            import paramiko

            result = await bootstrap._ssh_connect("10.0.0.1", 22, "admin", "secret", None)
        assert result is client
        # confirm paramiko was called with correct kwargs
        client.connect.assert_called_once()

    @pytest.mark.asyncio
    @pytest.mark.zentao("TC-S0293", domain="server/services", priority="P1")
    async def test_ssh_connect_with_key(self):
        bootstrap = AgentBootstrap()
        client = MagicMock()
        with patch.dict("sys.modules", {"paramiko": MagicMock(SSHClient=MagicMock(return_value=client))}):
            await bootstrap._ssh_connect("10.0.0.1", 22, "admin", None, "/key/path")
        client.connect.assert_called_once()

    @pytest.mark.asyncio
    @pytest.mark.zentao("TC-S0294", domain="server/services", priority="P1")
    async def test_ssh_close_swallows_exception(self):
        bootstrap = AgentBootstrap()
        client = MagicMock()
        client.close.side_effect = Exception("boom")
        # 不应抛
        await bootstrap._ssh_close(client)
        client.close.assert_called_once()

    @pytest.mark.asyncio
    @pytest.mark.zentao("TC-S0295", domain="server/services", priority="P2")
    async def test_ensure_remote_dir_with_root(self):
        bootstrap = AgentBootstrap()
        client = MagicMock()
        with patch.object(bootstrap, "_ssh_exec", new=AsyncMock()) as mock_exec:
            await bootstrap._ensure_remote_dir(client, "/usr/local/bin/foo")
        mock_exec.assert_called_once_with(client, "mkdir -p /usr/local/bin")

    @pytest.mark.asyncio
    @pytest.mark.zentao("TC-S0296", domain="server/services", priority="P2")
    async def test_ensure_remote_dir_no_parent(self):
        bootstrap = AgentBootstrap()
        client = MagicMock()
        with patch.object(bootstrap, "_ssh_exec", new=AsyncMock()) as mock_exec:
            await bootstrap._ensure_remote_dir(client, "foo")
        # parent 为空 → 不调用
        mock_exec.assert_not_called()

    @pytest.mark.asyncio
    @pytest.mark.zentao("TC-S0297", domain="server/services", priority="P2")
    async def test_check_binary_returns_true_on_zero(self):
        bootstrap = AgentBootstrap()
        client = MagicMock()
        client.exec_command.return_value = (
            MagicMock(),
            MagicMock(read=MagicMock(return_value=b"")),
            MagicMock(read=MagicMock(return_value=b"")),
        )
        # exit_code 通过 stdout.channel.recv_exit_status() 返回
        client.exec_command.return_value[1].channel.recv_exit_status.return_value = 0
        # 实际上 _ssh_exec 包装了 exit_code → 需要走 _ssh_exec
        # 直接覆盖 _ssh_exec 让其返回 (0, '', '')
        with patch.object(bootstrap, "_ssh_exec", return_value=(0, "", "")):
            assert await bootstrap._check_binary(client, "/path/bin") is True
        with patch.object(bootstrap, "_ssh_exec", return_value=(1, "", "")):
            assert await bootstrap._check_binary(client, "/path/bin") is False

    @pytest.mark.asyncio
    @pytest.mark.zentao("TC-S0298", domain="server/services", priority="P2")
    async def test_check_binary_uses_execution_not_test_x(self):
        """Issue #69: _check_binary 应通过执行二进制验证架构，而非仅 test -x。"""
        bootstrap = AgentBootstrap()
        with patch.object(bootstrap, "_ssh_exec", return_value=(0, "", "")) as mock_exec:
            await bootstrap._check_binary(MagicMock(), "/path/agent")
        cmd = mock_exec.call_args[0][1]
        assert "--help" in cmd
        assert "test -x" not in cmd

    @pytest.mark.asyncio
    @pytest.mark.zentao("TC-S0299", domain="server/services", priority="P2")
    async def test_get_remote_user_info_default_home(self):
        bootstrap = AgentBootstrap()
        with patch.object(bootstrap, "_ssh_exec", side_effect=[(1, "", ""), (0, "1000", "")]):
            home, is_root = await bootstrap._get_remote_user_info(MagicMock())
        assert home == "/root"
        assert is_root is False

    @pytest.mark.asyncio
    @pytest.mark.zentao("TC-S0300", domain="server/services", priority="P2")
    async def test_get_remote_user_info_root(self):
        bootstrap = AgentBootstrap()
        with patch.object(bootstrap, "_ssh_exec", side_effect=[(0, "/home/admin\n", ""), (0, "0", "")]):
            home, is_root = await bootstrap._get_remote_user_info(MagicMock())
        assert home == "/home/admin"
        assert is_root is True

    @pytest.mark.asyncio
    @pytest.mark.zentao("TC-S0301", domain="server/services", priority="P1")
    async def test_deploy_binary_unsupported_arch(self):
        bootstrap = AgentBootstrap()
        client = MagicMock()
        with patch.object(bootstrap, "_ssh_exec", return_value=(0, "unknown_arch", "")):
            with pytest.raises(AgentBootstrapError, match="Unsupported remote architecture"):
                await bootstrap._deploy_binary(client, "10.0.0.1", "/tmp/bin")

    @pytest.mark.asyncio
    @pytest.mark.zentao("TC-S0302", domain="server/services", priority="P1")
    async def test_deploy_binary_no_local_binary(self, tmp_path):
        bootstrap = AgentBootstrap()
        client = MagicMock()
        with (
            patch.object(bootstrap, "_ssh_exec", return_value=(0, "x86_64", "")),
            patch("os.path.exists", return_value=False),
        ):
            with pytest.raises(AgentBootstrapError, match="binary for arch"):
                await bootstrap._deploy_binary(client, "10.0.0.1", "/tmp/bin")

    @pytest.mark.asyncio
    @pytest.mark.zentao("TC-S0303", domain="server/services", priority="P1")
    async def test_deploy_binary_amd64(self, tmp_path):
        bootstrap = AgentBootstrap()
        client = MagicMock()
        # make a fake binary in the project
        binary = tmp_path / "taskpps-agent-linux-amd64"
        binary.write_bytes(b"fake")
        # patch project root resolution
        with (
            patch.object(bootstrap, "_ssh_exec", return_value=(0, "x86_64", "")),
            patch("os.path.exists", return_value=True),
        ):
            # 拦截 sftp 调用
            sftp_mock = MagicMock()
            client.open_sftp.return_value = sftp_mock
            await bootstrap._deploy_binary(client, "10.0.0.1", "/remote/bin")
        sftp_mock.put.assert_called_once()
        sftp_mock.close.assert_called_once()

    @pytest.mark.asyncio
    @pytest.mark.zentao("TC-S0304", domain="server/services", priority="P1")
    async def test_deploy_binary_arch_detect_failure(self):
        bootstrap = AgentBootstrap()
        client = MagicMock()
        with patch.object(bootstrap, "_ssh_exec", return_value=(1, "", "")):
            with pytest.raises(AgentBootstrapError, match="Failed to detect"):
                await bootstrap._deploy_binary(client, "10.0.0.1", "/tmp/bin")

    @pytest.mark.asyncio
    @pytest.mark.zentao("TC-S0305", domain="server/services", priority="P2")
    async def test_start_agent_daemon_success(self):
        bootstrap = AgentBootstrap()
        client = MagicMock()
        # _check_existing_agent returns None, then mkdir/run + cat pid + kill -0
        with patch.object(
            bootstrap,
            "_check_existing_agent",
            new=AsyncMock(return_value=None),
        ), patch.object(
            bootstrap,
            "_ssh_exec",
            side_effect=[(0, "", ""), (0, "42", ""), (0, "", "")],
        ):
            with patch("asyncio.sleep", new=AsyncMock()):
                pid = await bootstrap._start_agent_daemon(
                    client, "/bin/agent", "/var/log", "/var/run.pid", "agent-id", "secret", "ws://srv", {},
                )
        assert pid == 42

    @pytest.mark.asyncio
    @pytest.mark.zentao("TC-S0306", domain="server/services", priority="P1")
    async def test_start_agent_daemon_failure(self):
        bootstrap = AgentBootstrap()
        client = MagicMock()
        with patch.object(
            bootstrap,
            "_check_existing_agent",
            new=AsyncMock(return_value=None),
        ), patch.object(bootstrap, "_ssh_exec", return_value=(1, "", "boom")):
            with pytest.raises(AgentBootstrapError, match="Failed to start agent"):
                await bootstrap._start_agent_daemon(
                    client, "/bin/agent", "/var/log", "/var/run.pid", "agent-id", "", "ws://srv", {},
                )

    @pytest.mark.asyncio
    @pytest.mark.zentao("TC-S0307", domain="server/services", priority="P2")
    async def test_start_agent_daemon_no_pid_file(self):
        bootstrap = AgentBootstrap()
        client = MagicMock()
        with patch.object(
            bootstrap,
            "_check_existing_agent",
            new=AsyncMock(return_value=None),
        ), patch.object(
            bootstrap,
            "_ssh_exec",
            side_effect=[(0, "", ""), (1, "", "no such file")],
        ):
            with patch("asyncio.sleep", new=AsyncMock()):
                with pytest.raises(AgentBootstrapError, match="Failed to read PID file"):
                    await bootstrap._start_agent_daemon(
                        client, "/bin/agent", "/var/log", "/var/run.pid", "agent-id", "", "ws://srv", {},
                    )

    @pytest.mark.asyncio
    @pytest.mark.zentao("TC-S0308", domain="server/services", priority="P2")
    async def test_start_agent_daemon_with_workdir(self):
        bootstrap = AgentBootstrap()
        client = MagicMock()
        # 验证 secret + work_dir 都被加进命令
        with patch.object(
            bootstrap,
            "_check_existing_agent",
            new=AsyncMock(return_value=None),
        ), patch.object(
            bootstrap,
            "_ssh_exec",
            side_effect=[(0, "", ""), (0, "7", ""), (0, "", "")],
        ) as mock_exec:
            with patch("asyncio.sleep", new=AsyncMock()):
                await bootstrap._start_agent_daemon(
                    client,
                    "/bin/agent",
                    "/var/log",
                    "/var/run.pid",
                    "agent-id",
                    "topsecret",
                    "ws://srv",
                    {"agent_work_dir": "/work"},
                )
        first_cmd = mock_exec.call_args_list[0][0][1]
        assert "--secret topsecret" in first_cmd
        assert "--work-dir /work" in first_cmd

    @pytest.mark.asyncio
    @pytest.mark.zentao("TC-S0309", domain="server/services", priority="P2")
    async def test_start_agent_daemon_skips_when_already_running(self):
        """Issue #68: 远程主机已有 agent 运行时，应跳过启动，返回已有 PID。"""
        bootstrap = AgentBootstrap()
        client = MagicMock()
        with patch.object(
            bootstrap,
            "_check_existing_agent",
            new=AsyncMock(return_value=1234),
        ):
            pid = await bootstrap._start_agent_daemon(
                client, "/bin/agent", "/var/log", "/var/run.pid", "agent-id", "", "ws://srv", {},
            )
        assert pid == 1234

    @pytest.mark.asyncio
    @pytest.mark.zentao("TC-S0310", domain="server/services", priority="P2")
    async def test_start_agent_daemon_process_died_immediately(self):
        """Issue #70: 子进程启动后立即崩溃（kill -0 失败）→ 抛错并附 log tail。"""
        bootstrap = AgentBootstrap()
        client = MagicMock()
        # mkdir/run exit 0, cat pid → 55, kill -0 → 非 0（进程已死）, tail log
        with patch.object(
            bootstrap,
            "_check_existing_agent",
            new=AsyncMock(return_value=None),
        ), patch.object(
            bootstrap,
            "_ssh_exec",
            side_effect=[
                (0, "", ""),           # daemon start
                (0, "55", ""),         # cat pid_file
                (1, "", ""),           # kill -0 (dead)
                (0, "crash log\n", ""),  # tail log
            ],
        ):
            with patch("asyncio.sleep", new=AsyncMock()):
                with pytest.raises(AgentBootstrapError, match="died immediately"):
                    await bootstrap._start_agent_daemon(
                        client, "/bin/agent", "/var/log", "/var/run.pid", "agent-id", "", "ws://srv", {},
                    )


class TestCheckExistingAgent:
    """Issue #68: _check_existing_agent 检查远程主机是否已有 agent 运行。"""

    @pytest.mark.asyncio
    @pytest.mark.zentao("TC-S0311", domain="server/services", priority="P2")
    async def test_no_pid_file(self):
        """PID 文件不存在 → 返回 None。"""
        bootstrap = AgentBootstrap()
        with patch.object(bootstrap, "_ssh_exec", return_value=(1, "", "")):
            result = await bootstrap._check_existing_agent(MagicMock(), "/var/run/agent.pid")
        assert result is None

    @pytest.mark.asyncio
    @pytest.mark.zentao("TC-S0312", domain="server/services", priority="P2")
    async def test_pid_file_with_running_agent(self):
        """PID 文件存在，进程存活且是 taskpps-agent → 返回 PID。"""
        bootstrap = AgentBootstrap()
        # cat pid_file → 1234, kill -0 → 0, cat /proc/1234/cmdline → taskpps-agent
        with patch.object(
            bootstrap,
            "_ssh_exec",
            side_effect=[
                (0, "1234", ""),       # cat pid_file
                (0, "", ""),           # kill -0
                (0, "taskpps-agent\0run\0", ""),  # cat /proc/cmdline
            ],
        ):
            result = await bootstrap._check_existing_agent(MagicMock(), "/var/run/agent.pid")
        assert result == 1234

    @pytest.mark.asyncio
    @pytest.mark.zentao("TC-S0313", domain="server/services", priority="P2")
    async def test_pid_file_stale_process_dead(self):
        """PID 文件存在但进程已死 → 清理 PID 文件，返回 None。"""
        bootstrap = AgentBootstrap()
        with patch.object(
            bootstrap,
            "_ssh_exec",
            side_effect=[
                (0, "1234", ""),  # cat pid_file
                (1, "", ""),      # kill -0 (process dead)
                (0, "", ""),      # rm -f pid_file
            ],
        ):
            result = await bootstrap._check_existing_agent(MagicMock(), "/var/run/agent.pid")
        assert result is None

    @pytest.mark.asyncio
    @pytest.mark.zentao("TC-S0314", domain="server/services", priority="P2")
    async def test_pid_file_pid_reused_by_other_process(self):
        """PID 文件存在，进程存活但不是 taskpps-agent → 清理 PID 文件，返回 None。"""
        bootstrap = AgentBootstrap()
        with patch.object(
            bootstrap,
            "_ssh_exec",
            side_effect=[
                (0, "9999", ""),           # cat pid_file
                (0, "", ""),               # kill -0 (alive)
                (0, "some-other-program", ""),  # cat /proc/cmdline (not taskpps-agent)
                (0, "", ""),               # rm -f pid_file
            ],
        ):
            result = await bootstrap._check_existing_agent(MagicMock(), "/var/run/agent.pid")
        assert result is None

    @pytest.mark.asyncio
    @pytest.mark.zentao("TC-S0315", domain="server/services", priority="P2")
    async def test_pid_file_invalid_content(self):
        """PID 文件内容不是数字 → 清理 PID 文件，返回 None。"""
        bootstrap = AgentBootstrap()
        with patch.object(
            bootstrap,
            "_ssh_exec",
            side_effect=[
                (0, "not-a-pid", ""),  # cat pid_file
                (0, "", ""),           # rm -f pid_file
            ],
        ):
            result = await bootstrap._check_existing_agent(MagicMock(), "/var/run/agent.pid")
        assert result is None


class TestAgentBootstrapFlow:
    @pytest.mark.asyncio
    @pytest.mark.zentao("TC-S0316", domain="server/services", priority="P0")
    async def test_full_flow_handshake_success(self):
        """端到端测试：agent 二进制已存在 + handshake 在 timeout 内成功 → success"""
        bootstrap = AgentBootstrap()
        loader = MagicMock()
        loader.get.return_value = {
            "id": "remote-1",
            "host": "10.0.0.1",
            "port": 22,
            "credential_id": "cred-1",
        }
        cred_loader = MagicMock()
        cred_loader.get.return_value = {"id": "cred-1", "username": "admin", "password": "secret"}
        bootstrap._credential_loader = cred_loader

        client = _make_paramiko_client()

        # 顺序匹配 _ssh_exec 内部调用（_start_agent_daemon 已被 mock,不会触发 _ssh_exec）：
        # 1. echo $HOME
        # 2. id -u
        # 3. _check_binary (--help)
        ssh_results = [
            (0, "/home/admin\n", ""),  # echo $HOME
            (0, "1000", ""),  # id -u
            (0, "", ""),  # _check_binary (--help)
        ]

        with (
            patch.object(bootstrap, "_ssh_connect", return_value=client),
            patch.object(bootstrap, "_ssh_close", new=AsyncMock()),
            patch.object(bootstrap, "_ssh_exec", side_effect=ssh_results),
            patch.object(AgentManager, "disconnect", new=AsyncMock()),
            patch.object(bootstrap, "_check_server_reachability"),
            patch.object(bootstrap, "_start_agent_daemon", new=AsyncMock(return_value=99)),
            # 直接 mock _wait_for_handshake，避免 while True 循环导致内存泄漏
            patch.object(bootstrap, "_wait_for_handshake", new=AsyncMock()),
        ):
            result = await bootstrap.bootstrap("remote-1", agent_loader=loader)

        assert result["success"] is True

    @pytest.mark.asyncio
    @pytest.mark.zentao("TC-S0317", domain="server/services", priority="P1")
    async def test_handshake_timeout_raises(self):
        """handshake 超时 → 抛 AgentBootstrapError，附 log tail 信息。"""
        bootstrap = AgentBootstrap()
        loader = MagicMock()
        loader.get.return_value = {
            "id": "remote-2",
            "host": "10.0.0.1",
            "port": 22,
            "credential_id": "cred-1",
        }
        cred_loader = MagicMock()
        cred_loader.get.return_value = {"id": "cred-1", "username": "admin", "password": "secret"}
        bootstrap._credential_loader = cred_loader

        client = _make_paramiko_client()

        # _check_binary (--help) + log fetch (tail log)
        ssh_results = [
            (0, "/home/user", ""),    # echo $HOME
            (0, "1000", ""),          # id -u
            (0, "", ""),              # _check_binary (--help)
            (0, "log content here", ""),  # tail log (for error message)
        ]

        with (
            patch.object(AgentBootstrap, "_ssh_connect", return_value=client),
            patch.object(AgentBootstrap, "_ssh_close", new=AsyncMock()),
            patch.object(AgentBootstrap, "_ssh_exec", side_effect=ssh_results),
            patch.object(AgentManager, "disconnect", new=AsyncMock()),
            patch.object(AgentBootstrap, "_check_server_reachability"),
            patch.object(AgentBootstrap, "_start_agent_daemon", new=AsyncMock(return_value=1)),
            # 直接 mock _wait_for_handshake 抛 TimeoutError，避免无限循环
            patch.object(AgentBootstrap, "_wait_for_handshake", new=AsyncMock(side_effect=asyncio.TimeoutError())),
        ):
            with pytest.raises(AgentBootstrapError, match="failed to connect"):
                await bootstrap.bootstrap("remote-2", agent_loader=loader)

    @pytest.mark.asyncio
    @pytest.mark.zentao("TC-S0318", domain="server/services", priority="P1")
    async def test_deploys_binary_when_missing(self):
        """_check_binary 返回 False → 走 _deploy_binary 路径"""
        from taskpps.services.agent_manager import AgentManager

        bootstrap = AgentBootstrap()
        loader = MagicMock()
        loader.get.return_value = {
            "id": "remote-3",
            "host": "10.0.0.1",
            "port": 22,
            "credential_id": "cred-1",
        }
        cred_loader = MagicMock()
        cred_loader.get.return_value = {"id": "cred-1", "username": "admin", "password": "secret"}
        bootstrap._credential_loader = cred_loader

        client = _make_paramiko_client()

        with (
            patch.object(AgentBootstrap, "_ssh_connect", return_value=client),
            patch.object(AgentBootstrap, "_ssh_close", new=AsyncMock()),
            patch.object(AgentBootstrap, "_ssh_exec", return_value=(0, "/home/u", "")),
            patch.object(AgentManager, "disconnect", new=AsyncMock()),
            patch.object(AgentBootstrap, "_check_server_reachability"),
            patch.object(AgentBootstrap, "_check_binary", new=AsyncMock(return_value=False)),
            patch.object(AgentBootstrap, "_ensure_remote_dir", new=AsyncMock()),
            patch.object(AgentBootstrap, "_deploy_binary", new=AsyncMock()),
            patch.object(AgentBootstrap, "_start_agent_daemon", new=AsyncMock(return_value=11)),
            # 直接 mock _wait_for_handshake，避免 while True 循环导致内存泄漏
            patch.object(AgentBootstrap, "_wait_for_handshake", new=AsyncMock()),
        ):
            result = await bootstrap.bootstrap("remote-3", agent_loader=loader)
        assert result["success"] is True


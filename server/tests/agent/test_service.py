from unittest.mock import MagicMock, patch

from taskpps.services.agent_service import AgentService, _match_file_filter


def _make_agent_data(
    agent_id="test-agent",
    host="10.0.0.1",
    port=22,
    credential_id=None,
    username="root",
    agent_type="ssh-username-password",
):
    return {
        "id": agent_id,
        "name": f"Test Agent {agent_id}",
        "type": agent_type,
        "host": host,
        "port": port,
        "username": username,
        "credential_id": credential_id,
        "_source_file": "agents/test.yaml",
    }


def _make_credential_data(cred_id="test-cred", username="admin", password=None, key_path=None):
    data = {"id": cred_id, "username": username}
    if password:
        data["password"] = password
    if key_path:
        data["key_path"] = key_path
    return data


def _patch_paramiko():
    mock_paramiko = MagicMock()
    mock_client = MagicMock()
    mock_paramiko.SSHClient.return_value = mock_client
    mock_paramiko.AutoAddPolicy.return_value = MagicMock()
    mock_paramiko.AuthenticationException = type("AuthenticationException", (Exception,), {})
    return mock_paramiko, mock_client


class TestCheckOne:
    @pytest.mark.zentao("TC-S0438", domain="server/agent", priority="P2")
    def test_local_agent_ready(self):
        svc = AgentService()
        agent = _make_agent_data(host="localhost")
        result = svc._check_one(agent, 5)
        assert result.status == "ready"
        assert result.agent_id == "test-agent"

    @pytest.mark.zentao("TC-S0439", domain="server/agent", priority="P2")
    def test_local_agent_127(self):
        svc = AgentService()
        agent = _make_agent_data(host="127.0.0.1")
        result = svc._check_one(agent, 5)
        assert result.status == "ready"

    @pytest.mark.zentao("TC-S0440", domain="server/agent", priority="P2")
    def test_local_agent_empty_host(self):
        svc = AgentService()
        agent = _make_agent_data(host="")
        result = svc._check_one(agent, 5)
        assert result.status == "ready"

    @pytest.mark.zentao("TC-S0441", domain="server/agent", priority="P2")
    def test_tcp_connected_no_credential(self):
        svc = AgentService()
        agent = _make_agent_data(host="10.0.0.1", credential_id=None)
        with patch("taskpps.services.agent_service.socket") as mock_socket:
            mock_sock = MagicMock()
            mock_socket.create_connection.return_value = mock_sock
            result = svc._check_one(agent, 5)
        assert result.status == "connected"
        assert result.agent_id == "test-agent"

    @pytest.mark.zentao("TC-S0442", domain="server/agent", priority="P1")
    def test_tcp_timeout(self):
        svc = AgentService()
        agent = _make_agent_data(host="10.0.0.1")
        with patch("taskpps.services.agent_service.socket") as mock_socket:
            mock_socket.create_connection.side_effect = TimeoutError()
            result = svc._check_one(agent, 5)
        assert result.status == "failed"
        assert "timed out" in result.error

    @pytest.mark.zentao("TC-S0443", domain="server/agent", priority="P2")
    def test_tcp_connection_refused(self):
        svc = AgentService()
        agent = _make_agent_data(host="10.0.0.1")
        with patch("taskpps.services.agent_service.socket") as mock_socket:
            mock_socket.create_connection.side_effect = ConnectionRefusedError("Connection refused")
            result = svc._check_one(agent, 5)
        assert result.status == "failed"
        assert "Connection refused" in result.error


class TestCheckSshAuth:
    @pytest.mark.zentao("TC-S0444", domain="server/agent", priority="P1")
    def test_credential_not_found(self):
        svc = AgentService()
        agent = _make_agent_data(host="10.0.0.1", credential_id="nonexistent-cred")
        with patch.object(svc._loader, "resolve_credential", return_value=None):
            result = svc._check_ssh_auth(agent, 5)
        assert result is not None
        assert result.status == "failed"
        assert "nonexistent-cred" in result.error

    @pytest.mark.zentao("TC-S0445", domain="server/agent", priority="P2")
    def test_credential_no_password_no_key(self):
        svc = AgentService()
        agent = _make_agent_data(host="10.0.0.1", credential_id="bad-cred")
        cred = _make_credential_data(cred_id="bad-cred", username="admin")
        with patch.object(svc._loader, "resolve_credential", return_value=cred):
            result = svc._check_ssh_auth(agent, 5)
        assert result is not None
        assert result.status == "failed"
        assert "no password or key_path" in result.error

    @pytest.mark.zentao("TC-S0446", domain="server/agent", priority="P2")
    def test_auth_success_with_password(self):
        svc = AgentService()
        agent = _make_agent_data(host="10.0.0.1", credential_id="test-cred")
        cred = _make_credential_data(cred_id="test-cred", username="admin", password="secret")
        mock_paramiko, _mock_client = _patch_paramiko()
        with (
            patch.object(svc._loader, "resolve_credential", return_value=cred),
            patch.dict("sys.modules", {"paramiko": mock_paramiko}),
        ):
            result = svc._check_ssh_auth(agent, 5)
        assert result is None

    @pytest.mark.zentao("TC-S0447", domain="server/agent", priority="P2")
    def test_auth_success_with_key(self):
        svc = AgentService()
        agent = _make_agent_data(host="10.0.0.1", credential_id="test-cred")
        cred = _make_credential_data(cred_id="test-cred", username="admin", key_path="/path/to/key")
        mock_paramiko, _mock_client = _patch_paramiko()
        with (
            patch.object(svc._loader, "resolve_credential", return_value=cred),
            patch.dict("sys.modules", {"paramiko": mock_paramiko}),
        ):
            result = svc._check_ssh_auth(agent, 5)
        assert result is None

    @pytest.mark.zentao("TC-S0448", domain="server/agent", priority="P1")
    def test_auth_failure_wrong_password(self):
        svc = AgentService()
        agent = _make_agent_data(host="10.0.0.1", credential_id="wrong-cred")
        cred = _make_credential_data(cred_id="wrong-cred", username="admin", password="wrong")
        mock_paramiko, mock_client = _patch_paramiko()
        mock_client.connect.side_effect = mock_paramiko.AuthenticationException("Auth failed")
        with (
            patch.object(svc._loader, "resolve_credential", return_value=cred),
            patch.dict("sys.modules", {"paramiko": mock_paramiko}),
        ):
            result = svc._check_ssh_auth(agent, 5)
        assert result is not None
        assert result.status == "failed"
        assert "Authentication failed" in result.error

    @pytest.mark.zentao("TC-S0449", domain="server/agent", priority="P1")
    def test_auth_failure_wrong_key(self):
        svc = AgentService()
        agent = _make_agent_data(host="10.0.0.1", credential_id="wrong-key-cred")
        cred = _make_credential_data(cred_id="wrong-key-cred", username="admin", key_path="/bad/key")
        mock_paramiko, mock_client = _patch_paramiko()
        mock_client.connect.side_effect = mock_paramiko.AuthenticationException("Invalid key")
        with (
            patch.object(svc._loader, "resolve_credential", return_value=cred),
            patch.dict("sys.modules", {"paramiko": mock_paramiko}),
        ):
            result = svc._check_ssh_auth(agent, 5)
        assert result is not None
        assert result.status == "failed"
        assert "Authentication failed" in result.error

    @pytest.mark.zentao("TC-S0450", domain="server/agent", priority="P1")
    def test_ssh_connection_error(self):
        svc = AgentService()
        agent = _make_agent_data(host="10.0.0.1", credential_id="test-cred")
        cred = _make_credential_data(cred_id="test-cred", username="admin", password="secret")
        mock_paramiko, mock_client = _patch_paramiko()
        mock_client.connect.side_effect = Exception("Network error")
        with (
            patch.object(svc._loader, "resolve_credential", return_value=cred),
            patch.dict("sys.modules", {"paramiko": mock_paramiko}),
        ):
            result = svc._check_ssh_auth(agent, 5)
        assert result is not None
        assert result.status == "failed"
        assert "SSH auth check failed" in result.error


class TestCheckOneWithCredential:
    @pytest.mark.zentao("TC-S0451", domain="server/agent", priority="P1")
    def test_tcp_ok_but_auth_fails(self):
        svc = AgentService()
        agent = _make_agent_data(host="10.0.0.1", credential_id="wrong-cred")
        cred = _make_credential_data(cred_id="wrong-cred", username="admin", password="wrong")
        mock_paramiko, mock_client = _patch_paramiko()
        mock_client.connect.side_effect = mock_paramiko.AuthenticationException("Auth failed")
        with (
            patch("taskpps.services.agent_service.socket") as mock_socket,
            patch.object(svc._loader, "resolve_credential", return_value=cred),
            patch.dict("sys.modules", {"paramiko": mock_paramiko}),
        ):
            mock_sock = MagicMock()
            mock_socket.create_connection.return_value = mock_sock
            result = svc._check_one(agent, 5)
        assert result.status == "failed"
        assert "Authentication failed" in result.error

    @pytest.mark.zentao("TC-S0452", domain="server/agent", priority="P2")
    def test_tcp_ok_and_auth_ok(self):
        svc = AgentService()
        agent = _make_agent_data(host="10.0.0.1", credential_id="good-cred")
        cred = _make_credential_data(cred_id="good-cred", username="admin", password="correct")
        mock_paramiko, _mock_client = _patch_paramiko()
        with (
            patch("taskpps.services.agent_service.socket") as mock_socket,
            patch.object(svc._loader, "resolve_credential", return_value=cred),
            patch.dict("sys.modules", {"paramiko": mock_paramiko}),
        ):
            mock_sock = MagicMock()
            mock_socket.create_connection.return_value = mock_sock
            result = svc._check_one(agent, 5)
        assert result.status == "connected"


class TestMatchFileFilter:
    @pytest.mark.zentao("TC-S0453", domain="server/agent", priority="P2")
    def test_exact_match(self):
        assert _match_file_filter("agents/staging.yaml", "staging") is True

    @pytest.mark.zentao("TC-S0454", domain="server/agent", priority="P2")
    def test_yml_extension(self):
        assert _match_file_filter("agents/staging.yml", "staging") is True

    @pytest.mark.zentao("TC-S0455", domain="server/agent", priority="P2")
    def test_no_match(self):
        assert _match_file_filter("agents/prod.yaml", "staging") is False

    @pytest.mark.zentao("TC-S0456", domain="server/agent", priority="P2")
    def test_partial_no_match(self):
        assert _match_file_filter("agents/staging-server.yaml", "staging") is False

    @pytest.mark.zentao("TC-S0457", domain="server/agent", priority="P2")
    def test_case_insensitive(self):
        assert _match_file_filter("agents/Staging.yaml", "staging") is True


# ----------------------------------------------------------------------------
# _probe_remote_host_info 解析测试（host-info endpoint 依赖）
# ----------------------------------------------------------------------------


class TestProbeRemoteHostInfo:
    """解析 lscpu / free / df 输出的核心解析逻辑"""

    def _make_ssh_client(self, outputs: dict[str, str]):
        """outputs: {command_substring: stdout}"""
        client = MagicMock()

        def exec_command(cmd, timeout=None):
            # 找第一个匹配的 substring
            matched = ""
            for k, v in outputs.items():
                if k in cmd:
                    matched = v
                    break
            mock_stdout = MagicMock()
            mock_stdout.read.return_value = matched.encode("utf-8")
            return (None, mock_stdout, None)

        client.exec_command.side_effect = lambda cmd, timeout=None: exec_command(cmd, timeout)
        return client

    @pytest.mark.zentao("TC-S0458", domain="server/agent", priority="P2")
    def test_parses_lscpu_cores_threads(self):
        svc = AgentService()
        client = self._make_ssh_client(
            {
                "hostname": "myhost",
                "uname -a": "Linux myhost 5.15.0-amd64 #1 SMP x86_64",
                "/etc/os-release": 'PRETTY_NAME="Debian GNU/Linux 12"\nNAME="Debian"',
                "uptime": " 14:32:01 up 3 days, 2 users, load average: 0.05, 0.03, 0.00",
                "lscpu": "Architecture: x86_64\n"
                "Model name: Intel(R) Xeon(R) CPU E5-2680 v4 @ 2.40GHz\n"
                "CPU(s): 4\n"
                "Thread(s) per core: 1\n"
                "Core(s) per socket: 4\n"
                "Socket(s): 1\n"
                "nproc: 4",
                "free -h": "              total        used        free      shared  buff/cache   available\n"
                "Mem:           16Gi        4.2Gi       8.1Gi       0.1Gi       3.7Gi        11Gi\n"
                "Swap:         2.0Gi       0.0Ki       2.0Gi",
                "/proc/meminfo": "MemTotal:       16777216 kB\nMemAvailable:   12000000 kB\nBuffers:         100000 kB",
                "df -h": "Filesystem      Size  Used Avail Use% Mounted on\n"
                "/dev/sda1        50G   20G   28G  42% /\n"
                "/dev/sda2       200G  150G   40G  79% /var",
            }
        )
        data = svc._probe_remote_host_info(client, timeout=5)
        assert data["hostname"] == "myhost"
        assert "Linux" in data["kernel"]
        assert "Debian" in data["os_release"]
        # CPU
        assert data["cpu"]["model"] == "Intel(R) Xeon(R) CPU E5-2680 v4 @ 2.40GHz"
        assert data["cpu"]["threads"] == 4
        assert data["cpu"]["cores"] == 4  # 4 per socket * 1 socket
        # 内存
        assert data["memory"]["total"] == "16Gi"
        assert data["memory"]["used"] == "4.2Gi"
        # MemAvailable 算法：percent = (total - avail) / total
        # (16777216 - 12000000) / 16777216 = ~28.4%
        assert 25 <= data["memory"]["percent"] <= 31
        # 磁盘
        assert len(data["disks"]) == 2
        assert data["disks"][0]["mount"] == "/"
        assert data["disks"][0]["percent"] == 42
        assert data["disks"][1]["mount"] == "/var"
        assert data["disks"][1]["percent"] == 79

    @pytest.mark.zentao("TC-S0459", domain="server/agent", priority="P2")
    def test_handles_missing_commands(self):
        """lscpu / free / df 都不存在时，返回全空 dict 不抛异常"""
        svc = AgentService()
        client = self._make_ssh_client({})  # 所有命令返回空
        data = svc._probe_remote_host_info(client, timeout=5)
        assert data["hostname"] == ""
        assert data["cpu"] == {"model": "", "cores": 0, "threads": 0}
        assert data["memory"] == {"total": "", "used": "", "free": "", "percent": -1}
        assert data["disks"] == []

    @pytest.mark.zentao("TC-S0460", domain="server/agent", priority="P2")
    def test_handles_malformed_lscpu(self):
        """lscpu 输出乱码也不应该崩"""
        svc = AgentService()
        client = self._make_ssh_client(
            {
                "lscpu": "garbled output \x00\xff no newlines",
            }
        )
        data = svc._probe_remote_host_info(client, timeout=5)
        # 不抛异常 + threads/cores 兜底走 nproc
        assert isinstance(data["cpu"]["threads"], int)
        assert isinstance(data["cpu"]["cores"], int)

    @pytest.mark.zentao("TC-S0461", domain="server/agent", priority="P2")
    def test_disk_dedupes_by_device_shows_disk_usage(self):
        """issue #64: 按设备去重, 展示磁盘 usage 而非每个挂载点(分区)"""
        svc = AgentService()
        # 模拟 issue #64: 同一设备 /dev/sda2 有 1 个真实挂载点 + 2 个 docker overlay
        client = self._make_ssh_client(
            {
                "df -h": "Filesystem      Size  Used Avail Use% Mounted on\n"
                "/dev/sda1        49G   12G   35G  42% /\n"
                "/dev/sda1        49G   12G   35G  42% /fs\n"  # 同设备, 挂载路径更长
                "/dev/sda2       175G   81G   93G  47% /vol1\n"
                "/dev/sda2       175G   81G   93G  47% /vol1/docker/overlay2/abc/merged\n"  # 同设备, overlay
                "/dev/sda2       175G   81G   93G  47% /vol1/docker/overlay2/def/merged\n"  # 同设备, overlay
                "/dev/sda3       866G  472G  394G  55% /vol02/1000-0-50fff9e9\n"
                "/dev/sda4       1.0P    0  1.0P   0% /vol02/1000-1-d7502eb3\n",
            }
        )
        data = svc._probe_remote_host_info(client, timeout=5)
        mounts = [d["mount"] for d in data["disks"]]
        # 每个设备只出现一次: 4 个设备 = 4 条
        assert len(data["disks"]) == 4
        # /dev/sda1 取最短挂载路径 /, 而非 /fs
        assert "/" in mounts
        assert "/fs" not in mounts
        # /dev/sda2 取最短挂载路径 /vol1, 而非 docker overlay
        assert "/vol1" in mounts
        assert not any("/docker/overlay2/" in m for m in mounts)
        # 其余设备正常展示
        assert "/vol02/1000-0-50fff9e9" in mounts
        assert "/vol02/1000-1-d7502eb3" in mounts


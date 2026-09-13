from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from taskpps.main import app as _app


@pytest.fixture
def app():
    return _app


@pytest.mark.asyncio
@pytest.mark.zentao("TC-S0905", domain="server/api", priority="P2")
async def test_try_connect(app, setup_project, tmp_project):
    import taskpps.config as cfg

    cfg.set_project_root(tmp_project)
    cfg._settings = None
    cfg.load_settings(str(tmp_project / "taskpps.yaml"))

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/agents/try-connect",
            json={"agent_id": "staging-server", "timeout": 5},
        )
        assert response.status_code in (200, 400, 404)


@pytest.mark.asyncio
@pytest.mark.zentao("TC-S0906", domain="server/api", priority="P2")
async def test_check(app, setup_project, tmp_project):
    import taskpps.config as cfg

    cfg.set_project_root(tmp_project)
    cfg._settings = None
    cfg.load_settings(str(tmp_project / "taskpps.yaml"))

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/agents/check",
            json={"agent_id": "staging-server"},
        )
        assert response.status_code in (200, 400, 404)


@pytest.mark.asyncio
@pytest.mark.zentao("TC-S0907", domain="server/api", priority="P1")
async def test_check_agent_not_found(app, setup_project, tmp_project):
    import taskpps.config as cfg

    cfg.set_project_root(tmp_project)
    cfg._settings = None
    cfg.load_settings(str(tmp_project / "taskpps.yaml"))

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/agents/try-connect",
            json={"agent_id": "nonexistent", "timeout": 5},
        )
        assert response.status_code in (400, 404)


# ----------------------------------------------------------------------------
# /api/agents/{id}/host-info endpoint 测试
# ----------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.zentao("TC-S0908", domain="server/api", priority="P1")
async def test_host_info_agent_not_found(app, setup_project, tmp_project, db_engine):
    """不存在的 agent_id → 404"""
    import taskpps.config as cfg

    cfg.set_project_root(tmp_project)
    cfg._settings = None
    cfg.load_settings(str(tmp_project / "taskpps.yaml"))

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/agents/nonexistent/host-info")
        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()


@pytest.mark.asyncio
@pytest.mark.zentao("TC-S0909", domain="server/api", priority="P2")
async def test_host_info_execution_agent(app, setup_project, tmp_project):
    """execution-agent 类型：返回 source=agent + 错误（待 agent 端实现）"""
    from unittest.mock import MagicMock, patch

    import taskpps.config as cfg

    cfg.set_project_root(tmp_project)
    cfg._settings = None
    cfg.load_settings(str(tmp_project / "taskpps.yaml"))

    agent_cfg = {
        "id": "exec-agent",
        "name": "Exec Agent",
        "type": "execution-agent",
        "host": "",
        "port": 0,
    }

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        with patch("taskpps.api.agents.AgentLoader") as MockLoader:
            loader = MagicMock()
            loader.get.return_value = agent_cfg
            loader.resolve_credential.return_value = None
            MockLoader.return_value = loader
            with patch("taskpps.api.agents.manager") as mock_mgr:
                mock_mgr.get_connection.return_value = None
                response = await client.get("/api/agents/exec-agent/host-info")
    assert response.status_code == 200
    data = response.json()
    assert data["source"] == "agent"
    assert "execution agent" in (data.get("error") or "").lower()


@pytest.mark.asyncio
@pytest.mark.zentao("TC-S0910", domain="server/api", priority="P1")
async def test_host_info_ssh_missing_credential(app, setup_project, tmp_project):
    """ssh agent 但 credential 没 key_path / password → 200 + 明确错误信息"""
    from unittest.mock import MagicMock, patch

    import taskpps.config as cfg

    cfg.set_project_root(tmp_project)
    cfg._settings = None
    cfg.load_settings(str(tmp_project / "taskpps.yaml"))

    agent_cfg = {
        "id": "ssh-no-creds",
        "name": "SSH No Creds",
        "type": "ssh-username-password",
        "host": "10.0.0.1",
        "port": 22,
        "username": "root",
        "credential_id": "empty-cred",
    }

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        with patch("taskpps.api.agents.AgentLoader") as MockLoader:
            loader = MagicMock()
            loader.get.return_value = agent_cfg
            # credential yaml 只有 username，没 key_path/password
            loader.resolve_credential.return_value = {"id": "empty-cred", "username": "root"}
            MockLoader.return_value = loader
            response = await client.get("/api/agents/ssh-no-creds/host-info")
    assert response.status_code == 200
    data = response.json()
    assert data["source"] == "ssh"
    assert "key_path" in (data.get("error") or "") or "password" in (data.get("error") or "")


@pytest.mark.asyncio
@pytest.mark.zentao("TC-S0911", domain="server/api", priority="P1")
async def test_host_info_ssh_auth_failed(app, setup_project, tmp_project, db_engine):
    """SSH 认证失败 → 200 + 错误信息含 username（不发 5xx）"""
    from unittest.mock import MagicMock, patch

    import taskpps.config as cfg

    cfg.set_project_root(tmp_project)
    cfg._settings = None
    cfg.load_settings(str(tmp_project / "taskpps.yaml"))

    agent_cfg = {
        "id": "ssh-bad-pw",
        "name": "SSH Bad PW",
        "type": "ssh-username-password",
        "host": "10.0.0.1",
        "port": 22,
        "username": "root",
        "credential_id": "bad-cred",
    }

    # 模拟 paramiko 模块
    mock_paramiko = MagicMock()
    mock_client = MagicMock()
    mock_paramiko.SSHClient.return_value = mock_client
    mock_paramiko.AutoAddPolicy.return_value = MagicMock()

    # 模拟 paramiko.AuthenticationException 异常类
    class _AuthExc(Exception):
        pass

    mock_paramiko.AuthenticationException = _AuthExc
    mock_client.connect.side_effect = _AuthExc("bad password")

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        with patch("taskpps.api.agents.AgentLoader") as MockLoader:
            loader = MagicMock()
            loader.get.return_value = agent_cfg
            loader.resolve_credential.return_value = {
                "id": "bad-cred",
                "username": "admin",
                "password": "wrong",
            }
            MockLoader.return_value = loader
            with patch.dict("sys.modules", {"paramiko": mock_paramiko}):
                response = await client.get("/api/agents/ssh-bad-pw/host-info")
    assert response.status_code == 200
    data = response.json()
    assert data["source"] == "ssh"
    # 错误信息应该含 username（让用户诊断）
    assert "admin" in (data.get("error") or ""), f"Expected 'admin' in error, got: {data.get('error')}"
    assert "认证失败" in (data.get("error") or "")


@pytest.mark.asyncio
@pytest.mark.zentao("TC-S0912", domain="server/api", priority="P1")
async def test_host_info_ssh_success(app, setup_project, tmp_project, db_engine):
    """SSH 成功 → 返回真实 host 数据"""
    from unittest.mock import MagicMock, patch

    import taskpps.config as cfg

    cfg.set_project_root(tmp_project)
    cfg._settings = None
    cfg.load_settings(str(tmp_project / "taskpps.yaml"))

    agent_cfg = {
        "id": "ssh-ok",
        "name": "SSH OK",
        "type": "ssh-key",
        "host": "10.0.0.1",
        "port": 22,
        "username": "root",
        "credential_id": "good-cred",
    }

    # 模拟 paramiko 模块：connect 不抛错 + exec_command 返回 lscpu/free/df
    mock_paramiko = MagicMock()
    mock_client = MagicMock()
    mock_paramiko.SSHClient.return_value = mock_client
    mock_paramiko.AutoAddPolicy.return_value = MagicMock()
    mock_paramiko.AuthenticationException = type("AE", (Exception,), {})

    outputs = {
        "hostname": "myhost",
        "uname -a": "Linux myhost 6.1.0 x86_64",
        "/etc/os-release": 'PRETTY_NAME="Ubuntu 22.04"',
        "uptime": "10:00:00 up 1 day",
        "lscpu": "Model name: TestCPU\nCPU(s): 2\nCore(s) per socket: 2\nSocket(s): 1",
        "free -h": "Mem:           8Gi        2Gi       4Gi",
        "/proc/meminfo": "MemTotal:       8388608 kB\nMemAvailable:   6000000 kB",
        "df -h": "Filesystem      Size  Used Avail Use% Mounted on\n/dev/sda1       20G   8G   12G  40% /",
    }

    def _exec(cmd, timeout=None):
        mock = MagicMock()
        stdout = MagicMock()
        for k, v in outputs.items():
            if k in cmd:
                stdout.read.return_value = v.encode("utf-8")
                break
        else:
            stdout.read.return_value = b""
        return (None, stdout, None)

    mock_client.exec_command.side_effect = _exec

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        with patch("taskpps.api.agents.AgentLoader") as MockLoader:
            loader = MagicMock()
            loader.get.return_value = agent_cfg
            loader.resolve_credential.return_value = {
                "id": "good-cred",
                "username": "admin",
                "key_path": "/tmp/key",
            }
            MockLoader.return_value = loader
            with patch.dict("sys.modules", {"paramiko": mock_paramiko}):
                response = await client.get("/api/agents/ssh-ok/host-info")
    assert response.status_code == 200
    data = response.json()
    assert data["source"] == "ssh"
    assert data["error"] is None
    assert data["hostname"] == "myhost"
    assert "Linux" in data["kernel"]
    assert "Ubuntu" in data["os_release"]
    assert data["cpu"]["model"] == "TestCPU"
    assert data["cpu"]["threads"] == 2
    assert data["cpu"]["cores"] == 2
    assert data["memory"]["total"] == "8Gi"
    assert 25 <= data["memory"]["percent"] <= 35
    assert len(data["disks"]) == 1
    assert data["disks"][0]["mount"] == "/"
    # 验证 connect 调用用了 key_filename（不是 pkey 对象）
    mock_client.connect.assert_called_once()
    call_kwargs = mock_client.connect.call_args.kwargs
    assert call_kwargs.get("key_filename") == "/tmp/key"
    assert call_kwargs.get("username") == "admin"
    assert "pkey" not in call_kwargs  # ← 回归测试：之前 bug 用 pkey 错字段名


# ----------------------------------------------------------------------------
# Agent 列表 / 状态 / pending commands 测试
# ----------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.zentao("TC-S0913", domain="server/api", priority="P1")
async def test_agent_all_includes_max_parallel(app, setup_project, tmp_project):
    """/api/agents/all 返回的 AgentWithConfig 应包含 max_parallel"""
    import taskpps.config as cfg

    cfg.set_project_root(tmp_project)
    cfg._settings = None
    cfg.load_settings(str(tmp_project / "taskpps.yaml"))

    agent_items = [
        {
            "id": "agent-a",
            "name": "Agent A",
            "type": "execution-agent",
            "host": "",
            "port": 0,
            "max_parallel": 3,
            "_project_id": "proj-1",
            "_project_name": "Project 1",
        },
        {
            "id": "agent-b",
            "name": "Agent B",
            "type": "execution-agent",
            "host": "",
            "port": 0,
            "_project_id": "proj-1",
            "_project_name": "Project 1",
        },
    ]

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        with patch("taskpps.api.agents._load_agents_from_projects", return_value=(agent_items, [])):
            response = await client.get("/api/agents/all")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list) and len(data) == 2
    assert data[0]["agent_id"] == "agent-a"
    assert data[0]["max_parallel"] == 3
    assert data[1]["agent_id"] == "agent-b"
    assert data[1]["max_parallel"] == 1


@pytest.mark.asyncio
@pytest.mark.zentao("TC-S0914", domain="server/api", priority="P2")
async def test_agent_pending_commands_sorted_by_started_at(app, setup_project, tmp_project):
    """/api/agents/{id}/pending-commands 应按 started_at 排序返回"""
    import taskpps.config as cfg

    cfg.set_project_root(tmp_project)
    cfg._settings = None
    cfg.load_settings(str(tmp_project / "taskpps.yaml"))

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        with patch("taskpps.api.agents.AgentManager.instance") as mock_instance:
            conn = MagicMock()
            conn._pending_commands = {
                "cmd-2": MagicMock(
                    command_id="cmd-2",
                    command="echo 2",
                    cwd="",
                    timeout=0,
                    run_id="run-1",
                    task_name="task-2",
                    status="running",
                    queued_at=190.0,
                    started_at=200.0,
                    future=MagicMock(),
                ),
                "cmd-1": MagicMock(
                    command_id="cmd-1",
                    command="echo 1",
                    cwd="",
                    timeout=0,
                    run_id="run-1",
                    task_name="task-1",
                    status="running",
                    queued_at=90.0,
                    started_at=100.0,
                    future=MagicMock(),
                ),
            }
            mock_instance.return_value.get_connection.return_value = conn
            response = await client.get("/api/agents/test-agent/pending-commands")

    assert response.status_code == 200
    data = response.json()
    assert [item["command_id"] for item in data] == ["cmd-1", "cmd-2"]


@pytest.mark.asyncio
@pytest.mark.zentao("TC-S0915", domain="server/api", priority="P2")
async def test_agent_pending_commands_includes_queued_status(app, setup_project, tmp_project):
    """/api/agents/{id}/pending-commands 应返回 running/queued 状态"""
    import taskpps.config as cfg

    cfg.set_project_root(tmp_project)
    cfg._settings = None
    cfg.load_settings(str(tmp_project / "taskpps.yaml"))

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        with patch("taskpps.api.agents.AgentManager.instance") as mock_instance:
            conn = MagicMock()
            conn._pending_commands = {
                "cmd-running": MagicMock(
                    command_id="cmd-running",
                    command="echo running",
                    cwd="",
                    timeout=0,
                    run_id="run-1",
                    task_name="task-running",
                    status="running",
                    queued_at=100.0,
                    started_at=200.0,
                    future=MagicMock(),
                ),
                "cmd-queued": MagicMock(
                    command_id="cmd-queued",
                    command="echo queued",
                    cwd="",
                    timeout=0,
                    run_id="run-1",
                    task_name="task-queued",
                    status="queued",
                    queued_at=150.0,
                    started_at=0.0,
                    future=MagicMock(),
                ),
            }
            mock_instance.return_value.get_connection.return_value = conn
            response = await client.get("/api/agents/test-agent/pending-commands")

    assert response.status_code == 200
    data = response.json()
    statuses = {item["command_id"]: item["status"] for item in data}
    assert statuses["cmd-running"] == "running"
    assert statuses["cmd-queued"] == "queued"


@pytest.mark.asyncio
@pytest.mark.zentao("TC-S0916", domain="server/api", priority="P2")
async def test_agent_status_counts_running_and_queued(app, setup_project, tmp_project):
    """/api/agents/status/{id} 应分别统计 running 和 queued 命令数"""
    import taskpps.config as cfg

    cfg.set_project_root(tmp_project)
    cfg._settings = None
    cfg.load_settings(str(tmp_project / "taskpps.yaml"))

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        with patch("taskpps.api.agents.AgentManager.instance") as mock_instance:
            manager = MagicMock()
            manager.is_connected.return_value = True
            conn = MagicMock()
            conn.hostname = "host"
            conn.platform = "linux/x86_64"
            conn.system = "linux"
            conn.arch = "x86_64"
            conn.ip = "10.0.0.1"
            conn.agent_version = "1.0"
            conn.agent_pid = 1
            conn.connected_at = 1000.0
            conn.last_heartbeat = 1000.0
            conn._pending_commands = {
                "cmd-running": MagicMock(status="running"),
                "cmd-queued-1": MagicMock(status="queued"),
                "cmd-queued-2": MagicMock(status="queued"),
            }
            manager.get_connection.return_value = conn
            mock_instance.return_value = manager
            with patch("taskpps.api.agents._load_agent_max_parallel_map", return_value={"test-agent": 2}):
                response = await client.get("/api/agents/status/test-agent")

    assert response.status_code == 200
    data = response.json()
    assert data["running_commands"] == 1
    assert data["queued_commands"] == 2


@pytest.mark.asyncio
@pytest.mark.zentao("TC-S0917", domain="server/api", priority="P2")
async def test_agent_all_counts_running_and_queued(app, setup_project, tmp_project):
    """/api/agents/all 返回的 AgentWithConfig 应包含 queued_commands"""
    import taskpps.config as cfg

    cfg.set_project_root(tmp_project)
    cfg._settings = None
    cfg.load_settings(str(tmp_project / "taskpps.yaml"))

    agent_items = [
        {
            "id": "agent-a",
            "name": "Agent A",
            "type": "execution-agent",
            "host": "",
            "port": 0,
            "max_parallel": 2,
            "_project_id": "proj-1",
            "_project_name": "Project 1",
        },
    ]

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        with patch("taskpps.api.agents._load_agents_from_projects", return_value=(agent_items, [])):
            with patch("taskpps.api.agents.AgentManager.instance") as mock_instance:
                manager = MagicMock()
                manager.is_connected.return_value = True
                conn = MagicMock()
                conn._pending_commands = {
                    "cmd-running": MagicMock(status="running"),
                    "cmd-queued": MagicMock(status="queued"),
                }
                conn.hostname = "host"
                conn.platform = "linux/x86_64"
                conn.system = "linux"
                conn.arch = "x86_64"
                conn.ip = "10.0.0.1"
                conn.agent_version = "1.0"
                conn.agent_pid = 1
                conn.connected_at = 1000.0
                conn.last_heartbeat = 1000.0
                manager.get_connection.return_value = conn
                mock_instance.return_value = manager
                response = await client.get("/api/agents/all")

    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["running_commands"] == 1
    assert data[0]["queued_commands"] == 1


@pytest.mark.asyncio
@pytest.mark.zentao("TC-S3004", domain="server/api", priority="P2")
async def test_agent_all_includes_last_execution_time(app, setup_project, tmp_project):
    """/api/agents/all 返回的 AgentWithConfig 应包含 last_execution_time"""
    import taskpps.config as cfg

    cfg.set_project_root(tmp_project)
    cfg._settings = None
    cfg.load_settings(str(tmp_project / "taskpps.yaml"))

    agent_items = [
        {
            "id": "agent-a",
            "name": "Agent A",
            "type": "execution-agent",
            "host": "",
            "port": 0,
            "max_parallel": 1,
            "_project_id": "proj-1",
            "_project_name": "Project 1",
        },
    ]

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        with patch("taskpps.api.agents._load_agents_from_projects", return_value=(agent_items, [])):
            with patch("taskpps.api.agents.AgentManager.instance") as mock_instance:
                manager = MagicMock()
                manager.is_connected.return_value = True
                conn = MagicMock()
                conn._pending_commands = {}
                conn.hostname = "host"
                conn.platform = "linux/x86_64"
                conn.system = "linux"
                conn.arch = "x86_64"
                conn.ip = "10.0.0.1"
                conn.agent_version = "1.0"
                conn.agent_pid = 1
                conn.connected_at = 1000.0
                conn.last_heartbeat = 1000.0
                conn.last_command_finished_at = 1718000000.0
                manager.get_connection.return_value = conn
                mock_instance.return_value = manager
                response = await client.get("/api/agents/all")

    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["last_execution_time"] == 1718000000.0


@pytest.mark.asyncio
@pytest.mark.zentao("TC-S3005", domain="server/api", priority="P2")
async def test_agent_all_last_execution_time_default_zero(app, setup_project, tmp_project):
    """/api/agents/all 未连接 agent 的 last_execution_time 应为 0"""
    import taskpps.config as cfg

    cfg.set_project_root(tmp_project)
    cfg._settings = None
    cfg.load_settings(str(tmp_project / "taskpps.yaml"))

    agent_items = [
        {
            "id": "agent-o",
            "name": "Agent offline",
            "type": "execution-agent",
            "host": "",
            "port": 0,
            "max_parallel": 1,
            "_project_id": "proj-1",
            "_project_name": "Project 1",
        },
    ]

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        with patch("taskpps.api.agents._load_agents_from_projects", return_value=(agent_items, [])):
            response = await client.get("/api/agents/all")

    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["last_execution_time"] == 0


@pytest.mark.asyncio
@pytest.mark.zentao("TC-S3006", domain="server/api", priority="P1")
async def test_agent_all_net_probe_non_blocking(app, tmp_project):
    """离线 agent 的 TCP 探测不应阻塞 /all 响应：首次返回 net_status=unknown，
    探测结果在后台异步刷新（验证接口不被 1.5s 超时拖慢）。"""
    import taskpps.config as cfg

    cfg.set_project_root(tmp_project)
    cfg._settings = None
    cfg.load_settings(str(tmp_project / "taskpps.yaml"))

    agent_items = [
        {
            "id": "offline-1",
            "name": "Offline",
            "type": "ssh-linux",
            "host": "10.255.255.1",  # 不可达地址
            "port": 22,
            "max_parallel": 1,
            "_project_id": "proj-1",
            "_project_name": "Project 1",
        },
    ]

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        with patch("taskpps.api.agents._load_agents_from_projects", return_value=(agent_items, [])):
            # 探测必然超时（地址不可达），若同步等待会拖到 1.5s 且返回 reachable/unreachable
            with patch("asyncio.open_connection", side_effect=TimeoutError):
                response = await client.get("/api/agents/all")

    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    # 非阻塞：首次响应立即返回 unknown，不等待后台探测
    assert data[0]["net_status"] == "unknown"


# ----------------------------------------------------------------------------
# POST /api/agents/check-stream 与 POST /api/agents/update-deploy（issue #223）
# 设计考虑：这两个 POST 路由受 JWT 中间件保护，成功路径必须先拿测试 token；
# token 直接签发而不注册用户，避免把「用户体系」耦合进 Agent 路由测试。
# ----------------------------------------------------------------------------


def _auth_headers() -> dict[str, str]:
    """签发测试 JWT（ASGITransport 不触发 lifespan seed，需显式 ensure secret）。"""
    from taskpps.auth.security import create_access_token, ensure_jwt_secret

    ensure_jwt_secret()
    return {"Authorization": f"Bearer {create_access_token('tester', 'user')}"}


def _sse_data_lines(text: str) -> list[str]:
    """按流协议取 data: 行（每个事件一行，summary 行前缀为 data: summary:）。"""
    return [line for line in text.splitlines() if line.startswith("data: ")]


@pytest.mark.asyncio
@pytest.mark.zentao("TC-S3593", domain="server/api", priority="P1")
async def test_check_stream_returns_result_then_summary(client):
    """成功流：先推送各 agent 检查结果，最后以 summary 汇总收尾。"""
    resp = await client.post(
        "/api/agents/check-stream",
        json={"agent_id": "staging-server", "timeout": 5},
        headers=_auth_headers(),
    )
    assert resp.status_code == 200
    assert "text/event-stream" in resp.headers.get("content-type", "")

    lines = _sse_data_lines(resp.text)
    # 协议契约：1 条 agent 结果 + 1 条 summary，顺序不可颠倒（前端逐条渲染依赖它）
    assert len(lines) == 2

    result = json.loads(lines[0][len("data: ") :])
    assert result["agent_id"] == "staging-server"
    assert result["status"] == "ready"  # 本地 host 无需网络即可判定就绪
    assert result["error"] is None

    summary = json.loads(lines[1][len("data: summary:") :])
    assert summary == {"total": 1, "connected": 1, "failed": 0}


@pytest.mark.asyncio
@pytest.mark.zentao("TC-S3594", domain="server/api", priority="P2")
async def test_check_stream_unknown_agent_yields_empty_summary(client):
    """agent 不存在时的用户可见反馈：流不报错，只回一份 total=0 的 summary。"""
    resp = await client.post(
        "/api/agents/check-stream",
        json={"agent_id": "no-such-agent", "timeout": 1},
        headers=_auth_headers(),
    )
    assert resp.status_code == 200

    lines = _sse_data_lines(resp.text)
    assert len(lines) == 1
    assert lines[0].startswith("data: summary:")

    summary = json.loads(lines[0][len("data: summary:") :])
    assert summary == {"total": 0, "connected": 0, "failed": 0}


@pytest.mark.asyncio
@pytest.mark.zentao("TC-S3595", domain="server/api", priority="P0")
async def test_check_stream_unauthenticated_401(client):
    """未带 JWT 的 POST 被中间件拦截：401 + 明确文案，且不返回 SSE 流。"""
    resp = await client.post("/api/agents/check-stream", json={"agent_id": "staging-server"})
    assert resp.status_code == 401
    assert resp.json()["detail"] == "未登录或 token 无效"
    assert "text/event-stream" not in resp.headers.get("content-type", "")


@pytest.mark.asyncio
@pytest.mark.zentao("TC-S3596", domain="server/api", priority="P1")
async def test_update_deploy_success_invokes_bootstrap(client):
    """成功路径：解析到 agent 后真实调用 update_deploy，并回传部署成功响应。"""
    from taskpps.loaders.agent_loader import AgentLoader
    from taskpps.services.agent_bootstrap import AgentBootstrap

    with patch.object(AgentBootstrap, "update_deploy", new_callable=AsyncMock) as mock_update:
        resp = await client.post(
            "/api/agents/update-deploy",
            json={"agent_id": "staging-server"},
            headers=_auth_headers(),
        )

    assert resp.status_code == 200
    assert resp.json() == {"success": True, "agent_id": "staging-server", "agent_pid": 0, "error": None}
    mock_update.assert_awaited_once()
    assert mock_update.await_args.args[0] == "staging-server"
    # 路由必须把按项目解析出的 loader 透传给 bootstrap（否则多项目下会部署错文件）
    assert isinstance(mock_update.await_args.kwargs["agent_loader"], AgentLoader)


@pytest.mark.asyncio
@pytest.mark.zentao("TC-S3597", domain="server/api", priority="P1")
async def test_update_deploy_agent_not_found_404(client):
    """agent 不存在：404 + 含 agent_id 的 detail，不应触发部署调用。"""
    from taskpps.services.agent_bootstrap import AgentBootstrap

    with patch.object(AgentBootstrap, "update_deploy", new_callable=AsyncMock) as mock_update:
        resp = await client.post(
            "/api/agents/update-deploy",
            json={"agent_id": "missing-agent"},
            headers=_auth_headers(),
        )

    assert resp.status_code == 404
    # 路由把内部 HTTPException 统一重包装（type: str(exc)，str 含 status code 前缀）
    assert resp.json()["detail"] == "HTTPException: 404: Agent not found: missing-agent"
    mock_update.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.zentao("TC-S3598", domain="server/api", priority="P1")
async def test_update_deploy_local_agent_returns_500_detail(client):
    """部署失败的用户可见反馈：本地 agent 不支持强制更新，500 detail 带异常原因。"""
    resp = await client.post(
        "/api/agents/update-deploy",
        json={"agent_id": "staging-server"},
        headers=_auth_headers(),
    )
    assert resp.status_code == 500
    detail = resp.json()["detail"]
    assert detail.startswith("AgentBootstrapError:")
    assert "Update deploy is not supported for local agents" in detail


@pytest.mark.asyncio
@pytest.mark.zentao("TC-S3599", domain="server/api", priority="P2")
async def test_update_deploy_missing_agent_id_422(client):
    """请求校验：缺 agent_id 必填字段 → 422，detail 精确指向 body.agent_id。"""
    resp = await client.post(
        "/api/agents/update-deploy",
        json={"timeout": 5},
        headers=_auth_headers(),
    )
    assert resp.status_code == 422
    # main.py 的 RequestValidationError handler 把 pydantic 错误压成单句，精确到字段
    assert resp.json()["detail"] == "参数校验失败: agent_id: Field required"


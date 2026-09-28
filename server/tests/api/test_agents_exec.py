from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from tests.auth._helpers import register_and_auth_headers


class TestAgentExec:
    @pytest.mark.asyncio
    @pytest.mark.zentao("TC-S0918", domain="server/api", priority="P1")
    async def test_agent_exec_not_connected(self, client):
        # 中间件对 POST 强制认证；这些用例历史上按匿名调用，导致实际断言的是 401
        headers = await register_and_auth_headers(client)
        response = await client.post(
            "/api/agents/nonexistent/exec",
            headers=headers,
            json={
                "command": "echo hello",
                "timeout": 30,
            },
        )
        assert response.status_code == 404

    @pytest.mark.asyncio
    @pytest.mark.zentao("TC-S0919", domain="server/api", priority="P1")
    async def test_agent_exec_disconnected_agent(self, client):
        """agent 断开后（last_heartbeat=-1），exec 应返回 404 而非 500。"""
        from taskpps.services.agent_manager import AgentConnection, AgentManager

        headers = await register_and_auth_headers(client)
        manager = AgentManager.instance()
        ws = AsyncMock()
        ws.send_json = AsyncMock()
        conn = AgentConnection("disconnected-agent", ws)
        conn.last_heartbeat = -1  # 标记为断开
        manager._connections["disconnected-agent"] = conn

        response = await client.post(
            "/api/agents/disconnected-agent/exec",
            headers=headers,
            json={
                "command": "echo hello",
                "timeout": 5,
            },
        )
        assert response.status_code == 404

        # cleanup
        manager._connections.pop("disconnected-agent", None)

    @pytest.mark.asyncio
    @pytest.mark.zentao("TC-S0920", domain="server/api", priority="P2")
    async def test_agent_exec_connected(self, client):
        from taskpps.services.agent_manager import AgentConnection, AgentManager

        headers = await register_and_auth_headers(client)
        manager = AgentManager.instance()
        ws = AsyncMock()
        ws.send_json = AsyncMock()
        conn = AgentConnection("test-agent", ws)
        manager._connections["test-agent"] = conn

        # 立即 resolve pending，避免端点等满 15s 超时（否则每个用例多花 15s）
        async def _resolve(_agent_id, command_id, *_args, **_kwargs):
            conn.resolve_pending(command_id, {"exit_code": 0, "signal_name": "", "error": ""})

        with patch.object(manager, "send_command", side_effect=_resolve):
            response = await client.post(
                "/api/agents/test-agent/exec",
                headers=headers,
                json={
                    "command": "echo hello",
                    "timeout": 5,
                },
            )
        assert response.status_code == 200
        data = response.json()
        assert data["agent_id"] == "test-agent"

        # cleanup
        manager._connections.pop("test-agent", None)

    @pytest.mark.asyncio
    @pytest.mark.zentao("TC-S0921", domain="server/api", priority="P2")
    async def test_agent_exec_rejected_when_pipeline_running(self, client):
        """Issue #68: agent 正在执行 pipeline 任务时，手动 exec 应被拒绝。"""
        from taskpps.services.agent_manager import AgentConnection, AgentManager, PendingCommandInfo

        headers = await register_and_auth_headers(client)
        manager = AgentManager.instance()
        ws = AsyncMock()
        ws.send_json = AsyncMock()
        conn = AgentConnection("busy-agent", ws)
        # 模拟一个正在执行的 pipeline 任务
        info = PendingCommandInfo(
            command_id="cmd-1",
            command="robot --test example",
            run_id="run-123",
            task_name="main.example",
        )
        conn._pending_commands["cmd-1"] = info
        manager._connections["busy-agent"] = conn

        response = await client.post(
            "/api/agents/busy-agent/exec",
            headers=headers,
            json={
                "command": "echo hello",
                "timeout": 5,
            },
        )
        assert response.status_code == 409
        assert "pipeline task" in response.json()["detail"].lower()

        # cleanup
        manager._connections.pop("busy-agent", None)

    @pytest.mark.asyncio
    @pytest.mark.zentao("TC-S0922", domain="server/api", priority="P2")
    async def test_agent_exec_allowed_when_no_pipeline_task(self, client):
        """Issue #68: agent 只有非 pipeline 命令时，手动 exec 应被允许（不被 409 拒绝）。"""
        from taskpps.services.agent_manager import AgentConnection, AgentManager, PendingCommandInfo

        manager = AgentManager.instance()
        ws = AsyncMock()
        ws.send_json = AsyncMock()
        conn = AgentConnection("free-agent", ws)
        # 模拟一个非 pipeline 的 pending command（无 run_id）
        info = PendingCommandInfo(
            command_id="manual-cmd",
            command="ls -la",
            run_id="",  # 空 run_id 表示不是 pipeline 任务
        )
        conn._pending_commands["manual-cmd"] = info
        manager._connections["free-agent"] = conn

        # 验证不会因为 pipeline 检查被拒绝；立即 resolve pending 避免超时等待
        headers = await register_and_auth_headers(client)

        async def _resolve(_agent_id, command_id, *_args, **_kwargs):
            conn.resolve_pending(command_id, {"exit_code": 0, "signal_name": "", "error": ""})

        try:
            with patch.object(manager, "send_command", side_effect=_resolve):
                response = await client.post(
                    "/api/agents/free-agent/exec",
                    headers=headers,
                    json={"command": "echo hello", "timeout": 5},
                )
            assert response.status_code == 200
        finally:
            # 清理：确保 pending commands 和 output callbacks 被清理
            for cid in list(conn._pending_commands.keys()):
                conn.cleanup_command(cid)
            manager._connections.pop("free-agent", None)


class TestAgentExecEnv:
    @pytest.mark.asyncio
    async def test_exec_merges_agent_env_and_shell(self, client, monkeypatch):
        """Web REPL/手动 exec 必须带上 agent yaml 的 shell/env。

        设计决策（为什么 monkeypatch service 层而非写真实 YAML）：
        - 这里只验证 API 层的合并与透传契约；YAML 读写已由 test_agents_write 覆盖。
        - 通过 resolve_pending 立即结束等待，避免 15s 超时拖慢测试。
        """
        from taskpps.api import agents as agents_api
        from taskpps.main import _seed_admin_account
        from taskpps.services.agent_manager import AgentConnection, AgentManager
        from tests.auth._helpers import auth_headers

        await _seed_admin_account()
        login = await client.post("/api/v1/auth/login", json={"username": "admin", "password": "user@123"})
        assert login.status_code == 200, login.text
        headers = auth_headers(login.json()["access_token"])

        manager = AgentManager.instance()
        ws = AsyncMock()
        ws.send_json = AsyncMock()
        conn = AgentConnection("env-agent", ws)
        manager._connections["env-agent"] = conn

        async def fake_load():
            return (
                [
                    {
                        "id": "env-agent",
                        "env": {"FOO": "agent", "BAR": "agent"},
                        "shell": "/bin/zsh",
                    }
                ],
                [],
            )

        monkeypatch.setattr(agents_api, "_load_agents_from_projects", fake_load)

        sent: dict = {}

        async def fake_send(agent_id, command_id, command, env, cwd, timeout, shell=""):
            sent.update(agent_id=agent_id, env=env, shell=shell)
            conn.resolve_pending(command_id, {"exit_code": 0, "signal_name": "", "error": ""})

        monkeypatch.setattr(manager, "send_command", fake_send)

        try:
            response = await client.post(
                "/api/agents/env-agent/exec",
                headers=headers,
                json={"command": "echo $FOO", "env": {"FOO": "task"}, "timeout": 5},
            )
            assert response.status_code == 200, response.text
            assert sent["env"] == {"FOO": "task", "BAR": "agent"}
            assert sent["shell"] == "/bin/zsh"
        finally:
            for cid in list(conn._pending_commands.keys()):
                conn.cleanup_command(cid)
            manager._connections.pop("env-agent", None)

    @pytest.mark.asyncio
    async def test_exec_stream_merges_agent_env_and_shell(self, client, monkeypatch):
        """Web REPL 的 exec/stream 与 exec 使用同一份合并逻辑。

        回归背景：两个端点各自透传 env，合并/传 shell 只改一处会漏掉 REPL。
        """
        from taskpps.api import agents as agents_api
        from taskpps.main import _seed_admin_account
        from taskpps.services.agent_manager import AgentConnection, AgentManager
        from tests.auth._helpers import auth_headers

        await _seed_admin_account()
        login = await client.post("/api/v1/auth/login", json={"username": "admin", "password": "user@123"})
        assert login.status_code == 200, login.text
        headers = auth_headers(login.json()["access_token"])

        manager = AgentManager.instance()
        ws = AsyncMock()
        ws.send_json = AsyncMock()
        conn = AgentConnection("stream-env-agent", ws)
        manager._connections["stream-env-agent"] = conn

        async def fake_load():
            return (
                [{"id": "stream-env-agent", "env": {"BAR": "agent"}, "shell": "/usr/bin/dash"}],
                [],
            )

        monkeypatch.setattr(agents_api, "_load_agents_from_projects", fake_load)

        sent: dict = {}

        async def fake_send(agent_id, command_id, command, env, cwd, timeout, shell=""):
            sent.update(env=env, shell=shell)
            conn.resolve_pending(command_id, {"exit_code": 0, "signal_name": "", "error": ""})

        monkeypatch.setattr(manager, "send_command", fake_send)

        try:
            response = await client.post(
                "/api/agents/stream-env-agent/exec/stream",
                headers=headers,
                json={"command": "echo $BAR", "env": {"FOO": "req"}, "timeout": 5},
            )
            assert response.status_code == 200, response.text
            assert sent["env"] == {"BAR": "agent", "FOO": "req"}
            assert sent["shell"] == "/usr/bin/dash"
        finally:
            for cid in list(conn._pending_commands.keys()):
                conn.cleanup_command(cid)
            manager._connections.pop("stream-env-agent", None)


class TestAgentList:
    @pytest.mark.asyncio
    @pytest.mark.zentao("TC-S0923", domain="server/api", priority="P2")
    async def test_agent_list_empty(self, client):
        response = await client.get("/api/agents/list")
        assert response.status_code == 200
        assert isinstance(response.json(), list)

    @pytest.mark.asyncio
    @pytest.mark.zentao("TC-S0924", domain="server/api", priority="P2")
    async def test_agent_list_with_connected(self, client):
        from taskpps.services.agent_manager import AgentConnection, AgentManager

        manager = AgentManager.instance()
        ws = AsyncMock()
        ws.send_json = AsyncMock()
        conn = AgentConnection("agent-a", ws)
        conn.hostname = "myhost"
        manager._connections["agent-a"] = conn
        conn.last_heartbeat = __import__("time").time()

        response = await client.get("/api/agents/list")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) >= 1
        assert any(a["agent_id"] == "agent-a" for a in data)

        # cleanup
        manager._connections.pop("agent-a", None)


class TestAgentStatus:
    @pytest.mark.asyncio
    @pytest.mark.zentao("TC-S0925", domain="server/api", priority="P1")
    async def test_agent_status_not_connected(self, client):
        response = await client.get("/api/agents/status/nonexistent")
        assert response.status_code == 200
        data = response.json()
        assert data["connected"] is False

    @pytest.mark.asyncio
    @pytest.mark.zentao("TC-S0926", domain="server/api", priority="P2")
    async def test_agent_status_connected(self, client):
        from taskpps.services.agent_manager import AgentConnection, AgentManager

        manager = AgentManager.instance()
        ws = AsyncMock()
        ws.send_json = AsyncMock()
        conn = AgentConnection("status-agent", ws)
        conn.hostname = "testhost"
        conn.platform = "linux/amd64"
        conn.agent_version = "1.0.0"
        conn.agent_pid = 1234
        conn.last_heartbeat = __import__("time").time()
        manager._connections["status-agent"] = conn

        response = await client.get("/api/agents/status/status-agent")
        assert response.status_code == 200
        data = response.json()
        assert data["connected"] is True
        assert data["hostname"] == "testhost"
        assert data["platform"] == "linux/amd64"
        assert data["agent_version"] == "1.0.0"
        assert data["agent_pid"] == 1234

        # cleanup
        manager._connections.pop("status-agent", None)


class TestAgentDeploy:
    @pytest.mark.asyncio
    @pytest.mark.zentao("TC-S0927", domain="server/api", priority="P1")
    async def test_deploy_agent_not_found(self, client):
        """配置里不存在该 agent → 404（不再 mock 不存在的模块属性 AgentBootstrap）。"""
        headers = await register_and_auth_headers(client)
        response = await client.post(
            "/api/agents/deploy",
            headers=headers,
            json={"agent_id": "nonexistent-agent"},
        )
        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()


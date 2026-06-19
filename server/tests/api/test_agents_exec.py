from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest


class TestAgentExec:
    @pytest.mark.asyncio
    async def test_agent_exec_not_connected(self, client):
        response = await client.post(
            "/api/agents/nonexistent/exec",
            json={
                "command": "echo hello",
                "timeout": 30,
            },
        )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_agent_exec_disconnected_agent(self, client):
        """agent 断开后（last_heartbeat=-1），exec 应返回 404 而非 500。"""
        from taskpps.services.agent_manager import AgentConnection, AgentManager

        manager = AgentManager.instance()
        ws = AsyncMock()
        ws.send_json = AsyncMock()
        conn = AgentConnection("disconnected-agent", ws)
        conn.last_heartbeat = -1  # 标记为断开
        manager._connections["disconnected-agent"] = conn

        response = await client.post(
            "/api/agents/disconnected-agent/exec",
            json={
                "command": "echo hello",
                "timeout": 5,
            },
        )
        assert response.status_code == 404

        # cleanup
        manager._connections.pop("disconnected-agent", None)

    @pytest.mark.asyncio
    async def test_agent_exec_connected(self, client):
        from taskpps.services.agent_manager import AgentConnection, AgentManager

        manager = AgentManager.instance()
        ws = AsyncMock()
        ws.send_json = AsyncMock()
        conn = AgentConnection("test-agent", ws)
        manager._connections["test-agent"] = conn

        response = await client.post(
            "/api/agents/test-agent/exec",
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
    async def test_agent_exec_rejected_when_pipeline_running(self, client):
        """Issue #68: agent 正在执行 pipeline 任务时，手动 exec 应被拒绝。"""
        from taskpps.services.agent_manager import AgentConnection, AgentManager, PendingCommandInfo

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

        # 只验证不被 409 拒绝，不实际发送命令（避免 future 泄漏）
        # 验证不会因为 pipeline 检查被拒绝
        # 由于 agent 是 mock 的，实际 exec 会失败，但不应是 409
        try:
            response = await client.post(
                "/api/agents/free-agent/exec",
                json={"command": "echo hello", "timeout": 5},
            )
            assert response.status_code != 409
        finally:
            # 清理：确保 pending commands 和 output callbacks 被清理
            for cid in list(conn._pending_commands.keys()):
                conn.cleanup_command(cid)
            manager._connections.pop("free-agent", None)


class TestAgentList:
    @pytest.mark.asyncio
    async def test_agent_list_empty(self, client):
        response = await client.get("/api/agents/list")
        assert response.status_code == 200
        assert isinstance(response.json(), list)

    @pytest.mark.asyncio
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
    async def test_agent_status_not_connected(self, client):
        response = await client.get("/api/agents/status/nonexistent")
        assert response.status_code == 200
        data = response.json()
        assert data["connected"] is False

    @pytest.mark.asyncio
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
    async def test_deploy_agent_not_found(self, client):
        # Agent not found in config
        with patch("taskpps.api.agents.AgentBootstrap") as mock_bootstrap:
            mock_bootstrap.return_value.bootstrap = AsyncMock(side_effect=Exception("Agent not found"))
            response = await client.post(
                "/api/agents/deploy",
                json={
                    "agent_id": "nonexistent-agent",
                },
            )
            assert response.status_code == 500

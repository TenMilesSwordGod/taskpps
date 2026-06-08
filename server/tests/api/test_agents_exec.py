from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestAgentExec:
    @pytest.mark.asyncio
    async def test_agent_exec_not_connected(self, client):
        response = await client.post("/api/agents/nonexistent/exec", json={
            "command": "echo hello",
            "timeout": 30,
        })
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_agent_exec_connected(self, client):
        from taskpps.services.agent_manager import AgentManager, AgentConnection

        manager = AgentManager.instance()
        ws = AsyncMock()
        ws.send_json = AsyncMock()
        conn = AgentConnection("test-agent", ws)
        manager._connections["test-agent"] = conn

        response = await client.post("/api/agents/test-agent/exec", json={
            "command": "echo hello",
            "timeout": 5,
        })
        assert response.status_code == 200
        data = response.json()
        assert data["agent_id"] == "test-agent"

        # cleanup
        manager._connections.pop("test-agent", None)


class TestAgentList:
    @pytest.mark.asyncio
    async def test_agent_list_empty(self, client):
        response = await client.get("/api/agents/list")
        assert response.status_code == 200
        assert isinstance(response.json(), list)

    @pytest.mark.asyncio
    async def test_agent_list_with_connected(self, client):
        from taskpps.services.agent_manager import AgentManager, AgentConnection

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
        from taskpps.services.agent_manager import AgentManager, AgentConnection

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
            mock_bootstrap.return_value.bootstrap = AsyncMock(
                side_effect=Exception("Agent not found")
            )
            response = await client.post("/api/agents/deploy", json={
                "agent_id": "nonexistent-agent",
            })
            assert response.status_code == 500
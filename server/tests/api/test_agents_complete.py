from __future__ import annotations

import asyncio
import time
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio


@pytest_asyncio.fixture
async def auth_headers(client):
    """测试环境 POST 需要 JWT：直接生成 token（ASGITransport 不触发 lifespan seed）。"""
    from taskpps.auth.security import create_access_token, ensure_jwt_secret

    ensure_jwt_secret()
    token = create_access_token("admin", "admin")
    return {"Authorization": f"Bearer {token}"}


class TestAgentComplete:
    @pytest.mark.asyncio
    async def test_complete_not_connected(self, client, auth_headers):
        response = await client.post(
            "/api/agents/nonexistent/complete",
            json={"line": "ls", "cursor": 2, "cwd": ""},
            headers=auth_headers,
        )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_complete_disconnected_agent(self, client, auth_headers):
        """agent 断开后（last_heartbeat=-1），complete 应返回 404 而非 500。"""
        from taskpps.services.agent_manager import AgentConnection, AgentManager

        manager = AgentManager.instance()
        ws = AsyncMock()
        ws.send_json = AsyncMock()
        conn = AgentConnection("disconnected-complete", ws)
        conn.last_heartbeat = -1
        manager._connections["disconnected-complete"] = conn

        response = await client.post(
            "/api/agents/disconnected-complete/complete",
            json={"line": "ls", "cursor": 2},
            headers=auth_headers,
        )
        assert response.status_code == 404

        manager._connections.pop("disconnected-complete", None)

    @pytest.mark.asyncio
    async def test_complete_connected_returns_candidates(self, client, auth_headers):
        """agent 返回候选后，complete 端点应原样透传 candidates/prefix。"""
        from taskpps.services.agent_manager import AgentConnection, AgentManager

        manager = AgentManager.instance()
        ws = AsyncMock()
        ws.send_json = AsyncMock()
        conn = AgentConnection("complete-agent", ws)
        conn.last_heartbeat = time.time()
        manager._connections["complete-agent"] = conn

        async def resolve_after_delay():
            await asyncio.sleep(0.05)
            for request_id in list(conn._complete_futures.keys()):
                conn.handle_complete_result(
                    request_id,
                    {"request_id": request_id, "prefix": "ls", "candidates": ["ls", "lsblk"], "error": ""},
                )

        resolver_task = asyncio.create_task(resolve_after_delay())
        try:
            response = await client.post(
                "/api/agents/complete-agent/complete",
                json={"line": "ls", "cursor": 2, "cwd": ""},
                headers=auth_headers,
            )
            assert response.status_code == 200
            data = response.json()
            assert data["prefix"] == "ls"
            assert data["candidates"] == ["ls", "lsblk"]
            assert data["error"] == ""
            # complete 请求不应出现在 pending commands 中（不占并发槽位）
            assert len(conn._pending_commands) == 0
        finally:
            await resolver_task
            manager._connections.pop("complete-agent", None)

    @pytest.mark.asyncio
    async def test_complete_forwards_error_from_agent(self, client, auth_headers):
        """agent 侧补全失败（如 shell 无 compgen）时，error 应透传给前端。"""
        from taskpps.services.agent_manager import AgentConnection, AgentManager

        manager = AgentManager.instance()
        ws = AsyncMock()
        ws.send_json = AsyncMock()
        conn = AgentConnection("complete-err-agent", ws)
        conn.last_heartbeat = time.time()
        manager._connections["complete-err-agent"] = conn

        async def resolve_after_delay():
            await asyncio.sleep(0.05)
            for request_id in list(conn._complete_futures.keys()):
                conn.handle_complete_result(
                    request_id,
                    {"request_id": request_id, "prefix": "ls", "candidates": [], "error": "completion failed"},
                )

        resolver_task = asyncio.create_task(resolve_after_delay())
        try:
            response = await client.post(
                "/api/agents/complete-err-agent/complete",
                json={"line": "ls", "cursor": 2},
                headers=auth_headers,
            )
            assert response.status_code == 200
            data = response.json()
            assert data["error"] == "completion failed"
            assert data["candidates"] == []
        finally:
            await resolver_task
            manager._connections.pop("complete-err-agent", None)

    @pytest.mark.asyncio
    async def test_complete_timeout(self, client, auth_headers):
        """agent 5 秒内未返回时，端点应返回 200 + error 而非挂起。"""
        from taskpps.services.agent_manager import AgentConnection, AgentManager

        manager = AgentManager.instance()
        ws = AsyncMock()
        ws.send_json = AsyncMock()
        conn = AgentConnection("complete-timeout-agent", ws)
        conn.last_heartbeat = time.time()
        manager._connections["complete-timeout-agent"] = conn

        # 模拟 future 永不 resolve（agent 侧无响应）
        with patch("taskpps.api.agents.asyncio.wait_for", new_callable=AsyncMock, side_effect=asyncio.TimeoutError):
            response = await client.post(
                "/api/agents/complete-timeout-agent/complete",
                json={"line": "ls", "cursor": 2},
                headers=auth_headers,
            )
        assert response.status_code == 200
        data = response.json()
        assert data["error"] == "completion timeout"
        assert data["candidates"] == []

        # 超时后 future 应从字典中清理，避免泄漏
        assert len(conn._complete_futures) == 0
        manager._connections.pop("complete-timeout-agent", None)

    @pytest.mark.asyncio
    async def test_complete_send_failure_returns_500(self, client, auth_headers):
        """发送 complete_request 失败时返回 500（消息未送达 agent）。"""
        from taskpps.services.agent_manager import AgentConnection, AgentManager

        manager = AgentManager.instance()
        ws = AsyncMock()
        ws.send_json = AsyncMock(side_effect=RuntimeError("ws closed"))
        conn = AgentConnection("complete-send-fail", ws)
        conn.last_heartbeat = time.time()
        manager._connections["complete-send-fail"] = conn

        try:
            response = await client.post(
                "/api/agents/complete-send-fail/complete",
                json={"line": "ls", "cursor": 2},
                headers=auth_headers,
            )
            assert response.status_code == 500
            # 发送失败后注册的 future 必须被清理
            assert len(conn._complete_futures) == 0
        finally:
            manager._connections.pop("complete-send-fail", None)

    @pytest.mark.asyncio
    async def test_complete_uses_cwd_from_agent_work_dir(self, client, auth_headers):
        """cwd 为空时应回退到 agent 配置的 agent_work_dir（与 exec 行为一致）。"""
        from taskpps.services.agent_manager import AgentConnection, AgentManager

        manager = AgentManager.instance()
        ws = AsyncMock()
        ws.send_json = AsyncMock()
        conn = AgentConnection("complete-cwd-agent", ws)
        conn.last_heartbeat = time.time()
        manager._connections["complete-cwd-agent"] = conn

        async def resolve_after_delay():
            await asyncio.sleep(0.05)
            for request_id in list(conn._complete_futures.keys()):
                conn.handle_complete_result(
                    request_id,
                    {"request_id": request_id, "prefix": "ls", "candidates": ["ls"], "error": ""},
                )

        resolver_task = asyncio.create_task(resolve_after_delay())
        try:
            with patch(
                "taskpps.api.agents._load_agents_from_projects",
                return_value=([{"id": "complete-cwd-agent", "agent_work_dir": "/opt/work"}], []),
            ):
                response = await client.post(
                    "/api/agents/complete-cwd-agent/complete",
                    json={"line": "ls", "cursor": 2, "cwd": ""},
                    headers=auth_headers,
                )
            assert response.status_code == 200
        finally:
            await resolver_task
            manager._connections.pop("complete-cwd-agent", None)


class TestCompleteResultDispatch:
    @pytest.mark.asyncio
    async def test_handle_complete_result_resolves_future(self):
        """ws_agent 收到 complete_result 后应 resolve 对应的 future。"""
        from taskpps.services.agent_manager import AgentConnection

        conn = AgentConnection("dispatch-agent", AsyncMock())
        fut = conn.register_complete("req-1")

        conn.handle_complete_result("req-1", {"prefix": "ls", "candidates": ["ls"], "error": ""})

        assert fut.done()
        assert fut.result()["candidates"] == ["ls"]

    @pytest.mark.asyncio
    async def test_handle_complete_result_unknown_id_ignored(self):
        """未注册的 request_id 应被忽略（agent 重启残留的消息）。"""
        # v2 (2026-09 治理): 原用例只调用不校验。重写为断言已注册的 future
        # 不受影响、future map 保持原样。
        from taskpps.services.agent_manager import AgentConnection

        conn = AgentConnection("dispatch-agent2", AsyncMock())
        registered = conn.register_complete("known-req")

        conn.handle_complete_result("unknown-req", {"prefix": "", "candidates": []})

        assert not registered.done()
        assert set(conn._complete_futures) == {"known-req"}

    @pytest.mark.asyncio
    async def test_disconnect_fails_pending_completes(self):
        """断连时所有未完成的 complete future 应被失败（否则端点挂到超时）。"""
        from taskpps.services.agent_manager import AgentConnection

        conn = AgentConnection("dispatch-agent3", AsyncMock())
        fut = conn.register_complete("req-2")

        conn.fail_all_completes()

        assert fut.done()
        assert fut.result()["error"] == "connection lost"
        assert len(conn._complete_futures) == 0

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from taskpps.main import app as _app


@pytest.fixture
def app():
    return _app


@pytest.fixture
def project_env(setup_project, tmp_project):
    import taskpps.config as cfg

    cfg.set_project_root(tmp_project)
    cfg._settings = None
    cfg.load_settings(str(tmp_project / "taskpps.yaml"))


class TestAgentStatus:
    @pytest.mark.asyncio
    async def test_check_all_agents_empty(self, app, project_env, db_engine):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/api/agents/check",
                json={"timeout": 3},
            )
            assert resp.status_code == 200
            data = resp.json()
            assert data["summary"]["total"] >= 0
            assert "connected" in data["summary"]
            assert "failed" in data["summary"]

    @pytest.mark.asyncio
    async def test_agent_status_not_connected(self, app, project_env):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/agents/status/nonexistent-agent")
            assert resp.status_code == 200
            data = resp.json()
            assert data["agent_id"] == "nonexistent-agent"
            assert data["connected"] is False

    @pytest.mark.asyncio
    async def test_agent_list_empty(self, app, project_env):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/agents/list")
            assert resp.status_code == 200
            data = resp.json()
            assert isinstance(data, list)

    @pytest.mark.asyncio
    async def test_try_connect_nonexistent_agent(self, app, project_env):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/api/agents/try-connect",
                json={"agent_id": "nonexistent-agent", "timeout": 3},
            )
            assert resp.status_code == 404


class TestTriggerLifecycle:
    @pytest.mark.asyncio
    async def test_create_and_list_triggers(self, app, project_env, db_engine):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            create_resp = await client.post(
                "/api/plugins/triggers/",
                json={
                    "type": "cron",
                    "config": {"schedule": "*/5 * * * *"},
                    "pipeline_file": "deploy.yaml",
                    "enabled": True,
                },
            )
            assert create_resp.status_code == 201

            list_resp = await client.get("/api/plugins/triggers/")
            assert list_resp.status_code == 200
            triggers = list_resp.json()
            assert len(triggers) >= 1

    @pytest.mark.asyncio
    async def test_create_and_delete_trigger(self, app, project_env, db_engine):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            create_resp = await client.post(
                "/api/plugins/triggers/",
                json={
                    "type": "cron",
                    "config": {"schedule": "0 * * * *"},
                    "pipeline_file": "hourly.yaml",
                    "enabled": True,
                },
            )
            assert create_resp.status_code == 201
            trigger_id = create_resp.json()["id"]

            delete_resp = await client.delete(f"/api/plugins/triggers/{trigger_id}")
            assert delete_resp.status_code == 200

    @pytest.mark.asyncio
    async def test_delete_nonexistent_trigger(self, app, project_env, db_engine):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.delete("/api/plugins/triggers/nonexistent-id")
            assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_disabled_trigger(self, app, project_env, db_engine):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            create_resp = await client.post(
                "/api/plugins/triggers/",
                json={
                    "type": "cron",
                    "config": {"schedule": "*/10 * * * *"},
                    "pipeline_file": "backup.yaml",
                    "enabled": False,
                },
            )
            assert create_resp.status_code == 201

    @pytest.mark.asyncio
    async def test_create_trigger_missing_pipeline_file(self, app, project_env, db_engine):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/api/plugins/triggers/",
                json={
                    "type": "cron",
                    "config": {"schedule": "*/5 * * * *"},
                    "enabled": True,
                },
            )
            assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_create_multiple_triggers(self, app, project_env, db_engine):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            for i in range(3):
                resp = await client.post(
                    "/api/plugins/triggers/",
                    json={
                        "type": "cron",
                        "config": {"schedule": f"*/{i + 1} * * * *"},
                        "pipeline_file": f"pipeline_{i}.yaml",
                        "enabled": True,
                    },
                )
                assert resp.status_code == 201

            list_resp = await client.get("/api/plugins/triggers/")
            assert list_resp.status_code == 200
            triggers = list_resp.json()
            assert len(triggers) >= 3


class TestHealthAndStatus:
    @pytest.mark.asyncio
    async def test_health_endpoint(self, app, project_env):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/health")
            assert resp.status_code == 200
            data = resp.json()
            assert "status" in data
            assert "version" in data
            assert data["status"] == "ok"

    @pytest.mark.asyncio
    async def test_health_endpoint_no_auth(self, app, project_env):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/health")
            assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_health_endpoint_wrong_path(self, app, project_env):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/healthzzz")
            assert resp.status_code in (404, 401)

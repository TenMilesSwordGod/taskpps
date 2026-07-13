from __future__ import annotations

from tests.conftest import resolve_def_id
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


class TestPipelineCreateAndFetch:
    @pytest.mark.asyncio
    @pytest.mark.zentao("TC-S0210", domain="server/scenario", priority="P2")
    async def test_create_run_and_fetch(self, app, project_env, db_engine):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            create_resp = await client.post(
                "/api/runs/",
                json={"definition_id": await resolve_def_id(client, "deploy.yaml")},
            )
            assert create_resp.status_code == 201
            run_data = create_resp.json()
            assert "id" in run_data
            assert run_data["pipeline_name"] == "deploy"
            assert run_data["status"] == "pending"

            run_id = run_data["id"]
            get_resp = await client.get(f"/api/runs/{run_id}")
            assert get_resp.status_code == 200
            assert get_resp.json()["id"] == run_id

    @pytest.mark.asyncio
    @pytest.mark.zentao("TC-S0211", domain="server/scenario", priority="P1")
    async def test_list_runs_after_create(self, app, project_env, db_engine):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            for name in ["simple.yaml", "deploy.yaml", "fail_test.yaml"]:
                def_id = await resolve_def_id(client, name)
                await client.post("/api/runs/", json={"definition_id": def_id})

            list_resp = await client.get("/api/runs/")
            assert list_resp.status_code == 200
            data = list_resp.json()
            assert len(data.get("items", [])) >= 3

    @pytest.mark.asyncio
    @pytest.mark.zentao("TC-S0212", domain="server/scenario", priority="P1")
    async def test_list_runs_filter_by_pipeline(self, app, project_env, db_engine):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            await client.post("/api/runs/", json={"definition_id": await resolve_def_id(client, "simple.yaml")})
            await client.post("/api/runs/", json={"definition_id": await resolve_def_id(client, "deploy.yaml")})

            list_resp = await client.get("/api/runs/", params={"pipeline": "simple"})
            assert list_resp.status_code == 200
            data = list_resp.json()
            for item in data.get("items", []):
                assert item["pipeline_name"] == "simple"

    @pytest.mark.asyncio
    @pytest.mark.zentao("TC-S0213", domain="server/scenario", priority="P1")
    async def test_list_runs_filter_by_status(self, app, project_env, db_engine):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            await client.post("/api/runs/", json={"definition_id": await resolve_def_id(client, "simple.yaml")})

            list_resp = await client.get("/api/runs/", params={"status": "pending"})
            assert list_resp.status_code == 200
            data = list_resp.json()
            for item in data.get("items", []):
                assert item["status"] == "pending"

    @pytest.mark.asyncio
    @pytest.mark.zentao("TC-S0214", domain="server/scenario", priority="P2")
    async def test_create_run_with_params(self, app, project_env, db_engine):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            create_resp = await client.post(
                "/api/runs/",
                json={
                    "definition_id": await resolve_def_id(client, "deploy.yaml"),
                    "params": {"config": {"env": {"version": "1.0", "env": "staging"}}},
                },
            )
            assert create_resp.status_code == 201
            run_data = create_resp.json()
            assert run_data["pipeline_name"] == "deploy"

    @pytest.mark.asyncio
    @pytest.mark.zentao("TC-S0215", domain="server/scenario", priority="P2")
    async def test_get_nonexistent_run(self, app, project_env, db_engine):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/runs/nonexistent-id")
            assert resp.status_code == 404


class TestPipelineCancel:
    @pytest.mark.asyncio
    @pytest.mark.zentao("TC-S0216", domain="server/scenario", priority="P1")
    async def test_cancel_pending_run(self, app, project_env, db_engine):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            create_resp = await client.post("/api/runs/", json={"definition_id": await resolve_def_id(client, "simple.yaml")})
            assert create_resp.status_code == 201
            run_id = create_resp.json()["id"]

            cancel_resp = await client.post(f"/api/runs/{run_id}/cancel")
            assert cancel_resp.status_code == 200

            get_resp = await client.get(f"/api/runs/{run_id}")
            assert get_resp.json()["status"] in ("cancelled", "pending", "running")

    @pytest.mark.asyncio
    @pytest.mark.zentao("TC-S0217", domain="server/scenario", priority="P1")
    async def test_cancel_nonexistent_run(self, app, project_env, db_engine):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post("/api/runs/nonexistent/cancel")
            assert resp.status_code == 404


class TestPipelineCleanup:
    @pytest.mark.asyncio
    @pytest.mark.zentao("TC-S0218", domain="server/scenario", priority="P1")
    async def test_cleanup_runs_force(self, app, project_env, db_engine):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            for _i in range(3):
                await client.post("/api/runs/", json={"definition_id": await resolve_def_id(client, "simple.yaml")})

            cleanup_resp = await client.delete(
                "/api/runs/",
                params={"force": True},
            )
            assert cleanup_resp.status_code == 200
            data = cleanup_resp.json()
            assert data.get("deleted_runs", 0) >= 3

    @pytest.mark.asyncio
    @pytest.mark.zentao("TC-S0219", domain="server/scenario", priority="P1")
    async def test_cleanup_no_force_no_delete_recent(self, app, project_env, db_engine):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            await client.post("/api/runs/", json={"definition_id": await resolve_def_id(client, "simple.yaml")})

            cleanup_resp = await client.delete(
                "/api/runs/",
                params={"older_than": 365},
            )
            assert cleanup_resp.status_code == 200
            data = cleanup_resp.json()
            assert data.get("deleted_runs", 0) == 0


class TestPipelineErrorHandling:
    @pytest.mark.asyncio
    @pytest.mark.zentao("TC-S0220", domain="server/scenario", priority="P2")
    async def test_create_run_missing_pipeline_field(self, app, project_env, db_engine):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post("/api/runs/", json={})
            assert resp.status_code == 422

    @pytest.mark.asyncio
    @pytest.mark.zentao("TC-S0221", domain="server/scenario", priority="P2")
    async def test_create_run_empty_pipeline_name(self, app, project_env, db_engine):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post("/api/runs/", json={"definition_id": ""})
            assert resp.status_code == 400

    @pytest.mark.asyncio
    @pytest.mark.zentao("TC-S0222", domain="server/scenario", priority="P2")
    async def test_create_run_nonexistent_pipeline(self, app, project_env, db_engine):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post("/api/runs/", json={"definition_id": "deadbeef1234", "params": {}})
            assert resp.status_code == 400

    @pytest.mark.asyncio
    @pytest.mark.zentao("TC-S0223", domain="server/scenario", priority="P2")
    async def test_invalid_json_body(self, app, project_env, db_engine):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/api/runs/",
                content="not-json",
                headers={"Content-Type": "application/json"},
            )
            assert resp.status_code == 422

    @pytest.mark.asyncio
    @pytest.mark.zentao("TC-S0224", domain="server/scenario", priority="P0")
    async def test_create_run_with_cycle_detection(self, app, project_env, db_engine):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post("/api/runs/", json={"definition_id": await resolve_def_id(client, "cycle.yaml")})
            assert resp.status_code == 400


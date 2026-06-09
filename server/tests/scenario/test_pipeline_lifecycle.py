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


class TestPipelineCreateAndFetch:
    @pytest.mark.asyncio
    async def test_create_run_and_fetch(self, app, project_env, db_engine):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            create_resp = await client.post(
                "/api/runs/",
                json={"pipeline": "deploy.yaml"},
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
    async def test_list_runs_after_create(self, app, project_env, db_engine):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            for name in ["simple.yaml", "deploy.yaml", "fail_test.yaml"]:
                await client.post("/api/runs/", json={"pipeline": name})

            list_resp = await client.get("/api/runs/")
            assert list_resp.status_code == 200
            data = list_resp.json()
            assert len(data.get("items", [])) >= 3

    @pytest.mark.asyncio
    async def test_list_runs_filter_by_pipeline(self, app, project_env, db_engine):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            await client.post("/api/runs/", json={"pipeline": "simple.yaml"})
            await client.post("/api/runs/", json={"pipeline": "deploy.yaml"})

            list_resp = await client.get("/api/runs/", params={"pipeline": "simple"})
            assert list_resp.status_code == 200
            data = list_resp.json()
            for item in data.get("items", []):
                assert item["pipeline_name"] == "simple"

    @pytest.mark.asyncio
    async def test_list_runs_filter_by_status(self, app, project_env, db_engine):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            await client.post("/api/runs/", json={"pipeline": "simple.yaml"})

            list_resp = await client.get("/api/runs/", params={"status": "pending"})
            assert list_resp.status_code == 200
            data = list_resp.json()
            for item in data.get("items", []):
                assert item["status"] == "pending"

    @pytest.mark.asyncio
    async def test_create_run_with_params(self, app, project_env, db_engine):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            create_resp = await client.post(
                "/api/runs/",
                json={
                    "pipeline": "deploy.yaml",
                    "params": {"config": {"env": {"version": "1.0", "env": "staging"}}},
                },
            )
            assert create_resp.status_code == 201
            run_data = create_resp.json()
            assert run_data["pipeline_name"] == "deploy"

    @pytest.mark.asyncio
    async def test_get_nonexistent_run(self, app, project_env, db_engine):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/runs/nonexistent-id")
            assert resp.status_code == 404


class TestPipelineCancel:
    @pytest.mark.asyncio
    async def test_cancel_pending_run(self, app, project_env, db_engine):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            create_resp = await client.post("/api/runs/", json={"pipeline": "simple.yaml"})
            assert create_resp.status_code == 201
            run_id = create_resp.json()["id"]

            cancel_resp = await client.post(f"/api/runs/{run_id}/cancel")
            assert cancel_resp.status_code == 200

            get_resp = await client.get(f"/api/runs/{run_id}")
            assert get_resp.json()["status"] in ("cancelled", "pending", "running")

    @pytest.mark.asyncio
    async def test_cancel_nonexistent_run(self, app, project_env, db_engine):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post("/api/runs/nonexistent/cancel")
            assert resp.status_code == 404


class TestPipelineCleanup:
    @pytest.mark.asyncio
    async def test_cleanup_runs_force(self, app, project_env, db_engine):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            for _i in range(3):
                await client.post("/api/runs/", json={"pipeline": "simple.yaml"})

            cleanup_resp = await client.delete(
                "/api/runs/",
                params={"force": True},
            )
            assert cleanup_resp.status_code == 200
            data = cleanup_resp.json()
            assert data.get("deleted_runs", 0) >= 3

    @pytest.mark.asyncio
    async def test_cleanup_no_force_no_delete_recent(self, app, project_env, db_engine):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            await client.post("/api/runs/", json={"pipeline": "simple"})

            cleanup_resp = await client.delete(
                "/api/runs/",
                params={"older_than": 365},
            )
            assert cleanup_resp.status_code == 200
            data = cleanup_resp.json()
            assert data.get("deleted_runs", 0) == 0


class TestPipelineErrorHandling:
    @pytest.mark.asyncio
    async def test_create_run_missing_pipeline_field(self, app, project_env, db_engine):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post("/api/runs/", json={})
            assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_create_run_empty_pipeline_name(self, app, project_env, db_engine):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post("/api/runs/", json={"pipeline": ""})
            assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_create_run_nonexistent_pipeline(self, app, project_env, db_engine):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post("/api/runs/", json={"pipeline": "nonexistent_pipeline_xyz"})
            assert resp.status_code == 400

    @pytest.mark.asyncio
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
    async def test_create_run_with_cycle_detection(self, app, project_env, db_engine):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post("/api/runs/", json={"pipeline": "cycle"})
            assert resp.status_code == 400

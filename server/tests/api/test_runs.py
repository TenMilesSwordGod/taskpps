from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from taskpps.main import app as _app


@pytest.fixture
def app():
    return _app


@pytest.mark.asyncio
async def test_health(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"


@pytest.mark.asyncio
async def test_list_runs(app, setup_project, tmp_project, db_engine):
    import taskpps.config as cfg

    cfg.set_project_root(tmp_project)
    cfg._settings = None
    cfg.load_settings(str(tmp_project / "taskpps.yaml"))

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/runs/")
        assert response.status_code == 200
        data = response.json()
        assert "total" in data
        assert "items" in data


@pytest.mark.asyncio
async def test_create_run(app, setup_project, tmp_project, db_engine):
    import taskpps.config as cfg

    cfg.set_project_root(tmp_project)
    cfg._settings = None
    cfg.load_settings(str(tmp_project / "taskpps.yaml"))

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/runs/",
            json={"pipeline": "deploy.yaml", "params": {}},
        )
        assert response.status_code in (200, 201)
        data = response.json()
        assert "id" in data


@pytest.mark.asyncio
async def test_get_run(app, setup_project, tmp_project, db_engine):
    import taskpps.config as cfg

    cfg.set_project_root(tmp_project)
    cfg._settings = None
    cfg.load_settings(str(tmp_project / "taskpps.yaml"))

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        create_resp = await client.post(
            "/api/runs/",
            json={"pipeline": "deploy.yaml", "params": {}},
        )
        run_id = create_resp.json()["id"]

        response = await client.get(f"/api/runs/{run_id}")
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == run_id


@pytest.mark.asyncio
async def test_get_run_not_found(app, setup_project, tmp_project, db_engine):
    import taskpps.config as cfg

    cfg.set_project_root(tmp_project)
    cfg._settings = None
    cfg.load_settings(str(tmp_project / "taskpps.yaml"))

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/runs/nonexistent")
        assert response.status_code == 404


@pytest.mark.asyncio
async def test_create_run_invalid(app, setup_project, tmp_project, db_engine):
    import taskpps.config as cfg

    cfg.set_project_root(tmp_project)
    cfg._settings = None
    cfg.load_settings(str(tmp_project / "taskpps.yaml"))

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/runs/",
            json={"pipeline": "nonexistent.yaml", "params": {}},
        )
        assert response.status_code in (400, 404, 422)


@pytest.mark.asyncio
async def test_cancel_run(app, setup_project, tmp_project, db_engine):
    import taskpps.config as cfg

    cfg.set_project_root(tmp_project)
    cfg._settings = None
    cfg.load_settings(str(tmp_project / "taskpps.yaml"))

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        create_resp = await client.post(
            "/api/runs/",
            json={"pipeline": "deploy.yaml", "params": {}},
        )
        run_id = create_resp.json()["id"]

        response = await client.post(f"/api/runs/{run_id}/cancel")
        assert response.status_code in (200, 400)


@pytest.mark.asyncio
async def test_list_runs_filter(app, setup_project, tmp_project, db_engine):
    import taskpps.config as cfg

    cfg.set_project_root(tmp_project)
    cfg._settings = None
    cfg.load_settings(str(tmp_project / "taskpps.yaml"))

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        await client.post("/api/runs/", json={"pipeline": "deploy.yaml", "params": {}})
        await client.post("/api/runs/", json={"pipeline": "simple.yaml", "params": {}})

        response = await client.get("/api/runs/?pipeline=deploy")
        assert response.status_code == 200
        data = response.json()
        items = data["items"]
        for item in items:
            assert item["pipeline_name"] == "deploy"


@pytest.mark.asyncio
async def test_list_runs_limit(app, setup_project, tmp_project, db_engine):
    import taskpps.config as cfg

    cfg.set_project_root(tmp_project)
    cfg._settings = None
    cfg.load_settings(str(tmp_project / "taskpps.yaml"))

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/runs/?limit=5")
        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) <= 5


@pytest.mark.asyncio
async def test_get_run_logs(app, setup_project, tmp_project, db_engine):
    import taskpps.config as cfg

    cfg.set_project_root(tmp_project)
    cfg._settings = None
    cfg.load_settings(str(tmp_project / "taskpps.yaml"))

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        create_resp = await client.post(
            "/api/runs/",
            json={"pipeline": "deploy.yaml", "params": {}},
        )
        run_id = create_resp.json()["id"]

        from taskpps.config import get_logs_dir

        log_dir = get_logs_dir() / "deploy" / run_id / "step1"
        log_dir.mkdir(parents=True, exist_ok=True)
        (log_dir / "task.log").write_text("test log content")

        response = await client.get(f"/api/runs/{run_id}/logs")
        assert response.status_code == 200


@pytest.mark.asyncio
async def test_clean_runs(app, setup_project, tmp_project, db_engine):
    import taskpps.config as cfg

    cfg.set_project_root(tmp_project)
    cfg._settings = None
    cfg.load_settings(str(tmp_project / "taskpps.yaml"))

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.delete("/api/runs/")
        assert response.status_code == 200
        data = response.json()
        assert "deleted_runs" in data


@pytest.mark.asyncio
async def test_clean_runs_older_than(app, setup_project, tmp_project, db_engine):
    import taskpps.config as cfg

    cfg.set_project_root(tmp_project)
    cfg._settings = None
    cfg.load_settings(str(tmp_project / "taskpps.yaml"))

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.delete("/api/runs/?older_than=7")
        assert response.status_code == 200
        data = response.json()
        assert "deleted_runs" in data


@pytest.mark.asyncio
async def test_pipeline_snapshot(app, setup_project, tmp_project, db_engine):
    """Issue #58: 获取运行的流水线快照"""
    import taskpps.config as cfg

    cfg.set_project_root(tmp_project)
    cfg._settings = None
    cfg.load_settings(str(tmp_project / "taskpps.yaml"))

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        create_resp = await client.post(
            "/api/runs/",
            json={"pipeline": "deploy.yaml", "params": {}},
        )
        run_id = create_resp.json()["id"]

        response = await client.get(f"/api/runs/{run_id}/pipeline-snapshot")
        assert response.status_code == 200
        data = response.json()
        assert "name" in data


@pytest.mark.asyncio
async def test_pipeline_snapshot_not_found(app, setup_project, tmp_project, db_engine):
    """Issue #58: 不存在的运行返回 404"""
    import taskpps.config as cfg

    cfg.set_project_root(tmp_project)
    cfg._settings = None
    cfg.load_settings(str(tmp_project / "taskpps.yaml"))

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/runs/nonexistent/pipeline-snapshot")
        assert response.status_code == 404


@pytest.mark.asyncio
async def test_delete_single_run(app, setup_project, tmp_project, db_engine):
    """Issue #55: 删除单条运行记录"""
    import taskpps.config as cfg

    cfg.set_project_root(tmp_project)
    cfg._settings = None
    cfg.load_settings(str(tmp_project / "taskpps.yaml"))

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        create_resp = await client.post(
            "/api/runs/",
            json={"pipeline": "deploy.yaml", "params": {}},
        )
        run_id = create_resp.json()["id"]

        response = await client.delete(f"/api/runs/{run_id}")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "deleted"

        get_resp = await client.get(f"/api/runs/{run_id}")
        assert get_resp.status_code == 404


@pytest.mark.asyncio
async def test_delete_run_not_found(app, setup_project, tmp_project, db_engine):
    """Issue #55: 删除不存在的运行返回 404"""
    import taskpps.config as cfg

    cfg.set_project_root(tmp_project)
    cfg._settings = None
    cfg.load_settings(str(tmp_project / "taskpps.yaml"))

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.delete("/api/runs/nonexistent")
        assert response.status_code == 404


@pytest.mark.asyncio
async def test_no_auth_header(app, setup_project, tmp_project, db_engine):
    import taskpps.config as cfg

    cfg.set_project_root(tmp_project)
    cfg._settings = None
    cfg.load_settings(str(tmp_project / "taskpps.yaml"))

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/health")
        assert response.status_code == 200


@pytest.mark.asyncio
async def test_run_stats(app, setup_project, tmp_project, db_engine):
    """Issue #89: 运行历史状态统计接口"""
    import taskpps.config as cfg

    cfg.set_project_root(tmp_project)
    cfg._settings = None
    cfg.load_settings(str(tmp_project / "taskpps.yaml"))

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 创建几条运行记录
        await client.post("/api/runs/", json={"pipeline": "deploy.yaml", "params": {}})
        await client.post("/api/runs/", json={"pipeline": "simple.yaml", "params": {}})

        response = await client.get("/api/runs/stats")
        assert response.status_code == 200
        data = response.json()
        assert "total" in data
        assert "pending" in data
        assert "running" in data
        assert "success" in data
        assert "failed" in data
        assert "cancelled" in data
        assert "partial" in data
        assert data["total"] >= 2
        # 新创建的运行默认为 pending 状态
        assert data["pending"] >= 2


@pytest.mark.asyncio
async def test_run_stats_with_pipeline_filter(app, setup_project, tmp_project, db_engine):
    """Issue #89: 运行历史状态统计支持 pipeline 过滤"""
    import taskpps.config as cfg

    cfg.set_project_root(tmp_project)
    cfg._settings = None
    cfg.load_settings(str(tmp_project / "taskpps.yaml"))

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        await client.post("/api/runs/", json={"pipeline": "deploy.yaml", "params": {}})
        await client.post("/api/runs/", json={"pipeline": "simple.yaml", "params": {}})

        response = await client.get("/api/runs/stats?pipeline=deploy")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] >= 1

from __future__ import annotations

from tests.conftest import resolve_def_id
import pytest
from httpx import ASGITransport, AsyncClient

from taskpps.main import app as _app


@pytest.fixture
def app():
    return _app


@pytest.mark.asyncio
@pytest.mark.zentao("TC-S0981", domain="server/api", priority="P2")
async def test_health(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"


@pytest.mark.asyncio
@pytest.mark.zentao("TC-S0982", domain="server/api", priority="P1")
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
@pytest.mark.zentao("TC-S0983", domain="server/api", priority="P2")
async def test_create_run(app, setup_project, tmp_project, db_engine):
    import taskpps.config as cfg

    cfg.set_project_root(tmp_project)
    cfg._settings = None
    cfg.load_settings(str(tmp_project / "taskpps.yaml"))

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/runs/",
            json={"definition_id": await resolve_def_id(client, "deploy.yaml"), "params": {}},
        )
        assert response.status_code in (200, 201)
        data = response.json()
        assert "id" in data


@pytest.mark.asyncio
@pytest.mark.zentao("TC-S0984", domain="server/api", priority="P1")
async def test_get_run(app, setup_project, tmp_project, db_engine):
    import taskpps.config as cfg

    cfg.set_project_root(tmp_project)
    cfg._settings = None
    cfg.load_settings(str(tmp_project / "taskpps.yaml"))

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        create_resp = await client.post(
            "/api/runs/",
            json={"definition_id": await resolve_def_id(client, "deploy.yaml"), "params": {}},
        )
        run_id = create_resp.json()["id"]

        response = await client.get(f"/api/runs/{run_id}")
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == run_id


@pytest.mark.asyncio
@pytest.mark.zentao("TC-S0985", domain="server/api", priority="P1")
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
@pytest.mark.zentao("TC-S0986", domain="server/api", priority="P2")
async def test_create_run_invalid(app, setup_project, tmp_project, db_engine):
    import taskpps.config as cfg

    cfg.set_project_root(tmp_project)
    cfg._settings = None
    cfg.load_settings(str(tmp_project / "taskpps.yaml"))

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/runs/",
            json={"definition_id": "deadbeef1234", "params": {}},
        )
        assert response.status_code in (400, 404, 422)


@pytest.mark.asyncio
@pytest.mark.zentao("TC-S0987", domain="server/api", priority="P1")
async def test_cancel_run(app, setup_project, tmp_project, db_engine):
    import taskpps.config as cfg

    cfg.set_project_root(tmp_project)
    cfg._settings = None
    cfg.load_settings(str(tmp_project / "taskpps.yaml"))

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        create_resp = await client.post(
            "/api/runs/",
            json={"definition_id": await resolve_def_id(client, "deploy.yaml"), "params": {}},
        )
        run_id = create_resp.json()["id"]

        response = await client.post(f"/api/runs/{run_id}/cancel")
        assert response.status_code in (200, 400)


@pytest.mark.asyncio
@pytest.mark.zentao("TC-S0988", domain="server/api", priority="P1")
async def test_list_runs_filter(app, setup_project, tmp_project, db_engine):
    import taskpps.config as cfg

    cfg.set_project_root(tmp_project)
    cfg._settings = None
    cfg.load_settings(str(tmp_project / "taskpps.yaml"))

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        await client.post("/api/runs/", json={"definition_id": await resolve_def_id(client, "deploy.yaml"), "params": {}})
        await client.post("/api/runs/", json={"definition_id": await resolve_def_id(client, "simple.yaml"), "params": {}})

        response = await client.get("/api/runs/?pipeline=deploy")
        assert response.status_code == 200
        data = response.json()
        items = data["items"]
        for item in items:
            assert item["pipeline_name"] == "deploy"


@pytest.mark.asyncio
@pytest.mark.zentao("TC-S0989", domain="server/api", priority="P1")
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
@pytest.mark.zentao("TC-S0990", domain="server/api", priority="P1")
async def test_get_run_logs(app, setup_project, tmp_project, db_engine):
    import taskpps.config as cfg

    cfg.set_project_root(tmp_project)
    cfg._settings = None
    cfg.load_settings(str(tmp_project / "taskpps.yaml"))

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        create_resp = await client.post(
            "/api/runs/",
            json={"definition_id": await resolve_def_id(client, "deploy.yaml"), "params": {}},
        )
        run_id = create_resp.json()["id"]

        from taskpps.config import get_logs_dir

        log_dir = get_logs_dir() / "deploy" / run_id / "step1"
        log_dir.mkdir(parents=True, exist_ok=True)
        (log_dir / "task.log").write_text("test log content")

        response = await client.get(f"/api/runs/{run_id}/logs")
        assert response.status_code == 200


@pytest.mark.asyncio
@pytest.mark.zentao("TC-S0991", domain="server/api", priority="P1")
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
@pytest.mark.zentao("TC-S0992", domain="server/api", priority="P1")
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
@pytest.mark.zentao("TC-S0993", domain="server/api", priority="P2")
@pytest.mark.zcustom("TC-S0993", domain="server/api", priority="P1")
# v2 (2026-07): Phase 2 CreateRunRequest 改用 definition_id，部分测试直接调列表API
# resolve_def_id 内自动注册项目，确保列表API有注册项目可同步 pipeline_definitions
# v2 (2026-07): Phase 2 快照只从 DB 读取，不存在则 404
async def test_pipeline_snapshot(app, setup_project, tmp_project, db_engine):
    """获取运行的流水线快照"""
    import taskpps.config as cfg

    cfg.set_project_root(tmp_project)
    cfg._settings = None
    cfg.load_settings(str(tmp_project / "taskpps.yaml"))

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # resolve_def_id 内自动注册项目，此后列表API可正常同步 definitions
        def_id = await resolve_def_id(client, "deploy.yaml")

        create_resp = await client.post(
            "/api/runs/",
            json={"definition_id": def_id, "params": {}},
        )
        run_id = create_resp.json()["id"]

        response = await client.get(f"/api/runs/{run_id}/pipeline-snapshot")
        assert response.status_code == 200
        data = response.json()
        assert "name" in data


@pytest.mark.asyncio
@pytest.mark.zentao("TC-S0994", domain="server/api", priority="P1")
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
@pytest.mark.zentao("TC-S0995", domain="server/api", priority="P2")
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
            json={"definition_id": await resolve_def_id(client, "deploy.yaml"), "params": {}},
        )
        run_id = create_resp.json()["id"]

        response = await client.delete(f"/api/runs/{run_id}")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "deleted"

        get_resp = await client.get(f"/api/runs/{run_id}")
        assert get_resp.status_code == 404


@pytest.mark.asyncio
@pytest.mark.zentao("TC-S0996", domain="server/api", priority="P1")
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
@pytest.mark.zentao("TC-S0997", domain="server/api", priority="P2")
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
@pytest.mark.zentao("TC-S0998", domain="server/api", priority="P2")
async def test_run_stats(app, setup_project, tmp_project, db_engine):
    """Issue #89: 运行历史状态统计接口"""
    import taskpps.config as cfg

    cfg.set_project_root(tmp_project)
    cfg._settings = None
    cfg.load_settings(str(tmp_project / "taskpps.yaml"))

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 创建几条运行记录
        await client.post("/api/runs/", json={"definition_id": await resolve_def_id(client, "deploy.yaml"), "params": {}})
        await client.post("/api/runs/", json={"definition_id": await resolve_def_id(client, "simple.yaml"), "params": {}})

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
        # 各状态计数之和应等于总数（不依赖具体状态，因为后台 runner 可能已让运行状态变化）
        assert (
            data["pending"] + data["running"] + data["success"] + data["failed"] + data["cancelled"] + data["partial"]
            == data["total"]
        )


@pytest.mark.asyncio
@pytest.mark.zentao("TC-S0999", domain="server/api", priority="P1")
async def test_run_stats_with_pipeline_filter(app, setup_project, tmp_project, db_engine):
    """Issue #89: 运行历史状态统计支持 pipeline 过滤"""
    import taskpps.config as cfg

    cfg.set_project_root(tmp_project)
    cfg._settings = None
    cfg.load_settings(str(tmp_project / "taskpps.yaml"))

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        await client.post("/api/runs/", json={"definition_id": await resolve_def_id(client, "deploy.yaml"), "params": {}})
        await client.post("/api/runs/", json={"definition_id": await resolve_def_id(client, "simple.yaml"), "params": {}})

        response = await client.get("/api/runs/stats?pipeline=deploy")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] >= 1


@pytest.mark.asyncio
@pytest.mark.zentao("TC-S1000", domain="server/api", priority="P1")
async def test_cancel_retry_run_api(app, setup_project, tmp_project, db_engine):
    """Issue #102: 取消重试 API 在存在活跃 RetryRunner 时返回 200。"""
    from unittest.mock import AsyncMock, patch

    import taskpps.config as cfg

    cfg.set_project_root(tmp_project)
    cfg._settings = None
    cfg.load_settings(str(tmp_project / "taskpps.yaml"))

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        create_resp = await client.post("/api/runs/", json={"definition_id": await resolve_def_id(client, "deploy.yaml"), "params": {}})
        run_id = create_resp.json()["id"]

        mock_runner = AsyncMock()
        with patch("taskpps.services.pipeline_service.get_active_retry_runner", return_value=mock_runner):
            response = await client.post(f"/api/runs/{run_id}/retry/cancel")
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "cancelled"
            assert data["run_id"] == run_id
            mock_runner.cancel.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.zentao("TC-S1001", domain="server/api", priority="P1")
async def test_cancel_retry_run_api_no_active_retry(app, setup_project, tmp_project, db_engine):
    """Issue #102: 无活跃重试时取消重试 API 返回 404。"""
    import taskpps.config as cfg

    cfg.set_project_root(tmp_project)
    cfg._settings = None
    cfg.load_settings(str(tmp_project / "taskpps.yaml"))

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        create_resp = await client.post("/api/runs/", json={"definition_id": await resolve_def_id(client, "deploy.yaml"), "params": {}})
        run_id = create_resp.json()["id"]

        response = await client.post(f"/api/runs/{run_id}/retry/cancel")
        assert response.status_code == 404


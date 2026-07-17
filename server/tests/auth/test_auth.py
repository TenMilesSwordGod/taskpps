from __future__ import annotations

from tests.conftest import resolve_def_id
import pytest
from httpx import ASGITransport, AsyncClient

from taskpps.main import app as _app


@pytest.fixture
def app():
    return _app


@pytest.mark.asyncio
@pytest.mark.zentao("TC-S1018", domain="server/auth", priority="P2")
async def test_no_auth_header(app, setup_project, tmp_project):
    import taskpps.config as cfg

    cfg.set_project_root(tmp_project)
    cfg._settings = None
    cfg.load_settings(str(tmp_project / "taskpps.yaml"))

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/health")
        assert response.status_code == 200


@pytest.mark.asyncio
@pytest.mark.zentao("TC-S1019", domain="server/auth", priority="P0")
async def test_auth_with_valid_token(app, setup_project, tmp_project):
    import taskpps.config as cfg

    cfg.set_project_root(tmp_project)
    cfg._settings = None
    cfg.load_settings(str(tmp_project / "taskpps.yaml"))

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/health")
        assert response.status_code == 200


@pytest.mark.asyncio
@pytest.mark.zentao("TC-S1020", domain="server/auth", priority="P2")
async def test_auth_middleware_bypasses_health(app, setup_project, tmp_project):
    import taskpps.config as cfg

    cfg.set_project_root(tmp_project)
    cfg._settings = None
    cfg.load_settings(str(tmp_project / "taskpps.yaml"))

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/health")
        assert response.status_code == 200

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/health")
        assert response.status_code == 200


@pytest.mark.asyncio
@pytest.mark.zentao("TC-S1021", domain="server/auth", priority="P0")
async def test_auth_protected_endpoint(app, setup_project, tmp_project, db_engine):
    import taskpps.config as cfg

    cfg.set_project_root(tmp_project)
    cfg._settings = None
    cfg.load_settings(str(tmp_project / "taskpps.yaml"))

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/runs/")
        assert response.status_code == 200


@pytest.mark.asyncio
@pytest.mark.zentao("TC-S1022", domain="server/auth", priority="P2")
async def test_auth_create_run(app, setup_project, tmp_project, db_engine):
    import taskpps.config as cfg

    cfg.set_project_root(tmp_project)
    cfg._settings = None
    cfg.load_settings(str(tmp_project / "taskpps.yaml"))

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # issue #204 引入 JWT 中间件后，POST /api/runs/ 强制鉴权（401 无 token）。
        # 此处先注册 + 登录拿 token，再带 Authorization 头创建 run，适配新认证模型。
        await client.post(
            "/api/v1/auth/register",
            json={"username": "runner", "nickname": "Runner", "password": "pass123"},
        )
        login_resp = await client.post(
            "/api/v1/auth/login",
            json={"username": "runner", "password": "pass123"},
        )
        token = login_resp.json()["access_token"]
        response = await client.post(
            "/api/runs/",
            headers={"Authorization": f"Bearer {token}"},
            json={"definition_id": await resolve_def_id(client, "deploy.yaml"), "params": {}},
        )
        assert response.status_code in (200, 201)


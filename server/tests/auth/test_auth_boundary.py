from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from taskpps.main import app as _app


@pytest.fixture
def app():
    return _app


@pytest.mark.asyncio
async def test_missing_api_key_header(app, setup_project, tmp_project):
    import taskpps.config as cfg

    config_file = tmp_project / "taskpps.yaml"
    config_file.write_text("server:\n  host: 127.0.0.1\n  port: 26521\n  api_key: secret123\n")

    cfg.set_project_root(tmp_project)
    cfg._settings = None
    cfg.load_settings(str(config_file))

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/runs/")
        assert response.status_code == 401


@pytest.mark.asyncio
async def test_invalid_api_key(app, setup_project, tmp_project):
    import taskpps.config as cfg

    config_file = tmp_project / "taskpps.yaml"
    config_file.write_text("server:\n  host: 127.0.0.1\n  port: 26521\n  api_key: secret123\n")

    cfg.set_project_root(tmp_project)
    cfg._settings = None
    cfg.load_settings(str(config_file))

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/runs/", headers={"X-API-Key": "wrong_key"})
        assert response.status_code == 401


@pytest.mark.asyncio
async def test_valid_api_key(app, setup_project, tmp_project, db_engine):
    import taskpps.config as cfg

    config_file = tmp_project / "taskpps.yaml"
    config_file.write_text("server:\n  host: 127.0.0.1\n  port: 26521\n  api_key: secret123\n")

    cfg.set_project_root(tmp_project)
    cfg._settings = None
    cfg.load_settings(str(config_file))

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/runs/", headers={"X-API-Key": "secret123"})
        assert response.status_code == 200


@pytest.mark.asyncio
async def test_options_request_bypasses_auth(app, setup_project, tmp_project):
    import taskpps.config as cfg

    config_file = tmp_project / "taskpps.yaml"
    config_file.write_text("server:\n  host: 127.0.0.1\n  port: 26521\n  api_key: secret123\n")

    cfg.set_project_root(tmp_project)
    cfg._settings = None
    cfg.load_settings(str(config_file))

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.options("/api/runs/")
        assert response.status_code in (200, 204, 405)


@pytest.mark.asyncio
async def test_no_auth_when_api_key_none(app, setup_project, tmp_project, db_engine):
    import taskpps.config as cfg

    config_file = tmp_project / "taskpps.yaml"
    config_file.write_text("server:\n  host: 127.0.0.1\n  port: 26521\n")

    cfg.set_project_root(tmp_project)
    cfg._settings = None
    cfg.load_settings(str(config_file))

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/runs/")
        assert response.status_code == 200


@pytest.mark.asyncio
async def test_health_bypasses_auth_with_key(app, setup_project, tmp_project):
    import taskpps.config as cfg

    config_file = tmp_project / "taskpps.yaml"
    config_file.write_text("server:\n  host: 127.0.0.1\n  port: 26521\n  api_key: secret123\n")

    cfg.set_project_root(tmp_project)
    cfg._settings = None
    cfg.load_settings(str(config_file))

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/health")
        assert response.status_code == 200


@pytest.mark.asyncio
async def test_ws_path_bypasses_auth(app, setup_project, tmp_project):
    import taskpps.config as cfg

    config_file = tmp_project / "taskpps.yaml"
    config_file.write_text("server:\n  host: 127.0.0.1\n  port: 26521\n  api_key: secret123\n")

    cfg.set_project_root(tmp_project)
    cfg._settings = None
    cfg.load_settings(str(config_file))

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/ws/status")
        assert response.status_code in (200, 404, 405)


@pytest.mark.asyncio
async def test_empty_api_key(app, setup_project, tmp_project):
    import taskpps.config as cfg

    config_file = tmp_project / "taskpps.yaml"
    config_file.write_text("server:\n  host: 127.0.0.1\n  port: 26521\n  api_key: secret123\n")

    cfg.set_project_root(tmp_project)
    cfg._settings = None
    cfg.load_settings(str(config_file))

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/runs/", headers={"X-API-Key": ""})
        assert response.status_code == 401
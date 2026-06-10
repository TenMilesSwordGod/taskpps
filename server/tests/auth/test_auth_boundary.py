from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from taskpps.main import app as _app


@pytest.fixture
def app():
    return _app


def _setup_auth_config(tmp_project, config_content):
    import taskpps.config as cfg

    config_file = tmp_project / "taskpps.yaml"
    original = config_file.read_text() if config_file.exists() else None

    config_file.write_text(config_content)

    cfg.set_project_root(tmp_project)
    cfg._settings = None
    cfg.load_settings(str(config_file))

    return original


def _restore_config(tmp_project, original):
    if original is not None:
        config_file = tmp_project / "taskpps.yaml"
        config_file.write_text(original)


@pytest.mark.asyncio
async def test_missing_api_key_header(app, setup_project, tmp_project):
    original = _setup_auth_config(tmp_project, "server:\n  host: 127.0.0.1\n  port: 26521\n  api_key: secret123\n")
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/api/runs/")
            assert response.status_code == 401
    finally:
        _restore_config(tmp_project, original)


@pytest.mark.asyncio
async def test_invalid_api_key(app, setup_project, tmp_project):
    original = _setup_auth_config(tmp_project, "server:\n  host: 127.0.0.1\n  port: 26521\n  api_key: secret123\n")
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/api/runs/", headers={"X-API-Key": "wrong_key"})
            assert response.status_code == 401
    finally:
        _restore_config(tmp_project, original)


@pytest.mark.asyncio
async def test_valid_api_key(app, setup_project, tmp_project, db_engine):
    original = _setup_auth_config(tmp_project, "server:\n  host: 127.0.0.1\n  port: 26521\n  api_key: secret123\n")
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/api/runs/", headers={"X-API-Key": "secret123"})
            assert response.status_code == 200
    finally:
        _restore_config(tmp_project, original)


@pytest.mark.asyncio
async def test_options_request_bypasses_auth(app, setup_project, tmp_project):
    original = _setup_auth_config(tmp_project, "server:\n  host: 127.0.0.1\n  port: 26521\n  api_key: secret123\n")
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.options("/api/runs/")
            assert response.status_code in (200, 204, 405)
    finally:
        _restore_config(tmp_project, original)


@pytest.mark.asyncio
async def test_no_auth_when_api_key_none(app, setup_project, tmp_project, db_engine):
    original = _setup_auth_config(tmp_project, "server:\n  host: 127.0.0.1\n  port: 26521\n")
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/api/runs/")
            assert response.status_code == 200
    finally:
        _restore_config(tmp_project, original)


@pytest.mark.asyncio
async def test_health_bypasses_auth_with_key(app, setup_project, tmp_project):
    original = _setup_auth_config(tmp_project, "server:\n  host: 127.0.0.1\n  port: 26521\n  api_key: secret123\n")
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/api/health")
            assert response.status_code == 200
    finally:
        _restore_config(tmp_project, original)


@pytest.mark.asyncio
async def test_ws_path_bypasses_auth(app, setup_project, tmp_project):
    original = _setup_auth_config(tmp_project, "server:\n  host: 127.0.0.1\n  port: 26521\n  api_key: secret123\n")
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/api/ws/status")
            assert response.status_code in (200, 404, 405)
    finally:
        _restore_config(tmp_project, original)


@pytest.mark.asyncio
async def test_empty_api_key(app, setup_project, tmp_project):
    original = _setup_auth_config(tmp_project, "server:\n  host: 127.0.0.1\n  port: 26521\n  api_key: secret123\n")
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/api/runs/", headers={"X-API-Key": ""})
            assert response.status_code == 401
    finally:
        _restore_config(tmp_project, original)


@pytest.mark.asyncio
async def test_root_path_not_blocked_by_auth(app, setup_project, tmp_project):
    """GET / 不应被 API key 拦截返回 401，应透传到静态文件处理（200 或 404）。"""
    original = _setup_auth_config(tmp_project, "server:\n  host: 127.0.0.1\n  port: 26521\n  api_key: secret123\n")
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/")
            # 不是 401 就对了（实际可能是 200 有 index.html 或 404 没有静态目录）
            assert response.status_code != 401
    finally:
        _restore_config(tmp_project, original)


@pytest.mark.asyncio
async def test_favicon_not_blocked_by_auth(app, setup_project, tmp_project):
    """GET /favicon.ico 不应被 API key 拦截返回 401。"""
    original = _setup_auth_config(tmp_project, "server:\n  host: 127.0.0.1\n  port: 26521\n  api_key: secret123\n")
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/favicon.ico")
            assert response.status_code != 401
    finally:
        _restore_config(tmp_project, original)


@pytest.mark.asyncio
async def test_assets_path_not_blocked_by_auth(app, setup_project, tmp_project):
    """GET /assets/... 不应被 API key 拦截返回 401。"""
    original = _setup_auth_config(tmp_project, "server:\n  host: 127.0.0.1\n  port: 26521\n  api_key: secret123\n")
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/assets/index-abc123.js")
            assert response.status_code != 401
    finally:
        _restore_config(tmp_project, original)

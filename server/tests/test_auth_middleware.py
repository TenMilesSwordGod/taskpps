import pytest
from httpx import ASGITransport, AsyncClient

from taskpps.main import app


@pytest.mark.asyncio
async def test_auth_disabled_no_key(db_engine):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.get("/api/health")
        assert resp.status_code == 200


@pytest.mark.asyncio
async def test_auth_disabled_runs(db_engine):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.get("/api/runs/")
        assert resp.status_code == 200


@pytest.mark.asyncio
async def test_auth_enabled_valid_key(db_engine):
    from taskpps.config import get_settings

    settings = get_settings()
    settings.server.api_key = "test-key-123"
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.get("/api/health")
        assert resp.status_code == 200


@pytest.mark.asyncio
async def test_auth_enabled_invalid_key(db_engine):
    from taskpps.config import get_settings

    settings = get_settings()
    settings.server.api_key = "test-key-123"
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.get("/api/runs/", headers={"X-API-Key": "wrong-key"})
        assert resp.status_code == 401


@pytest.mark.asyncio
async def test_auth_enabled_missing_key(db_engine):
    from taskpps.config import get_settings

    settings = get_settings()
    settings.server.api_key = "test-key-123"
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.get("/api/runs/")
        assert resp.status_code == 401


@pytest.mark.asyncio
async def test_auth_enabled_options_skip(db_engine):
    from taskpps.config import get_settings

    settings = get_settings()
    settings.server.api_key = "test-key-123"
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.options("/api/runs/")
        assert resp.status_code != 401


@pytest.mark.asyncio
async def test_auth_enabled_health_skip(db_engine):
    from taskpps.config import get_settings

    settings = get_settings()
    settings.server.api_key = "test-key-123"
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.get("/api/health")
        assert resp.status_code == 200


@pytest.mark.asyncio
async def test_auth_enabled_health_skip_no_key(db_engine):
    from taskpps.config import get_settings

    settings = get_settings()
    settings.server.api_key = "test-key-123"
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.get("/api/health", headers={"X-API-Key": "wrong-key"})
        assert resp.status_code == 200


@pytest.mark.asyncio
async def test_auth_enabled_valid_key_on_runs(db_engine):
    from taskpps.config import get_settings

    settings = get_settings()
    settings.server.api_key = "test-key-123"
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.get("/api/runs/", headers={"X-API-Key": "test-key-123"})
        assert resp.status_code == 200

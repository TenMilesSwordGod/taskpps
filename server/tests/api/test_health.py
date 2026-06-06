from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from taskpps.main import app as _app
from taskpps.version import __version__


@pytest.fixture
def app():
    return _app


@pytest.mark.asyncio
async def test_health_check_returns_ok(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert data["version"] == __version__


@pytest.mark.asyncio
async def test_health_check_response_headers(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/health")
        assert "content-type" in response.headers


@pytest.mark.asyncio
async def test_health_check_multiple_requests(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        for _ in range(5):
            response = await client.get("/api/health")
            assert response.status_code == 200
            assert response.json()["status"] == "ok"


@pytest.mark.asyncio
async def test_health_check_no_auth_required(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/health")
        assert response.status_code == 200


@pytest.mark.asyncio
async def test_health_check_not_found_on_wrong_path(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/healthzzz")
        assert response.status_code in (404, 401)
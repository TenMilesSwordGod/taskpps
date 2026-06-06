from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from taskpps.main import app as _app


@pytest.fixture
def app():
    return _app


@pytest.mark.asyncio
async def test_try_connect(app, setup_project, tmp_project):
    import taskpps.config as cfg

    cfg.set_project_root(tmp_project)
    cfg._settings = None
    cfg.load_settings(str(tmp_project / "taskpps.yaml"))

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/agents/try-connect",
            json={"agent_id": "staging-server", "timeout": 5},
        )
        assert response.status_code in (200, 400, 404)


@pytest.mark.asyncio
async def test_check(app, setup_project, tmp_project):
    import taskpps.config as cfg

    cfg.set_project_root(tmp_project)
    cfg._settings = None
    cfg.load_settings(str(tmp_project / "taskpps.yaml"))

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/agents/check",
            json={"agent_id": "staging-server"},
        )
        assert response.status_code in (200, 400, 404)


@pytest.mark.asyncio
async def test_check_agent_not_found(app, setup_project, tmp_project):
    import taskpps.config as cfg

    cfg.set_project_root(tmp_project)
    cfg._settings = None
    cfg.load_settings(str(tmp_project / "taskpps.yaml"))

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/agents/try-connect",
            json={"agent_id": "nonexistent", "timeout": 5},
        )
        assert response.status_code in (400, 404)

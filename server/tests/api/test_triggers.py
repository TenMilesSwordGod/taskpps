from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from taskpps.main import app as _app


@pytest.fixture
def app():
    return _app


@pytest.mark.asyncio
@pytest.mark.zentao("TC-S1002", domain="server/api", priority="P2")
async def test_create_trigger(app, db_engine):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/plugins/triggers/",
            json={
                "type": "cron",
                "config": {"schedule": "*/5 * * * *"},
                "pipeline_file": "deploy.yaml",
                "enabled": True,
            },
        )
        assert response.status_code == 201


@pytest.mark.asyncio
@pytest.mark.zentao("TC-S1003", domain="server/api", priority="P2")
async def test_list_triggers(app, db_engine):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/plugins/triggers/")
        assert response.status_code == 200


@pytest.mark.asyncio
@pytest.mark.zentao("TC-S1004", domain="server/api", priority="P2")
async def test_delete_trigger(app, db_engine):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        create_resp = await client.post(
            "/api/plugins/triggers/",
            json={
                "type": "cron",
                "config": {"schedule": "*/5 * * * *"},
                "pipeline_file": "deploy.yaml",
                "enabled": True,
            },
        )
        trigger_id = create_resp.json()["id"]

        response = await client.delete(f"/api/plugins/triggers/{trigger_id}")
        assert response.status_code == 200


@pytest.mark.asyncio
@pytest.mark.zentao("TC-S1005", domain="server/api", priority="P2")
async def test_delete_nonexistent_trigger(app, db_engine):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.delete("/api/plugins/triggers/nonexistent-id")
        assert response.status_code == 404


@pytest.mark.asyncio
@pytest.mark.zentao("TC-S1006", domain="server/api", priority="P2")
async def test_create_trigger_without_pipeline_file(app, db_engine):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/plugins/triggers/",
            json={
                "type": "cron",
                "config": {"schedule": "*/5 * * * *"},
                "enabled": True,
            },
        )
        assert response.status_code == 422


@pytest.mark.asyncio
@pytest.mark.zentao("TC-S1007", domain="server/api", priority="P2")
async def test_create_trigger_disabled(app, db_engine):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/plugins/triggers/",
            json={
                "type": "cron",
                "config": {"schedule": "*/5 * * * *"},
                "pipeline_file": "deploy.yaml",
                "enabled": False,
            },
        )
        assert response.status_code == 201


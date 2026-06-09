from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from taskpps.main import app as _app


@pytest.fixture
def app():
    return _app


@pytest.mark.asyncio
async def test_register_project(app, setup_project, tmp_project, db_engine):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/projects/",
            json={"workdir": "/opt/project-a", "name": "project-a"},
        )
        assert response.status_code == 201
        data = response.json()
        assert data["workdir"] == "/opt/project-a"
        assert data["name"] == "project-a"
        assert data["active"] is True
        assert "id" in data


@pytest.mark.asyncio
async def test_register_project_duplicate_workdir(app, setup_project, tmp_project, db_engine):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        await client.post(
            "/api/projects/",
            json={"workdir": "/opt/project-dup"},
        )
        response = await client.post(
            "/api/projects/",
            json={"workdir": "/opt/project-dup"},
        )
        assert response.status_code == 409


@pytest.mark.asyncio
async def test_list_projects(app, setup_project, tmp_project, db_engine, clean_db):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        await client.post(
            "/api/projects/",
            json={"workdir": "/opt/p1", "name": "p1"},
        )
        await client.post(
            "/api/projects/",
            json={"workdir": "/opt/p2", "name": "p2"},
        )
        response = await client.get("/api/projects/")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2


@pytest.mark.asyncio
async def test_get_project(app, setup_project, tmp_project, db_engine):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        create_resp = await client.post(
            "/api/projects/",
            json={"workdir": "/opt/project-get", "name": "project-get"},
        )
        project_id = create_resp.json()["id"]

        response = await client.get(f"/api/projects/{project_id}")
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == project_id
        assert data["name"] == "project-get"


@pytest.mark.asyncio
async def test_get_project_not_found(app, setup_project, tmp_project, db_engine):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/projects/nonexistent")
        assert response.status_code == 404


@pytest.mark.asyncio
async def test_unregister_project(app, setup_project, tmp_project, db_engine):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        create_resp = await client.post(
            "/api/projects/",
            json={"workdir": "/opt/project-del"},
        )
        project_id = create_resp.json()["id"]

        response = await client.delete(f"/api/projects/{project_id}")
        assert response.status_code == 200

        get_resp = await client.get(f"/api/projects/{project_id}")
        assert get_resp.status_code == 404


@pytest.mark.asyncio
async def test_unregister_project_not_found(app, setup_project, tmp_project, db_engine):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.delete("/api/projects/nonexistent")
        assert response.status_code == 404

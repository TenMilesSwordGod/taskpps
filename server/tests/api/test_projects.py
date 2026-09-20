from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from taskpps.main import app as _app
from tests.auth._helpers import register_and_auth_headers


@pytest.fixture
def app():
    return _app


@pytest.mark.asyncio
@pytest.mark.zentao("TC-S0935", domain="server/api", priority="P2")
async def test_register_project(app, setup_project, tmp_project, db_engine, tmp_path):
    workdir = tmp_path / "project-a"
    workdir.mkdir()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        headers = await register_and_auth_headers(client)
        response = await client.post(
            "/api/projects/",
            json={"workdir": str(workdir), "name": "project-a"},
            headers=headers,
        )
        assert response.status_code == 201
        data = response.json()
        assert data["workdir"] == str(workdir.resolve())
        assert data["name"] == "project-a"
        assert data["active"] is True
        assert "id" in data


@pytest.mark.asyncio
@pytest.mark.zentao("TC-S0936", domain="server/api", priority="P2")
async def test_register_project_duplicate_workdir(app, setup_project, tmp_project, db_engine, tmp_path):
    workdir = tmp_path / "project-dup"
    workdir.mkdir()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        headers = await register_and_auth_headers(client)
        await client.post(
            "/api/projects/",
            json={"workdir": str(workdir)},
            headers=headers,
        )
        response = await client.post(
            "/api/projects/",
            json={"workdir": str(workdir)},
            headers=headers,
        )
        assert response.status_code == 409


@pytest.mark.asyncio
@pytest.mark.zentao("TC-S0937", domain="server/api", priority="P2")
async def test_list_projects(app, setup_project, tmp_project, db_engine, clean_db, tmp_path):
    p1 = tmp_path / "p1"
    p2 = tmp_path / "p2"
    p1.mkdir()
    p2.mkdir()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        headers = await register_and_auth_headers(client)
        await client.post(
            "/api/projects/",
            json={"workdir": str(p1), "name": "p1"},
            headers=headers,
        )
        await client.post(
            "/api/projects/",
            json={"workdir": str(p2), "name": "p2"},
            headers=headers,
        )
        response = await client.get("/api/projects/")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2


@pytest.mark.asyncio
@pytest.mark.zentao("TC-S0938", domain="server/api", priority="P2")
async def test_get_project(app, setup_project, tmp_project, db_engine, tmp_path):
    workdir = tmp_path / "project-get"
    workdir.mkdir()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        headers = await register_and_auth_headers(client)
        create_resp = await client.post(
            "/api/projects/",
            json={"workdir": str(workdir), "name": "project-get"},
            headers=headers,
        )
        project_id = create_resp.json()["id"]

        response = await client.get(f"/api/projects/{project_id}")
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == project_id
        assert data["name"] == "project-get"


@pytest.mark.asyncio
@pytest.mark.zentao("TC-S0939", domain="server/api", priority="P1")
async def test_get_project_not_found(app, setup_project, tmp_project, db_engine):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/projects/nonexistent")
        assert response.status_code == 404


@pytest.mark.asyncio
@pytest.mark.zentao("TC-S0940", domain="server/api", priority="P2")
async def test_unregister_project(app, setup_project, tmp_project, db_engine, tmp_path):
    workdir = tmp_path / "project-del"
    workdir.mkdir()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        headers = await register_and_auth_headers(client)
        create_resp = await client.post(
            "/api/projects/",
            json={"workdir": str(workdir)},
            headers=headers,
        )
        project_id = create_resp.json()["id"]

        response = await client.delete(f"/api/projects/{project_id}", headers=headers)
        assert response.status_code == 200

        get_resp = await client.get(f"/api/projects/{project_id}")
        assert get_resp.status_code == 404


@pytest.mark.asyncio
@pytest.mark.zentao("TC-S0941", domain="server/api", priority="P1")
async def test_unregister_project_not_found(app, setup_project, tmp_project, db_engine):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        headers = await register_and_auth_headers(client)
        response = await client.delete("/api/projects/nonexistent", headers=headers)
        assert response.status_code == 404


# v3 (2026-09): 网页端注册项目目录 — 服务端严格校验 + 自动创建 pipelines/


@pytest.mark.asyncio
async def test_register_project_requires_auth(app, setup_project, tmp_project, db_engine, tmp_path):
    """未登录调用注册接口 → 401（注册写操作受 JWT 保护）"""
    workdir = tmp_path / "no-auth"
    workdir.mkdir()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/projects/",
            json={"workdir": str(workdir)},
        )
        assert response.status_code == 401


@pytest.mark.asyncio
async def test_register_project_creates_pipelines_dir(app, setup_project, tmp_project, db_engine, tmp_path):
    """注册成功后自动创建 pipelines/ 目录，网页端可立即新建流水线"""
    workdir = tmp_path / "new-project"
    workdir.mkdir()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        headers = await register_and_auth_headers(client)
        response = await client.post(
            "/api/projects/",
            json={"workdir": str(workdir), "name": "new-project"},
            headers=headers,
        )
        assert response.status_code == 201
    assert (workdir / "pipelines").is_dir()


@pytest.mark.asyncio
async def test_register_project_nonexistent_workdir_400(app, setup_project, tmp_project, db_engine, tmp_path):
    """workdir 在服务器上不存在 → 400"""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        headers = await register_and_auth_headers(client)
        response = await client.post(
            "/api/projects/",
            json={"workdir": str(tmp_path / "does-not-exist")},
            headers=headers,
        )
        assert response.status_code == 400


@pytest.mark.asyncio
async def test_register_project_relative_workdir_400(app, setup_project, tmp_project, db_engine):
    """workdir 必须是绝对路径 → 400"""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        headers = await register_and_auth_headers(client)
        response = await client.post(
            "/api/projects/",
            json={"workdir": "relative/path"},
            headers=headers,
        )
        assert response.status_code == 400

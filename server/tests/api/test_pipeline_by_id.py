from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from taskpps.main import app as _app


@pytest.fixture
def app():
    return _app


@pytest.mark.asyncio
@pytest.mark.zentao("TC-S2000", domain="server/api", priority="P1")
async def test_get_pipeline_by_id(app, setup_project, tmp_project, db_engine, clean_db):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        create_resp = await client.post(
            "/api/projects/",
            json={"workdir": str(tmp_project), "name": "my-project"},
        )
        assert create_resp.status_code == 201
        project_id = create_resp.json()["id"]

        list_resp = await client.get("/api/pipelines/", params={"project_id": project_id})
        assert list_resp.status_code == 200
        items = list_resp.json()["items"]
        assert len(items) > 0
        definition_id = items[0]["id"]
        assert definition_id != ""

        detail_resp = await client.get(
            f"/api/pipelines/by-id/{definition_id}",
            params={"project_id": project_id},
        )
        assert detail_resp.status_code == 200
        data = detail_resp.json()
        assert data["name"] in ("deploy", "simple", "fail_test", "continue_test",
                                "cycle", "timeout_test", "invoke_test", "diamond",
                                "multi_sub", "continue_diamond")


@pytest.mark.asyncio
@pytest.mark.zentao("TC-S2001", domain="server/api", priority="P1")
async def test_get_pipeline_by_id_not_found(app, db_engine, clean_db):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(
            "/api/pipelines/by-id/nonexistent",
            params={"project_id": "proj-nonexistent"},
        )
        assert response.status_code == 404


@pytest.mark.asyncio
@pytest.mark.zentao("TC-S2002", domain="server/api", priority="P1")
async def test_get_pipeline_by_id_wrong_project(app, setup_project, tmp_project, db_engine, clean_db):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        create_resp = await client.post(
            "/api/projects/",
            json={"workdir": str(tmp_project), "name": "my-project"},
        )
        assert create_resp.status_code == 201
        project_id = create_resp.json()["id"]

        list_resp = await client.get("/api/pipelines/", params={"project_id": project_id})
        assert list_resp.status_code == 200
        items = list_resp.json()["items"]
        definition_id = items[0]["id"]

        response = await client.get(
            f"/api/pipelines/by-id/{definition_id}",
            params={"project_id": "wrong-project-id"},
        )
        assert response.status_code == 404


@pytest.mark.asyncio
@pytest.mark.zentao("TC-S2003", domain="server/api", priority="P1")
async def test_put_pipeline_by_id_overwrite(app, setup_project, tmp_project, db_engine, clean_db):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        create_resp = await client.post(
            "/api/projects/",
            json={"workdir": str(tmp_project), "name": "my-project"},
        )
        assert create_resp.status_code == 201
        project_id = create_resp.json()["id"]

        list_resp = await client.get("/api/pipelines/", params={"project_id": project_id})
        items = list_resp.json()["items"]
        definition_id = items[0]["id"]

        new_yaml = "name: updated\ntasks:\n  - name: step-new\n    command: echo new\n"
        put_resp = await client.put(
            f"/api/pipelines/by-id/{definition_id}",
            json={"content": new_yaml},
        )
        assert put_resp.status_code == 200
        data = put_resp.json()
        assert data["status"] == "ok"
        assert data["definition_id"] == definition_id

        detail_resp = await client.get(
            f"/api/pipelines/by-id/{definition_id}",
            params={"project_id": project_id},
        )
        assert detail_resp.status_code == 200
        assert detail_resp.json()["name"] == "updated"


@pytest.mark.asyncio
@pytest.mark.zentao("TC-S2004", domain="server/api", priority="P1")
async def test_put_pipeline_by_id_not_found(app, db_engine, clean_db):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.put(
            "/api/pipelines/by-id/nonexistent",
            json={"content": "name: test\n"},
        )
        assert response.status_code == 404


@pytest.mark.asyncio
@pytest.mark.zentao("TC-S2005", domain="server/api", priority="P1")
async def test_put_pipeline_by_id_invalid_yaml(app, setup_project, tmp_project, db_engine, clean_db):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        create_resp = await client.post(
            "/api/projects/",
            json={"workdir": str(tmp_project), "name": "my-project"},
        )
        assert create_resp.status_code == 201
        project_id = create_resp.json()["id"]

        list_resp = await client.get("/api/pipelines/", params={"project_id": project_id})
        items = list_resp.json()["items"]
        definition_id = items[0]["id"]

        response = await client.put(
            f"/api/pipelines/by-id/{definition_id}",
            json={"content": "{invalid: yaml: :"},
        )
        assert response.status_code == 400

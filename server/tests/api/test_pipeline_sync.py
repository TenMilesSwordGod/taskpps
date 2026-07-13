from __future__ import annotations

from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from taskpps.main import app as _app


@pytest.fixture
def app():
    return _app


@pytest.mark.asyncio
async def test_list_pipelines_sync_creates_definitions(app, setup_project, tmp_project, db_engine, clean_db):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        create_resp = await client.post(
            "/api/projects/",
            json={"workdir": str(tmp_project), "name": "my-project"},
        )
        assert create_resp.status_code == 201
        project_id = create_resp.json()["id"]

        response = await client.get("/api/pipelines/", params={"project_id": project_id})
        assert response.status_code == 200
        data = response.json()
        items = data["items"]
        assert len(items) > 0

        for item in items:
            assert "id" in item
            definition_id = item.get("id")
            assert definition_id is not None
            assert len(definition_id) == 12

        from taskpps.db.engine import get_session_factory
        from taskpps.db.repository import PipelineDefinitionRepository

        async with get_session_factory()() as session:
            repo = PipelineDefinitionRepository(session)
            definitions = await repo.list_by_project(project_id)
            assert len(definitions) == len(items)
            for d in definitions:
                assert d.active is True
                assert d.project_id == project_id
                assert d.file_hash != ""


@pytest.mark.asyncio
async def test_list_pipelines_sync_no_duplicate_on_second_call(app, setup_project, tmp_project, db_engine, clean_db):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        create_resp = await client.post(
            "/api/projects/",
            json={"workdir": str(tmp_project), "name": "my-project"},
        )
        assert create_resp.status_code == 201
        project_id = create_resp.json()["id"]

        resp1 = await client.get("/api/pipelines/", params={"project_id": project_id})
        assert resp1.status_code == 200
        items1 = resp1.json()["items"]
        ids1 = {item["id"] for item in items1}

        resp2 = await client.get("/api/pipelines/", params={"project_id": project_id})
        assert resp2.status_code == 200
        items2 = resp2.json()["items"]
        ids2 = {item["id"] for item in items2}

        assert ids1 == ids2


@pytest.mark.asyncio
async def test_list_pipelines_sync_removed_file_deactivated(app, setup_project, tmp_project, db_engine, clean_db):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        create_resp = await client.post(
            "/api/projects/",
            json={"workdir": str(tmp_project), "name": "my-project"},
        )
        assert create_resp.status_code == 201
        project_id = create_resp.json()["id"]

        resp1 = await client.get("/api/pipelines/", params={"project_id": project_id})
        assert resp1.status_code == 200
        items_before = resp1.json()["items"]

        extra_yaml = Path(tmp_project) / "pipelines" / "extra.yaml"
        extra_yaml.write_text("name: extra\ntasks:\n  - name: t1\n    command: echo extra\n")

        resp2 = await client.get("/api/pipelines/", params={"project_id": project_id})
        assert resp2.status_code == 200
        items_with_extra = resp2.json()["items"]
        assert len(items_with_extra) == len(items_before) + 1

        extra_yaml.unlink()

        resp3 = await client.get("/api/pipelines/", params={"project_id": project_id})
        assert resp3.status_code == 200
        items_after = resp3.json()["items"]
        assert len(items_after) == len(items_before)

        from taskpps.db.engine import get_session_factory
        from taskpps.db.repository import PipelineDefinitionRepository

        async with get_session_factory()() as session:
            repo = PipelineDefinitionRepository(session)
            all_defs = await repo.list_by_project(project_id, active_only=False)
            extra_def = next(d for d in all_defs if d.file_path == "extra.yaml")
            assert extra_def.active is False


@pytest.mark.asyncio
async def test_list_pipelines_sync_restored_file_new_uuid(app, setup_project, tmp_project, db_engine, clean_db):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        create_resp = await client.post(
            "/api/projects/",
            json={"workdir": str(tmp_project), "name": "my-project"},
        )
        assert create_resp.status_code == 201
        project_id = create_resp.json()["id"]

        await client.get("/api/pipelines/", params={"project_id": project_id})

        extra_yaml = Path(tmp_project) / "pipelines" / "extra.yaml"
        extra_yaml.write_text("name: extra\ntasks:\n  - name: t1\n    command: echo extra\n")

        resp2 = await client.get("/api/pipelines/", params={"project_id": project_id})
        extra_id_v1 = None
        for item in resp2.json()["items"]:
            if item["file"] == "extra.yaml":
                extra_id_v1 = item["id"]
        assert extra_id_v1 is not None

        extra_yaml.unlink()
        await client.get("/api/pipelines/", params={"project_id": project_id})

        extra_yaml.write_text("name: extra\ntasks:\n  - name: t1\n    command: echo extra\n")
        resp4 = await client.get("/api/pipelines/", params={"project_id": project_id})
        extra_id_v2 = None
        for item in resp4.json()["items"]:
            if item["file"] == "extra.yaml":
                extra_id_v2 = item["id"]
        assert extra_id_v2 is not None
        assert extra_id_v2 != extra_id_v1


@pytest.mark.asyncio
async def test_list_pipelines_sync_same_file_same_hash_same_id(app, setup_project, tmp_project, db_engine, clean_db):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        create_resp = await client.post(
            "/api/projects/",
            json={"workdir": str(tmp_project), "name": "my-project"},
        )
        assert create_resp.status_code == 201
        project_id = create_resp.json()["id"]

        resp1 = await client.get("/api/pipelines/", params={"project_id": project_id})
        ids1 = {item["id"] for item in resp1.json()["items"]}

        resp2 = await client.get("/api/pipelines/", params={"project_id": project_id})
        ids2 = {item["id"] for item in resp2.json()["items"]}

        assert ids1 == ids2


@pytest.mark.asyncio
async def test_list_pipelines_sync_changed_content_different_hash_same_id(app, setup_project, tmp_project, db_engine, clean_db):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        create_resp = await client.post(
            "/api/projects/",
            json={"workdir": str(tmp_project), "name": "my-project"},
        )
        assert create_resp.status_code == 201
        project_id = create_resp.json()["id"]

        resp1 = await client.get("/api/pipelines/", params={"project_id": project_id})
        deploy_items = [i for i in resp1.json()["items"] if i["file"] == "deploy.yaml"]
        deploy_id_v1 = deploy_items[0]["id"]

        deploy_yaml = Path(tmp_project) / "pipelines" / "deploy.yaml"
        deploy_yaml.write_text(
            "name: deploy\n"
            "options:\n"
            "  env:\n"
            "    APP_ENV: production\n"
            "  timeout: 120\n"
            "  on_failure: fail\n"
            "tasks:\n"
            "  - name: step1\n"
            "    command: echo changed\n"
            "  - name: step2\n"
            "    command: echo world\n"
            "    depends_on: [step1]\n"
        )

        resp2 = await client.get("/api/pipelines/", params={"project_id": project_id})
        deploy_items2 = [i for i in resp2.json()["items"] if i["file"] == "deploy.yaml"]
        deploy_id_v2 = deploy_items2[0]["id"]
        assert deploy_id_v2 == deploy_id_v1

        from taskpps.db.engine import get_session_factory
        from taskpps.db.repository import PipelineDefinitionRepository

        async with get_session_factory()() as session:
            repo = PipelineDefinitionRepository(session)
            d = await repo.get(deploy_id_v2)
            assert d is not None
            assert "changed" in d.content

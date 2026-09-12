from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from taskpps.main import app as _app
from tests.auth._helpers import register_and_auth_headers


@pytest.fixture
def app():
    return _app


@pytest.mark.asyncio
@pytest.mark.zentao("TC-S2000", domain="server/api", priority="P1")
async def test_get_pipeline_by_id(app, setup_project, tmp_project, db_engine, clean_db):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        headers = await register_and_auth_headers(client)
        create_resp = await client.post(
            "/api/projects/",
            json={"workdir": str(tmp_project), "name": "my-project"},
            headers=headers,
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
@pytest.mark.zentao("TC-S2006", domain="server/api", priority="P1")
async def test_get_pipeline_by_id_includes_raw_content(app, setup_project, tmp_project, db_engine, clean_db):
    """by-id 必须返回文件原文 raw_content。

    为什么需要（v3 2026-09）：Web「YAML 编辑器」此前只能用已解析模型反序列化，
    Pydantic schema 未声明的字段（如用户实测的裸 `task:` 列表）会被静默丢弃，
    导致编辑器内容 ≠ 真实文件；前端改为优先展示 raw_content 后需要后端返回该字段。
    """
    pipelines_dir = tmp_project / "pipelines"
    custom_file = pipelines_dir / "raw_fidelity.yaml"
    raw_text = (
        "name: raw-fidelity\n"
        "pipelines:\n"
        "  - name: test\n"
        "    tasks:\n"
        "      - name: hello\n"
        "        task:\n"
        "          - run: ls\n"
        "        retry: 0\n"
    )
    custom_file.write_text(raw_text, encoding="utf-8")
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            headers = await register_and_auth_headers(client)
            create_resp = await client.post(
                "/api/projects/",
                json={"workdir": str(tmp_project), "name": "my-project"},
                headers=headers,
            )
            assert create_resp.status_code == 201
            project_id = create_resp.json()["id"]

            list_resp = await client.get("/api/pipelines/", params={"project_id": project_id})
            assert list_resp.status_code == 200
            item = next(i for i in list_resp.json()["items"] if i["file"] == "raw_fidelity.yaml")

            detail_resp = await client.get(
                f"/api/pipelines/by-id/{item['id']}",
                params={"project_id": project_id},
            )
            assert detail_resp.status_code == 200
            data = detail_resp.json()
            # 原文逐字节一致：未知字段不能在传输环节被模型过滤
            assert data["raw_content"] == raw_text
    finally:
        custom_file.unlink(missing_ok=True)


@pytest.mark.asyncio
@pytest.mark.zentao("TC-S2002", domain="server/api", priority="P1")
async def test_get_pipeline_by_id_wrong_project(app, setup_project, tmp_project, db_engine, clean_db):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        headers = await register_and_auth_headers(client)
        create_resp = await client.post(
            "/api/projects/",
            json={"workdir": str(tmp_project), "name": "my-project"},
            headers=headers,
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
        headers = await register_and_auth_headers(client)
        create_resp = await client.post(
            "/api/projects/",
            json={"workdir": str(tmp_project), "name": "my-project"},
            headers=headers,
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
            headers=headers,
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
        headers = await register_and_auth_headers(client)
        response = await client.put(
            "/api/pipelines/by-id/nonexistent",
            json={"content": "name: test\n"},
            headers=headers,
        )
        assert response.status_code == 404


@pytest.mark.asyncio
@pytest.mark.zentao("TC-S2005", domain="server/api", priority="P1")
async def test_put_pipeline_by_id_invalid_yaml(app, setup_project, tmp_project, db_engine, clean_db):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        headers = await register_and_auth_headers(client)
        create_resp = await client.post(
            "/api/projects/",
            json={"workdir": str(tmp_project), "name": "my-project"},
            headers=headers,
        )
        assert create_resp.status_code == 201
        project_id = create_resp.json()["id"]

        list_resp = await client.get("/api/pipelines/", params={"project_id": project_id})
        items = list_resp.json()["items"]
        definition_id = items[0]["id"]

        response = await client.put(
            f"/api/pipelines/by-id/{definition_id}",
            json={"content": "{invalid: yaml: :"},
            headers=headers,
        )
        assert response.status_code == 400

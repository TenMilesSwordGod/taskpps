"""v3 (2026-09): 网页端流水线/文件夹 CRUD API 测试。

覆盖 POST/PATCH/DELETE /api/pipelines/by-file 与 /folders，以及列表接口的
folders 字段（空文件夹展示）。所有写操作走 JWT 认证（#204 中间件）。
"""

from __future__ import annotations

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from taskpps.main import app as _app
from tests.auth._helpers import register_and_auth_headers


@pytest_asyncio.fixture
async def crud_env(tmp_path, db_engine):
    """独立临时项目 + 已认证 client，避免污染 session 级 tmp_project。"""
    workdir = tmp_path / "crud-project"
    (workdir / "pipelines").mkdir(parents=True)
    transport = ASGITransport(app=_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        headers = await register_and_auth_headers(client)
        resp = await client.post(
            "/api/projects/",
            json={"workdir": str(workdir), "name": "crud"},
            headers=headers,
        )
        assert resp.status_code == 201
        yield client, resp.json()["id"], workdir, headers


VALID_YAML = "name: demo\ntasks:\n  - name: hello\n    command: echo hi\n"


# ── 新建流水线 ──────────────────────────────────────────────

@pytest.mark.asyncio
async def test_create_pipeline_writes_file_and_definition(crud_env):
    client, pid, workdir, headers = crud_env
    resp = await client.post(
        f"/api/pipelines/by-file/{pid}",
        json={"file": "demo.yaml", "content": VALID_YAML},
        headers=headers,
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["file"] == "demo.yaml"
    assert data["definition_id"]

    assert (workdir / "pipelines" / "demo.yaml").read_text() == VALID_YAML

    list_resp = await client.get("/api/pipelines/")
    items = list_resp.json()["items"]
    demo = next(i for i in items if i.get("file") == "demo.yaml")
    assert demo["id"] == data["definition_id"]
    assert demo["valid"] is True


@pytest.mark.asyncio
async def test_create_pipeline_conflict_409(crud_env):
    client, pid, _workdir, headers = crud_env
    await client.post(
        f"/api/pipelines/by-file/{pid}",
        json={"file": "demo.yaml", "content": VALID_YAML},
        headers=headers,
    )
    resp = await client.post(
        f"/api/pipelines/by-file/{pid}",
        json={"file": "demo.yaml", "content": VALID_YAML},
        headers=headers,
    )
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_create_pipeline_requires_auth(crud_env):
    client, pid, _workdir, _headers = crud_env
    resp = await client.post(
        f"/api/pipelines/by-file/{pid}",
        json={"file": "demo.yaml", "content": VALID_YAML},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_create_pipeline_rejects_path_traversal(crud_env):
    client, pid, workdir, headers = crud_env
    resp = await client.post(
        f"/api/pipelines/by-file/{pid}",
        json={"file": "../evil.yaml", "content": VALID_YAML},
        headers=headers,
    )
    assert resp.status_code == 400
    assert not (workdir / "evil.yaml").exists()


@pytest.mark.asyncio
async def test_create_pipeline_rejects_non_yaml(crud_env):
    client, pid, _workdir, headers = crud_env
    resp = await client.post(
        f"/api/pipelines/by-file/{pid}",
        json={"file": "demo.txt", "content": VALID_YAML},
        headers=headers,
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_create_pipeline_invalid_yaml_syntax_400(crud_env):
    client, pid, _workdir, headers = crud_env
    resp = await client.post(
        f"/api/pipelines/by-file/{pid}",
        json={"file": "bad.yaml", "content": "name: bad\n  bad indent: yes\n"},
        headers=headers,
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_create_pipeline_invalid_structure_saved_without_definition(crud_env):
    """YAML 语法合法但 schema 非法：仍写盘，definition_id 为 null，列表 valid=false"""
    client, pid, workdir, headers = crud_env
    resp = await client.post(
        f"/api/pipelines/by-file/{pid}",
        json={"file": "incomplete.yaml", "content": "foo: bar\n"},
        headers=headers,
    )
    assert resp.status_code == 201
    assert resp.json()["definition_id"] is None
    assert (workdir / "pipelines" / "incomplete.yaml").exists()

    list_resp = await client.get("/api/pipelines/")
    items = list_resp.json()["items"]
    incomplete = next(i for i in items if i.get("file") == "incomplete.yaml")
    assert incomplete["valid"] is False


# ── 新建文件夹 ──────────────────────────────────────────────

@pytest.mark.asyncio
async def test_create_folder_and_list_returns_empty_folder(crud_env):
    client, pid, _workdir, headers = crud_env
    resp = await client.post(
        f"/api/pipelines/folders/{pid}",
        json={"folder": "debug/prod"},
        headers=headers,
    )
    assert resp.status_code == 201
    assert resp.json()["folder"] == "debug/prod"

    list_resp = await client.get("/api/pipelines/")
    folders = [(f["project_id"], f["folder"]) for f in list_resp.json()["folders"]]
    assert (pid, "debug") in folders
    assert (pid, "debug/prod") in folders


@pytest.mark.asyncio
async def test_create_folder_conflict_409(crud_env):
    client, pid, _workdir, headers = crud_env
    await client.post(f"/api/pipelines/folders/{pid}", json={"folder": "debug"}, headers=headers)
    resp = await client.post(f"/api/pipelines/folders/{pid}", json={"folder": "debug"}, headers=headers)
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_create_folder_rejects_traversal(crud_env):
    client, pid, workdir, headers = crud_env
    resp = await client.post(
        f"/api/pipelines/folders/{pid}",
        json={"folder": "../outside"},
        headers=headers,
    )
    assert resp.status_code == 400
    assert not (workdir / "outside").exists()


# ── 重命名流水线 ────────────────────────────────────────────

@pytest.mark.asyncio
async def test_rename_pipeline_preserves_definition_id(crud_env):
    client, pid, workdir, headers = crud_env
    create_resp = await client.post(
        f"/api/pipelines/by-file/{pid}",
        json={"file": "demo.yaml", "content": VALID_YAML},
        headers=headers,
    )
    definition_id = create_resp.json()["definition_id"]

    resp = await client.patch(
        f"/api/pipelines/by-file/{pid}",
        json={"file": "demo.yaml", "new_file": "renamed/demo.yaml"},
        headers=headers,
    )
    assert resp.status_code == 200
    assert resp.json()["file"] == "renamed/demo.yaml"

    assert not (workdir / "pipelines" / "demo.yaml").exists()
    assert (workdir / "pipelines" / "renamed" / "demo.yaml").exists()

    list_resp = await client.get("/api/pipelines/")
    items = list_resp.json()["items"]
    renamed = next(i for i in items if i.get("file") == "renamed/demo.yaml")
    assert renamed["id"] == definition_id


@pytest.mark.asyncio
async def test_rename_pipeline_conflict_409(crud_env):
    client, pid, _workdir, headers = crud_env
    for name in ("a.yaml", "b.yaml"):
        await client.post(
            f"/api/pipelines/by-file/{pid}",
            json={"file": name, "content": VALID_YAML},
            headers=headers,
        )
    resp = await client.patch(
        f"/api/pipelines/by-file/{pid}",
        json={"file": "a.yaml", "new_file": "b.yaml"},
        headers=headers,
    )
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_rename_pipeline_not_found(crud_env):
    client, pid, _workdir, headers = crud_env
    resp = await client.patch(
        f"/api/pipelines/by-file/{pid}",
        json={"file": "missing.yaml", "new_file": "other.yaml"},
        headers=headers,
    )
    assert resp.status_code == 404


# ── 重命名文件夹 ────────────────────────────────────────────

@pytest.mark.asyncio
async def test_rename_folder_updates_definition_paths(crud_env):
    client, pid, workdir, headers = crud_env
    create_resp = await client.post(
        f"/api/pipelines/by-file/{pid}",
        json={"file": "a/x.yaml", "content": VALID_YAML},
        headers=headers,
    )
    definition_id = create_resp.json()["definition_id"]

    resp = await client.patch(
        f"/api/pipelines/folders/{pid}",
        json={"folder": "a", "new_folder": "b"},
        headers=headers,
    )
    assert resp.status_code == 200
    assert resp.json()["folder"] == "b"
    assert (workdir / "pipelines" / "b" / "x.yaml").exists()
    assert not (workdir / "pipelines" / "a").exists()

    list_resp = await client.get("/api/pipelines/")
    items = list_resp.json()["items"]
    moved = next(i for i in items if i.get("file") == "b/x.yaml")
    assert moved["id"] == definition_id


@pytest.mark.asyncio
async def test_rename_folder_into_itself_400(crud_env):
    client, pid, _workdir, headers = crud_env
    await client.post(f"/api/pipelines/folders/{pid}", json={"folder": "a/b"}, headers=headers)
    resp = await client.patch(
        f"/api/pipelines/folders/{pid}",
        json={"folder": "a", "new_folder": "a/b/c"},
        headers=headers,
    )
    assert resp.status_code == 400


# ── 删除流水线 / 文件夹 ─────────────────────────────────────

@pytest.mark.asyncio
async def test_delete_pipeline_removes_file_and_hides_from_list(crud_env):
    client, pid, workdir, headers = crud_env
    await client.post(
        f"/api/pipelines/by-file/{pid}",
        json={"file": "demo.yaml", "content": VALID_YAML},
        headers=headers,
    )
    resp = await client.delete(
        f"/api/pipelines/by-file/{pid}",
        params={"file": "demo.yaml"},
        headers=headers,
    )
    assert resp.status_code == 200
    assert not (workdir / "pipelines" / "demo.yaml").exists()

    list_resp = await client.get("/api/pipelines/")
    files = [i.get("file") for i in list_resp.json()["items"]]
    assert "demo.yaml" not in files


@pytest.mark.asyncio
async def test_delete_folder_requires_recursive_when_non_empty(crud_env):
    client, pid, workdir, headers = crud_env
    await client.post(
        f"/api/pipelines/by-file/{pid}",
        json={"file": "debug/x.yaml", "content": VALID_YAML},
        headers=headers,
    )
    resp = await client.delete(
        f"/api/pipelines/folders/{pid}",
        params={"folder": "debug"},
        headers=headers,
    )
    assert resp.status_code == 409

    resp = await client.delete(
        f"/api/pipelines/folders/{pid}",
        params={"folder": "debug", "recursive": "true"},
        headers=headers,
    )
    assert resp.status_code == 200
    assert not (workdir / "pipelines" / "debug").exists()

    list_resp = await client.get("/api/pipelines/")
    files = [i.get("file") for i in list_resp.json()["items"]]
    assert "debug/x.yaml" not in files


@pytest.mark.asyncio
async def test_delete_empty_folder_ok(crud_env):
    client, pid, _workdir, headers = crud_env
    await client.post(f"/api/pipelines/folders/{pid}", json={"folder": "empty"}, headers=headers)
    resp = await client.delete(
        f"/api/pipelines/folders/{pid}",
        params={"folder": "empty"},
        headers=headers,
    )
    assert resp.status_code == 200

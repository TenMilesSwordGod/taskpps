from __future__ import annotations

from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from taskpps.main import app as _app


@pytest.fixture
def app():
    return _app


@pytest.mark.asyncio
async def test_sync_handles_corrupted_yaml_crashes_bug(app, setup_project, tmp_project, db_engine, clean_db):
    """已知 bug: _sync_pipeline_definitions 没有对 yaml.safe_load 做异常捕获，
    损坏的 yaml 文件会导致列表 API 返回 500 错误。
    期望行为: 损坏文件被跳过，其他正常文件仍然同步成功并返回 200。
    """
    corrupted_path = None
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            create_resp = await client.post(
                "/api/projects/",
                json={"workdir": str(tmp_project), "name": "my-project"},
            )
            assert create_resp.status_code == 201
            project_id = create_resp.json()["id"]

            corrupted_path = Path(tmp_project) / "pipelines" / "corrupted.yaml"
            corrupted_path.write_text("name: corrupted\n  - bad indent: [\n")

            response = await client.get("/api/pipelines/", params={"project_id": project_id})
            assert response.status_code == 200
            items = response.json()["items"]
            corrupted_items = [i for i in items if i["file"] == "corrupted.yaml"]
            assert len(corrupted_items) == 0
    finally:
        if corrupted_path and corrupted_path.exists():
            corrupted_path.unlink(missing_ok=True)


@pytest.mark.asyncio
async def test_sync_handles_empty_yaml_file(app, setup_project, tmp_project, db_engine, clean_db):
    empty_path = None
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            create_resp = await client.post(
                "/api/projects/",
                json={"workdir": str(tmp_project), "name": "my-project"},
            )
            assert create_resp.status_code == 201
            project_id = create_resp.json()["id"]

            empty_path = Path(tmp_project) / "pipelines" / "empty.yaml"
            empty_path.write_text("")

            response = await client.get("/api/pipelines/", params={"project_id": project_id})
            assert response.status_code == 200
            data = response.json()
            items = data["items"]
            empty_items = [i for i in items if i["file"] == "empty.yaml"]
            assert len(empty_items) == 0
    finally:
        if empty_path and empty_path.exists():
            empty_path.unlink()


@pytest.mark.asyncio
async def test_sync_skips_yaml_with_only_comments(app, setup_project, tmp_project, db_engine, clean_db):
    comment_path = None
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            create_resp = await client.post(
                "/api/projects/",
                json={"workdir": str(tmp_project), "name": "my-project"},
            )
            assert create_resp.status_code == 201
            project_id = create_resp.json()["id"]

            comment_path = Path(tmp_project) / "pipelines" / "comments.yaml"
            comment_path.write_text("# just a comment\n# nothing else\n")

            response = await client.get("/api/pipelines/", params={"project_id": project_id})
            assert response.status_code == 200
            data = response.json()
            items = data["items"]
            comment_items = [i for i in items if i["file"] == "comments.yaml"]
            assert len(comment_items) == 0
    finally:
        if comment_path and comment_path.exists():
            comment_path.unlink()


@pytest.mark.asyncio
async def test_list_pipelines_with_nonexistent_project(app, setup_project, tmp_project, db_engine, clean_db):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/pipelines/", params={"project_id": "nonexistent-id"})
        assert response.status_code == 404


@pytest.mark.asyncio
async def test_put_save_with_invalid_yaml(app, setup_project, tmp_project, db_engine, clean_db):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        create_resp = await client.post(
            "/api/projects/",
            json={"workdir": str(tmp_project), "name": "my-project"},
        )
        assert create_resp.status_code == 201
        project_id = create_resp.json()["id"]

        response = await client.put(
            "/api/pipelines/deploy.yaml",
            json={"content": "broken: [\n"},
            params={"project_id": project_id},
        )
        assert response.status_code == 400


@pytest.mark.asyncio
async def test_sync_handles_yaml_without_name_field_crashes_bug(app, setup_project, tmp_project, db_engine, clean_db):
    """已知 bug: name 不是 YAML 必填字段（options/tasks 才是关键），
    但 PipelineYAML 模型要求 name 必填，sync 函数无异常捕获导致 500。
    期望: name 缺省时使用空字符串，文件仍同步成功。
    """
    noname_path = None
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            create_resp = await client.post(
                "/api/projects/",
                json={"workdir": str(tmp_project), "name": "my-project"},
            )
            assert create_resp.status_code == 201
            project_id = create_resp.json()["id"]

            noname_path = Path(tmp_project) / "pipelines" / "noname.yaml"
            noname_path.write_text("options: {}\ntasks:\n  - name: t1\n    command: echo hi\n")

            response = await client.get("/api/pipelines/", params={"project_id": project_id})
            assert response.status_code == 200
            items = response.json()["items"]
            noname_items = [i for i in items if i["file"] == "noname.yaml"]
            assert len(noname_items) == 0
    finally:
        if noname_path and noname_path.exists():
            noname_path.unlink(missing_ok=True)


@pytest.mark.asyncio
async def test_sync_handles_nested_yaml_in_subdir(app, setup_project, tmp_project, db_engine, clean_db):
    nested_yaml = None
    sub_dir = None
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            create_resp = await client.post(
                "/api/projects/",
                json={"workdir": str(tmp_project), "name": "my-project"},
            )
            assert create_resp.status_code == 201
            project_id = create_resp.json()["id"]

            sub_dir = Path(tmp_project) / "pipelines" / "sub"
            sub_dir.mkdir(exist_ok=True)
            nested_yaml = sub_dir / "nested.yaml"
            nested_yaml.write_text("name: nested\noptions: {}\ntasks:\n  - name: t1\n    command: echo nested\n")

            response = await client.get("/api/pipelines/", params={"project_id": project_id})
            assert response.status_code == 200
            data = response.json()
            items = data["items"]
            nested_items = [i for i in items if i["file"] == "sub/nested.yaml"]
            assert len(nested_items) == 1
            assert nested_items[0]["name"] == "nested"
    finally:
        if nested_yaml and nested_yaml.exists():
            nested_yaml.unlink()
        if sub_dir and sub_dir.exists():
            try:
                sub_dir.rmdir()
            except OSError:
                pass

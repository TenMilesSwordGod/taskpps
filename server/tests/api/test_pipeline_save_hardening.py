from __future__ import annotations

import shutil

import pytest
from httpx import ASGITransport, AsyncClient

from taskpps.main import app as _app


@pytest.fixture
def app():
    return _app


@pytest.fixture
def auth_headers(tmp_project):
    """JWT 中间件对 POST/PUT 强制鉴权，测试里签发一个合法 token。"""
    import taskpps.config as cfg
    from taskpps.auth.security import create_access_token, ensure_jwt_secret

    cfg.set_project_root(tmp_project)
    cfg._settings = None
    cfg.load_settings(str(tmp_project / "taskpps.yaml"))
    ensure_jwt_secret()
    return {"Authorization": f"Bearer {create_access_token('save-hardening', 'user')}"}


async def _register_project(client: AsyncClient, tmp_project, auth_headers) -> str:
    resp = await client.post(
        "/api/projects/",
        json={"workdir": str(tmp_project), "name": "save-hardening"},
        headers=auth_headers,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


async def _definition_id_for(client: AsyncClient, file_name: str) -> str:
    resp = await client.get("/api/pipelines/")
    assert resp.status_code == 200, resp.text
    found = [i for i in resp.json()["items"] if i.get("file") == file_name]
    assert found and found[0].get("id"), f"{file_name} 未同步为 definition: {resp.json()}"
    return found[0]["id"]


# --- P1：by-id 保存「先写盘后校验」导致 500 且磁盘已被改写 ---


@pytest.mark.asyncio
async def test_put_pipeline_by_id_valid_save_syncs_disk_and_db(
    app, tmp_project, db_engine, clean_db, auth_headers
):
    """by-id 保存合法 YAML：落盘 + 同步 DB（校验前移后的回归保护）。"""
    target = tmp_project / "pipelines" / "hardening3.yaml"
    target.write_text(
        "name: hardening3\ntasks:\n  - name: s1\n    command: echo ok\n", encoding="utf-8"
    )

    transport = ASGITransport(app=app, raise_app_exceptions=False)
    try:
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            project_id = await _register_project(client, tmp_project, auth_headers)
            definition_id = await _definition_id_for(client, "hardening3.yaml")

            new_yaml = "name: renamed-by-hardening\ntasks:\n  - name: s1\n    command: echo new\n"
            resp = await client.put(
                f"/api/pipelines/by-id/{definition_id}",
                json={"content": new_yaml},
                headers=auth_headers,
            )
            assert resp.status_code == 200, resp.text
            assert target.read_text(encoding="utf-8") == new_yaml

            detail = await client.get(
                f"/api/pipelines/by-id/{definition_id}",
                params={"project_id": project_id},
            )
            assert detail.status_code == 200
            assert detail.json()["name"] == "renamed-by-hardening"
    finally:
        target.unlink(missing_ok=True)


@pytest.mark.asyncio
async def test_put_pipeline_by_id_structurally_invalid_does_not_write_disk(
    app, tmp_project, db_engine, clean_db, auth_headers
):
    """[P1] by-id 保存结构非法 YAML：必须 4xx 拒绝且磁盘保持原样。

    v7 修复前：先 write_text 落盘，再 loader.parse_dict；pydantic ValidationError
    未捕获 → 500。用户看到「保存失败」，但磁盘上旧流水线已被破坏，DB 未同步，
    磁盘与 DB 分叉。
    """
    target = tmp_project / "pipelines" / "hardening.yaml"
    original = "name: hardening\ntasks:\n  - name: s1\n    command: echo ok\n"
    target.write_text(original, encoding="utf-8")

    transport = ASGITransport(app=app, raise_app_exceptions=False)
    try:
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            await _register_project(client, tmp_project, auth_headers)
            definition_id = await _definition_id_for(client, "hardening.yaml")

            # 语法合法但结构非法（缺少必填 name）
            bad_yaml = "tasks:\n  - name: step1\n    command: echo ok\n"
            resp = await client.put(
                f"/api/pipelines/by-id/{definition_id}",
                json={"content": bad_yaml},
                headers=auth_headers,
            )
            disk_changed = target.read_text(encoding="utf-8") != original

        assert resp.status_code == 400 and not disk_changed, (
            f"结构非法应被 4xx 拒绝且不改写磁盘，实际 status={resp.status_code}, "
            f"disk_changed={disk_changed}: {resp.text}"
        )
    finally:
        target.unlink(missing_ok=True)


@pytest.mark.asyncio
async def test_put_pipeline_by_id_comment_only_content_rejected(
    app, tmp_project, db_engine, clean_db, auth_headers
):
    """[P2] by-id 保存只有注释（safe_load 为 None）的内容：不得 200 且清空磁盘。

    v7 修复前：safe_load → None 时跳过 DB 同步，但文件已写成空内容并返回 200
    「已保存」。GET by-id 仍返回旧定义，磁盘与 DB 分叉。
    """
    target = tmp_project / "pipelines" / "hardening2.yaml"
    original = "name: hardening2\ntasks:\n  - name: s1\n    command: echo ok\n"
    target.write_text(original, encoding="utf-8")

    transport = ASGITransport(app=app, raise_app_exceptions=False)
    try:
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            await _register_project(client, tmp_project, auth_headers)
            definition_id = await _definition_id_for(client, "hardening2.yaml")

            resp = await client.put(
                f"/api/pipelines/by-id/{definition_id}",
                json={"content": "# 只有注释，没有流水线数据\n"},
                headers=auth_headers,
            )
            disk_changed = target.read_text(encoding="utf-8") != original

        assert resp.status_code == 400 and not disk_changed, (
            f"空流水线应被拒绝且不改写磁盘，实际 status={resp.status_code}, "
            f"disk_changed={disk_changed}"
        )
    finally:
        target.unlink(missing_ok=True)


# --- P1：by-file 路径穿越（前缀匹配绕过）---


@pytest.mark.asyncio
async def test_put_pipeline_by_file_rejects_sibling_prefix_traversal(
    app, tmp_project, db_engine, clean_db, auth_headers
):
    """[P1] 越界写：file=../pipelines_evil/x.yaml 绕过 startswith 前缀校验。

    `(pipelines_dir / "../pipelines_evil/x.yaml").resolve()` 的结果字符串仍以
    `.../project/pipelines` 开头，因此旧的 startswith 校验放行，文件被写到
    pipelines 目录之外。
    """
    evil_dir = tmp_project / "pipelines_evil"
    target = evil_dir / "evil.yaml"

    transport = ASGITransport(app=app, raise_app_exceptions=False)
    try:
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            project_id = await _register_project(client, tmp_project, auth_headers)

            resp = await client.put(
                f"/api/pipelines/by-file/{project_id}",
                json={"file": "../pipelines_evil/evil.yaml", "content": "name: evil\n"},
                headers=auth_headers,
            )
            wrote_outside = target.exists()

        assert resp.status_code == 400 and not wrote_outside, (
            f"越界路径必须被拒绝且不得越界写文件，实际 status={resp.status_code}, "
            f"wrote_outside={wrote_outside}"
        )
    finally:
        shutil.rmtree(evil_dir, ignore_errors=True)


@pytest.mark.asyncio
async def test_get_pipeline_by_file_rejects_sibling_prefix_traversal(
    app, tmp_project, db_engine, clean_db, auth_headers
):
    """[P2] 越界读：file=../pipelines_secret/x.yaml 可读取 pipelines 目录外文件。"""
    secret_dir = tmp_project / "pipelines_secret"
    secret_dir.mkdir(exist_ok=True)
    secret = secret_dir / "secret.yaml"
    secret.write_text("name: leaked\npassword: topsecret\n", encoding="utf-8")

    transport = ASGITransport(app=app, raise_app_exceptions=False)
    try:
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            project_id = await _register_project(client, tmp_project, auth_headers)

            resp = await client.get(
                f"/api/pipelines/by-file/{project_id}",
                params={"file": "../pipelines_secret/secret.yaml"},
            )

        if resp.status_code == 200:
            pytest.fail(f"越界读取被放行，泄漏内容: {resp.json()}")
        assert resp.status_code in (400, 404), f"越界路径必须被拒绝，实际 {resp.status_code}"
    finally:
        shutil.rmtree(secret_dir, ignore_errors=True)


# --- by-file 保存语义（记录既有设计，防止回归）---


@pytest.mark.asyncio
async def test_save_pipeline_by_file_invalid_structure_only_writes_disk(
    app, tmp_project, db_engine, clean_db, auth_headers
):
    """by-file 保存结构非法 YAML：允许落盘供用户继续修改，但不同步 DB。

    这是 issue #195 的既有设计（非法 pipeline 无 definition_id，需要能保存草稿）。
    """
    target = tmp_project / "pipelines" / "draft.yaml"
    target.write_text("", encoding="utf-8")

    transport = ASGITransport(app=app, raise_app_exceptions=False)
    try:
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            project_id = await _register_project(client, tmp_project, auth_headers)

            bad_yaml = "tasks:\n  - name: step1\n    command: echo ok\n"
            resp = await client.put(
                f"/api/pipelines/by-file/{project_id}",
                json={"file": "draft.yaml", "content": bad_yaml},
                headers=auth_headers,
            )
            assert resp.status_code == 200
            assert target.read_text(encoding="utf-8") == bad_yaml
            assert resp.json().get("definition_id") is None, "结构非法不应同步出 definition_id"
    finally:
        target.unlink(missing_ok=True)


@pytest.mark.asyncio
async def test_save_pipeline_by_file_valid_structure_syncs_db(
    app, tmp_project, db_engine, clean_db, auth_headers
):
    """by-file 保存合法 YAML：落盘 + 同步 DB，列表可见新名称。"""
    target = tmp_project / "pipelines" / "synced.yaml"
    target.write_text("", encoding="utf-8")

    transport = ASGITransport(app=app, raise_app_exceptions=False)
    try:
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            project_id = await _register_project(client, tmp_project, auth_headers)

            valid_yaml = "name: synced-name\ntasks:\n  - name: step1\n    command: echo ok\n"
            resp = await client.put(
                f"/api/pipelines/by-file/{project_id}",
                json={"file": "synced.yaml", "content": valid_yaml},
                headers=auth_headers,
            )
            assert resp.status_code == 200
            assert resp.json().get("definition_id"), "合法 YAML 应同步出 definition_id"
            assert target.read_text(encoding="utf-8") == valid_yaml

            list_resp = await client.get("/api/pipelines/")
            item = [i for i in list_resp.json()["items"] if i.get("file") == "synced.yaml"]
            assert item and item[0]["name"] == "synced-name"
            assert item[0]["valid"] is True
    finally:
        target.unlink(missing_ok=True)

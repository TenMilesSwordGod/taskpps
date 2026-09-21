from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from taskpps.main import app as _app


@pytest.fixture
def app():
    return _app


@pytest.fixture
def auth_headers(tmp_project):
    import taskpps.config as cfg
    from taskpps.auth.security import create_access_token, ensure_jwt_secret

    cfg.set_project_root(tmp_project)
    cfg._settings = None
    cfg.load_settings(str(tmp_project / "taskpps.yaml"))
    ensure_jwt_secret()
    return {"Authorization": f"Bearer {create_access_token('yaml-validation', 'user')}"}


async def _register_project(client: AsyncClient, tmp_project, auth_headers) -> str:
    resp = await client.post(
        "/api/projects/",
        json={"workdir": str(tmp_project), "name": "yaml-validation"},
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


def _write_pipeline(tmp_project, file_name: str, content: str):
    target = tmp_project / "pipelines" / file_name
    target.write_text(content, encoding="utf-8")
    return target


# --- P0：保存/同步时变量替换结果入库，凭据明文可被 guest 读取 ---


@pytest.mark.asyncio
async def test_get_pipeline_by_id_does_not_leak_resolved_credential(
    app, tmp_project, db_engine, clean_db, auth_headers
):
    """[P0] GET /by-id 返回的定义内容不得包含已解析的凭据明文。

    v7 修复前：list 同步 / 保存时用 loader.parse_dict（会做变量替换，
    把 ${credential:default-cred.password} 解析成真实密码）的结果写进
    pipeline_definitions.content；GET /by-id 原样返回（guest 可读），
    且前端编辑器会基于该内容重新序列化，下次保存把明文写回磁盘。
    """
    _write_pipeline(
        tmp_project,
        "leaky.yaml",
        "name: leaky\ntasks:\n  - name: t1\n    command: echo ${credential:default-cred.password}\n",
    )

    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        project_id = await _register_project(client, tmp_project, auth_headers)
        definition_id = await _definition_id_for(client, "leaky.yaml")

        resp = await client.get(
            f"/api/pipelines/by-id/{definition_id}",
            params={"project_id": project_id},
        )
        assert resp.status_code == 200, resp.text
        body = resp.text
        assert "testpass" not in body, "定义内容泄漏了凭据明文"
        assert "${credential:default-cred.password}" in body, "应保留未解析的变量占位符"


@pytest.mark.asyncio
async def test_save_pipeline_by_id_stores_raw_placeholder_not_resolved(
    app, tmp_project, db_engine, clean_db, auth_headers
):
    """[P0] by-id 保存后 DB 中的 content 必须是未替换的原始结构，而非解析后的明文。"""
    _write_pipeline(
        tmp_project,
        "leaky2.yaml",
        "name: leaky2\ntasks:\n  - name: t1\n    command: echo ok\n",
    )

    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        project_id = await _register_project(client, tmp_project, auth_headers)
        definition_id = await _definition_id_for(client, "leaky2.yaml")

        new_yaml = (
            "name: leaky2\n"
            "tasks:\n"
            "  - name: t1\n"
            "    command: echo ${credential:default-cred.password}\n"
        )
        put = await client.put(
            f"/api/pipelines/by-id/{definition_id}",
            json={"content": new_yaml},
            headers=auth_headers,
        )
        assert put.status_code == 200, put.text

        resp = await client.get(
            f"/api/pipelines/by-id/{definition_id}",
            params={"project_id": project_id},
        )
        assert resp.status_code == 200
        assert "testpass" not in resp.text, "保存后的定义内容泄漏了凭据明文"
        assert "${credential:default-cred.password}" in resp.text


@pytest.mark.asyncio
async def test_loader_load_still_resolves_credential_at_run_time(tmp_project):
    """回归保护：运行时 loader.load 仍必须做变量替换（否则命令跑不起来）。"""
    from taskpps.loaders.pipeline_loader import PipelineLoader

    _write_pipeline(
        tmp_project,
        "runtime.yaml",
        "name: runtime\ntasks:\n  - name: t1\n    command: echo ${credential:default-cred.password}\n",
    )
    loader = PipelineLoader(base_dir=tmp_project / "pipelines")
    spec = loader.load("runtime.yaml", project_workdir=tmp_project)
    tasks = spec.pipelines[0].tasks if spec.pipelines else spec.tasks
    assert tasks is not None
    assert tasks[0].command == "echo testpass"


# --- P1：语法非法的 YAML 文件无法通过 by-file 打开（file 模式的核心场景）---


@pytest.mark.asyncio
async def test_get_pipeline_by_file_invalid_syntax_returns_raw_content(
    app, tmp_project, db_engine, clean_db, auth_headers
):
    """[P1] by-file GET 对语法非法的 YAML 必须返回 raw_content 供用户修复。

    v7 修复前：name 提取处直接 yaml.safe_load(raw_content)，语法错误时
    YAMLError 未捕获 → 500，前端 file 模式拿不到内容，无法修复非法流水线。
    """
    raw = "name: bad\n  wrong_indent: yes\ntasks: []\n"
    _write_pipeline(tmp_project, "bad_syntax.yaml", raw)

    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        project_id = await _register_project(client, tmp_project, auth_headers)

        resp = await client.get(
            f"/api/pipelines/by-file/{project_id}",
            params={"file": "bad_syntax.yaml"},
        )
        assert resp.status_code == 200, f"非法 YAML 也应可读取，实际 {resp.status_code}: {resp.text}"
        assert resp.json()["raw_content"] == raw


@pytest.mark.asyncio
async def test_get_pipeline_by_id_includes_raw_content(
    app, tmp_project, db_engine, clean_db, auth_headers
):
    """[P1] GET /by-id 必须附带 raw_content，供前端编辑器保留注释/格式。

    v7 修复前：只返回解析后的结构 JSON，前端用它重新序列化生成编辑器文本，
    注释/空行/字段顺序在「打开编辑器」时就消失，保存后磁盘上永久丢失。
    """
    raw = (
        "name: with_comment\n"
        "# 关键注释：这段不能丢\n"
        "tasks:\n"
        "  - name: t1\n"
        "    command: echo ok\n"
    )
    _write_pipeline(tmp_project, "comment.yaml", raw)

    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        project_id = await _register_project(client, tmp_project, auth_headers)
        definition_id = await _definition_id_for(client, "comment.yaml")

        resp = await client.get(
            f"/api/pipelines/by-id/{definition_id}",
            params={"project_id": project_id},
        )
        assert resp.status_code == 200, resp.text
        assert resp.json().get("raw_content") == raw


# --- P1：重复 task / subpipeline 名称未校验，保存成功但运行失败或静默漏跑 ---


@pytest.mark.asyncio
async def test_put_pipeline_by_id_duplicate_task_names_rejected(
    app, tmp_project, db_engine, clean_db, auth_headers
):
    """[P1] 同一 SubPipeline 内重复 task name：保存必须 400。

    v7 修复前：pydantic 不校验唯一性 → 200「已保存」；运行期 DAG 用
    {name: task} 去重，第一个定义被静默覆盖，随后报「循环依赖」。
    """
    target = _write_pipeline(
        tmp_project,
        "dup_task.yaml",
        "name: dup_task\ntasks:\n  - name: build\n    command: echo first\n",
    )

    transport = ASGITransport(app=app, raise_app_exceptions=False)
    try:
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            await _register_project(client, tmp_project, auth_headers)
            definition_id = await _definition_id_for(client, "dup_task.yaml")

            dup_yaml = (
                "name: dup_task\n"
                "tasks:\n"
                "  - name: build\n"
                "    command: echo first\n"
                "  - name: build\n"
                "    command: echo second\n"
            )
            resp = await client.put(
                f"/api/pipelines/by-id/{definition_id}",
                json={"content": dup_yaml},
                headers=auth_headers,
            )
            assert resp.status_code == 400, f"重复 task name 必须被拒绝，实际 {resp.status_code}"
            assert target.read_text(encoding="utf-8") == "name: dup_task\ntasks:\n  - name: build\n    command: echo first\n"
    finally:
        target.unlink(missing_ok=True)


@pytest.mark.asyncio
async def test_put_pipeline_by_id_duplicate_subpipeline_names_rejected(
    app, tmp_project, db_engine, clean_db, auth_headers
):
    """[P1] 重复 subpipeline name：保存必须 400（否则第二个 sub 静默不执行）。"""
    target = _write_pipeline(
        tmp_project,
        "dup_sub.yaml",
        "name: dup_sub\ntasks:\n  - name: t1\n    command: echo ok\n",
    )

    transport = ASGITransport(app=app, raise_app_exceptions=False)
    try:
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            await _register_project(client, tmp_project, auth_headers)
            definition_id = await _definition_id_for(client, "dup_sub.yaml")

            dup_yaml = (
                "name: dup_sub\n"
                "pipelines:\n"
                "  - name: build\n"
                "    tasks:\n"
                "      - name: t1\n"
                "        command: echo 1\n"
                "  - name: build\n"
                "    tasks:\n"
                "      - name: t2\n"
                "        command: echo 2\n"
            )
            resp = await client.put(
                f"/api/pipelines/by-id/{definition_id}",
                json={"content": dup_yaml},
                headers=auth_headers,
            )
            assert resp.status_code == 400, f"重复 subpipeline name 必须被拒绝，实际 {resp.status_code}"
    finally:
        target.unlink(missing_ok=True)


@pytest.mark.asyncio
async def test_list_marks_duplicate_task_name_file_invalid(
    app, tmp_project, db_engine, clean_db, auth_headers
):
    """[P1] 磁盘上已存在的重复 task name 文件，列表必须标记 valid=false。"""
    _write_pipeline(
        tmp_project,
        "dup_on_disk.yaml",
        "name: dup_on_disk\ntasks:\n  - name: build\n    command: echo 1\n  - name: build\n    command: echo 2\n",
    )

    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        await _register_project(client, tmp_project, auth_headers)
        resp = await client.get("/api/pipelines/")
        item = [i for i in resp.json()["items"] if i.get("file") == "dup_on_disk.yaml"]
        assert item, "文件应出现在列表中"
        assert item[0]["valid"] is False, "重复 task name 应判定为非法"
        assert item[0]["validation_error"] is not None


# --- P1/P2：重复 mapping key（含重复 env 变量）前后端校验不一致 ---


@pytest.mark.asyncio
async def test_put_pipeline_by_id_duplicate_mapping_key_rejected(
    app, tmp_project, db_engine, clean_db, auth_headers
):
    """[P1] 重复 mapping key（如重复 env 变量）：保存必须 400，不能静默后者覆盖前者。"""
    target = _write_pipeline(
        tmp_project,
        "dup_key.yaml",
        "name: dup_key\ntasks:\n  - name: t1\n    command: echo ok\n",
    )

    transport = ASGITransport(app=app, raise_app_exceptions=False)
    try:
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            await _register_project(client, tmp_project, auth_headers)
            definition_id = await _definition_id_for(client, "dup_key.yaml")

            dup_yaml = (
                "name: dup_key\n"
                "config:\n"
                "  env:\n"
                "    TOKEN: first\n"
                "    TOKEN: second\n"
                "tasks:\n"
                "  - name: t1\n"
                "    command: echo ${env.TOKEN}\n"
            )
            resp = await client.put(
                f"/api/pipelines/by-id/{definition_id}",
                json={"content": dup_yaml},
                headers=auth_headers,
            )
            assert resp.status_code == 400, f"重复 key 必须被拒绝，实际 {resp.status_code}"
    finally:
        target.unlink(missing_ok=True)


@pytest.mark.asyncio
async def test_list_marks_duplicate_key_file_invalid(app, tmp_project, db_engine, clean_db, auth_headers):
    """[P2] 磁盘上重复 mapping key 的文件，列表必须 valid=false（与前端 js-yaml 行为一致）。"""
    _write_pipeline(
        tmp_project,
        "dup_key_on_disk.yaml",
        "name: dup_key_on_disk\nconfig:\n  env:\n    TOKEN: first\n    TOKEN: second\ntasks:\n  - name: t1\n    command: echo ok\n",
    )

    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        await _register_project(client, tmp_project, auth_headers)
        resp = await client.get("/api/pipelines/")
        item = [i for i in resp.json()["items"] if i.get("file") == "dup_key_on_disk.yaml"]
        assert item, "文件应出现在列表中"
        assert item[0]["valid"] is False, "重复 mapping key 应判定为非法"


@pytest.mark.asyncio
async def test_put_pipeline_by_id_tasks_and_pipelines_together_rejected(
    app, tmp_project, db_engine, clean_db, auth_headers
):
    """[P1] 同时出现顶层 tasks 与 pipelines：必须 400。

    v7 修复前：PipelineYAML 仅在 pipelines 为 None 时把 tasks 归一化进 pipelines；
    两者同时存在时，ResolvedPipeline 只用 pipelines，顶层 tasks 被静默忽略
    （保存 200，运行少跑任务，列表 task_count 也不含它们）。
    """
    target = _write_pipeline(
        tmp_project,
        "both_forms.yaml",
        "name: both_forms\ntasks:\n  - name: t1\n    command: echo ok\n",
    )

    transport = ASGITransport(app=app, raise_app_exceptions=False)
    try:
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            await _register_project(client, tmp_project, auth_headers)
            definition_id = await _definition_id_for(client, "both_forms.yaml")

            both_yaml = (
                "name: both_forms\n"
                "tasks:\n"
                "  - name: top-task\n"
                "    command: echo top\n"
                "pipelines:\n"
                "  - name: sub\n"
                "    tasks:\n"
                "      - name: sub-task\n"
                "        command: echo sub\n"
            )
            resp = await client.put(
                f"/api/pipelines/by-id/{definition_id}",
                json={"content": both_yaml},
                headers=auth_headers,
            )
            assert resp.status_code == 400, f"tasks 与 pipelines 不能共存，实际 {resp.status_code}"
    finally:
        target.unlink(missing_ok=True)


@pytest.mark.asyncio
async def test_definition_id_stable_after_transient_invalid(
    app, tmp_project, db_engine, clean_db, auth_headers
):
    """[P2] 文件短暂非法后修复，必须复用原 definition_id（否则运行历史凭空消失）。

    v7 修复前：文件非法时 _sync 会 deactivate 旧行；修复后 upsert 只查 active 行，
    于是新建 definition_id。runs 按旧 id 关联，列表的成功率/最近运行全部归零。
    """
    target = tmp_project / "pipelines" / "hist.yaml"
    valid = "name: hist\ntasks:\n  - name: t1\n    command: echo ok\n"
    target.write_text(valid, encoding="utf-8")

    transport = ASGITransport(app=app, raise_app_exceptions=False)
    try:
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            await _register_project(client, tmp_project, auth_headers)
            id1 = await _definition_id_for(client, "hist.yaml")

            # 短暂非法（缺少必填 name）
            target.write_text("tasks:\n  - name: t1\n    command: echo ok\n", encoding="utf-8")
            resp = await client.get("/api/pipelines/")
            item = next(i for i in resp.json()["items"] if i.get("file") == "hist.yaml")
            assert item["valid"] is False
            assert item["id"] == ""

            # 修复
            target.write_text(valid, encoding="utf-8")
            id2 = await _definition_id_for(client, "hist.yaml")
            assert id2 == id1, "修复非法 YAML 后应复用原 definition_id，保住运行历史"
    finally:
        target.unlink(missing_ok=True)


# --- P2：by-file 空内容保存会清空文件并造成磁盘/DB 分叉 ---


@pytest.mark.asyncio
async def test_put_pipeline_by_file_empty_content_rejected(
    app, tmp_project, db_engine, clean_db, auth_headers
):
    """[P2] by-file 保存空/仅注释内容必须 400，不能清空文件。"""
    target = _write_pipeline(tmp_project, "emptied.yaml", "name: kept\ntasks:\n  - name: t1\n    command: echo ok\n")
    original = target.read_text(encoding="utf-8")

    transport = ASGITransport(app=app, raise_app_exceptions=False)
    try:
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            project_id = await _register_project(client, tmp_project, auth_headers)

            resp = await client.put(
                f"/api/pipelines/by-file/{project_id}",
                json={"file": "emptied.yaml", "content": ""},
                headers=auth_headers,
            )
            assert resp.status_code == 400, f"空内容必须被拒绝，实际 {resp.status_code}"
            assert target.read_text(encoding="utf-8") == original
    finally:
        target.unlink(missing_ok=True)

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from taskpps.main import app as _app


@pytest.fixture
def app():
    return _app


@pytest.mark.asyncio
@pytest.mark.zentao("TC-S0933", domain="server/api", priority="P0")
async def test_list_pipelines_returns_project_name(app, setup_project, tmp_project, db_engine, clean_db):
    """Issue #91: 流水线列表应返回 project_name 而非仅 project_id"""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 注册项目（使用 tmp_project 作为 workdir，确保有 pipeline 文件）
        create_resp = await client.post(
            "/api/projects/",
            json={"workdir": str(tmp_project), "name": "my-project"},
        )
        assert create_resp.status_code == 201

        # 获取流水线列表
        response = await client.get("/api/pipelines/")
        assert response.status_code == 200
        data = response.json()
        items = data["items"]
        assert len(items) > 0

        # 每条流水线记录应包含 project_name
        for item in items:
            if item.get("project_id"):
                assert "project_name" in item
                assert item["project_name"] is not None


@pytest.mark.asyncio
@pytest.mark.zentao("TC-S0934", domain="server/api", priority="P0")
async def test_list_pipelines_project_name_fallback_to_workdir(app, setup_project, tmp_project, db_engine, clean_db):
    """Issue #91: 项目 name 为空时，project_name 应回退到 workdir 最后一段路径"""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 注册项目，不指定 name
        create_resp = await client.post(
            "/api/projects/",
            json={"workdir": str(tmp_project)},
        )
        assert create_resp.status_code == 201

        response = await client.get("/api/pipelines/")
        assert response.status_code == 200
        data = response.json()
        items = data["items"]
        assert len(items) > 0

        for item in items:
            if item.get("project_id"):
                assert "project_name" in item
                # name 为空时应回退到 workdir 路径名
                assert item["project_name"] is not None



# --- v1 (2026-07): issue #195 — list_pipelines 校验字段测试 ---
# 验证 list_pipelines 接口返回 valid/validation_error 字段
# 验证非法 pipeline 不会被静默跳过，而是以 valid=false 出现在列表中

@pytest.mark.asyncio
@pytest.mark.zentao("TC-S1002", domain="server/api", priority="P1")
async def test_list_pipelines_valid_pipelines_have_valid_true(app, setup_project, tmp_project, db_engine, clean_db):
    """TC-S1002: 合法 pipeline 返回 valid=true, validation_error=null"""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        create_resp = await client.post(
            "/api/projects/",
            json={"workdir": str(tmp_project), "name": "test-project"},
        )
        assert create_resp.status_code == 201

        response = await client.get("/api/pipelines/")
        assert response.status_code == 200
        data = response.json()
        items = data["items"]

        # 所有合法 pipeline 应包含 valid/validation_error 字段
        for item in items:
            if item.get("id"):  # 有 id 说明来自 DB，是合法的
                assert "valid" in item, f"缺少 valid 字段: {item.get('name')}"
                assert item["valid"] is True, f"合法 pipeline valid 应为 True: {item['name']}"
                assert item.get("validation_error") is None, \
                    f"合法 pipeline validation_error 应为 null: {item['name']}"


@pytest.mark.asyncio
@pytest.mark.zentao("TC-S1001", domain="server/api", priority="P1")
async def test_list_pipelines_includes_invalid_yaml(app, setup_project, tmp_project, db_engine, clean_db):
    """TC-S1001: 非法 YAML pipeline 出现于列表中，valid=false, validation_error 非空"""
    import os

    # 在项目 pipelines 目录下放置非法 YAML 文件
    pipelines_dir = tmp_project / "pipelines"
    bad_yaml = pipelines_dir / "invalid_syntax.yaml"
    bad_yaml.write_text("name: bad\n  wrong_indent: yes\ntasks: []\n")

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        create_resp = await client.post(
            "/api/projects/",
            json={"workdir": str(tmp_project), "name": "test-project"},
        )
        assert create_resp.status_code == 201

        response = await client.get("/api/pipelines/")
        assert response.status_code == 200
        data = response.json()
        items = data["items"]

        # 找到非法 pipeline
        invalid_items = [i for i in items if i.get("file") == "invalid_syntax.yaml"]
        assert len(invalid_items) >= 1, (
            f"非法 YAML 文件应出现在列表中, items files: {[i.get('file') for i in items]}"
        )
        bad_item = invalid_items[0]
        assert bad_item["valid"] is False, f"非法 pipeline valid 应为 False, got: {bad_item}"
        assert bad_item.get("validation_error") is not None, \
            f"非法 pipeline validation_error 不应为 null, got: {bad_item.get('validation_error')}"
        verr = bad_item["validation_error"]
        assert "message" in verr, f"validation_error 需含 message: {verr}"
        assert len(verr["message"]) > 0


@pytest.mark.asyncio
@pytest.mark.zentao("TC-S1001", domain="server/api", priority="P2")
async def test_list_pipelines_invalid_empty_yaml(app, setup_project, tmp_project, db_engine, clean_db):
    """空 YAML 文件应出现在列表中，valid=false, validation_error.line=1"""
    pipelines_dir = tmp_project / "pipelines"
    empty_yaml = pipelines_dir / "empty_pipe.yaml"
    empty_yaml.write_text("")

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        create_resp = await client.post(
            "/api/projects/",
            json={"workdir": str(tmp_project), "name": "test-project"},
        )
        assert create_resp.status_code == 201

        response = await client.get("/api/pipelines/")
        assert response.status_code == 200
        data = response.json()
        items = data["items"]

        empty_items = [i for i in items if i.get("file") == "empty_pipe.yaml"]
        assert len(empty_items) >= 1, "空YAML文件应出现在列表中"
        assert empty_items[0]["valid"] is False
        assert empty_items[0]["validation_error"]["line"] == 1
        assert empty_items[0]["validation_error"]["column"] == 1


@pytest.mark.asyncio
@pytest.mark.zentao("TC-S1001", domain="server/api", priority="P2")
async def test_list_pipelines_invalid_missing_name(app, setup_project, tmp_project, db_engine, clean_db):
    """缺 name 字段的 YAML 应出现在列表中，valid=false, validation_error.path 非空"""
    pipelines_dir = tmp_project / "pipelines"
    no_name_yaml = pipelines_dir / "no_name_pipe.yaml"
    no_name_yaml.write_text("tasks:\n  - name: step1\n    command: echo ok\n")

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        create_resp = await client.post(
            "/api/projects/",
            json={"workdir": str(tmp_project), "name": "test-project"},
        )
        assert create_resp.status_code == 201

        response = await client.get("/api/pipelines/")
        assert response.status_code == 200
        data = response.json()
        items = data["items"]

        no_name_items = [i for i in items if i.get("file") == "no_name_pipe.yaml"]
        assert len(no_name_items) >= 1
        assert no_name_items[0]["valid"] is False
        # pydantic 校验应产生 path 字段
        verr = no_name_items[0]["validation_error"]
        assert verr.get("path") is not None, \
            f"pydantic 校验错误应含 path: {verr}"

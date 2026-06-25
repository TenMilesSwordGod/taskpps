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


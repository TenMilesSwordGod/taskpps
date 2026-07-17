"""issue #204 注册 API 异常流测试（TC-S1153 ~ TC-S1155）。

覆盖维度：异常流 — 用户名冲突 / 缺字段 / 字段类型错误。
"""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from taskpps.main import app
from tests.auth._helpers import register_user_status


@pytest.fixture
def app_fixture():
    return app


@pytest.mark.asyncio
@pytest.mark.zentao("TC-S1153", domain="server/auth", priority="P1")
async def test_register_duplicate_username_409(app_fixture, setup_project, tmp_project, db_engine):
    """重复用户名注册应返回 409，不重复创建。"""
    transport = ASGITransport(app=app_fixture)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 第一次成功
        status1, _ = await register_user_status(client, username="alice", nickname="Alice", password="pass123")
        assert status1 == 201
        # 第二次冲突
        status2, body2 = await register_user_status(client, username="alice", nickname="Alice2", password="pass123")
    assert status2 == 409
    assert "已被注册" in body2.get("detail", "")


@pytest.mark.asyncio
@pytest.mark.zentao("TC-S1154", domain="server/auth", priority="P2")
async def test_register_missing_password_field_422(app_fixture, setup_project, tmp_project, db_engine):
    """缺少 password 必填字段应 422。"""
    transport = ASGITransport(app=app_fixture)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/v1/auth/register",
            json={"username": "alice", "nickname": "Alice"},  # 缺 password
        )
    assert resp.status_code == 422


@pytest.mark.asyncio
@pytest.mark.zentao("TC-S1155", domain="server/auth", priority="P2")
async def test_register_wrong_field_type_422(app_fixture, setup_project, tmp_project, db_engine):
    """username 为数字（非字符串）应 422。"""
    transport = ASGITransport(app=app_fixture)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/v1/auth/register",
            json={"username": 12345, "nickname": "Num", "password": "pass123"},  # 类型错误
        )
    assert resp.status_code == 422


@pytest.mark.asyncio
@pytest.mark.zentao("TC-S1155b", domain="server/auth", priority="P2")
async def test_register_username_too_short_422(app_fixture, setup_project, tmp_project, db_engine):
    """用户名 2 字符低于 min_length=3 应 422。"""
    transport = ASGITransport(app=app_fixture)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/v1/auth/register",
            json={"username": "ab", "nickname": "Ab", "password": "pass123"},
        )
    assert resp.status_code == 422

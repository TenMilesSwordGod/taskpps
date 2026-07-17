"""issue #204 注册 API 边界值测试（TC-S1148 ~ TC-S1152）。

覆盖维度：边界值 — 用户名/密码的 min/max 长度、特殊字符、合法下限/上限。
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
@pytest.mark.zentao("TC-S1148", domain="server/auth", priority="P2")
async def test_register_username_min_length_3(app_fixture, setup_project, tmp_project, db_engine):
    """用户名 3 字符合法下限应注册成功。"""
    transport = ASGITransport(app=app_fixture)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        status, body = await register_user_status(client, username="abc", nickname="Abc", password="pass123")
    assert status == 201
    assert body["username"] == "abc"
    assert body["role"] == "user"
    assert body["avatar"]  # 非空


@pytest.mark.asyncio
@pytest.mark.zentao("TC-S1149", domain="server/auth", priority="P2")
async def test_register_username_max_length_32(app_fixture, setup_project, tmp_project, db_engine):
    """用户名 32 字符合法上限应注册成功。"""
    username = "a" * 32
    transport = ASGITransport(app=app_fixture)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        status, body = await register_user_status(client, username=username, nickname="Long", password="pass123")
    assert status == 201
    assert body["username"] == username


@pytest.mark.asyncio
@pytest.mark.zentao("TC-S1150", domain="server/auth", priority="P2")
async def test_register_username_special_char_rejected(app_fixture, setup_project, tmp_project, db_engine):
    """用户名含 @ 非法字符应 422（pattern ^[a-zA-Z0-9_-]+$）。"""
    transport = ASGITransport(app=app_fixture)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        status, _ = await register_user_status(client, username="ab@cd", nickname="Bad", password="pass123")
    assert status == 422


@pytest.mark.asyncio
@pytest.mark.zentao("TC-S1151", domain="server/auth", priority="P2")
async def test_register_password_min_length_6(app_fixture, setup_project, tmp_project, db_engine):
    """密码 6 字符合法下限应注册成功。"""
    transport = ASGITransport(app=app_fixture)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        status, body = await register_user_status(client, username="bob01", nickname="Bob", password="123456")
    assert status == 201
    assert body["username"] == "bob01"


@pytest.mark.asyncio
@pytest.mark.zentao("TC-S1152", domain="server/auth", priority="P2")
async def test_register_password_max_length_64(app_fixture, setup_project, tmp_project, db_engine):
    """密码 64 字符合法上限应注册成功。"""
    password = "p" * 64
    transport = ASGITransport(app=app_fixture)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        status, body = await register_user_status(client, username="carol1", nickname="Carol", password=password)
    assert status == 201
    assert body["username"] == "carol1"

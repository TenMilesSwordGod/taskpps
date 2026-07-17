"""issue #204 登录 API 异常流测试（TC-S1157 ~ TC-S1160）。

覆盖维度：异常流 — 用户不存在 / 密码错 / 账号禁用 / 缺字段（含防枚举校验）。
"""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient
from sqlmodel import select

from taskpps.db.engine import get_session_factory
from taskpps.main import app
from taskpps.models.user import User
from tests.auth._helpers import register_user_status


@pytest.fixture
def app_fixture():
    return app


@pytest.mark.asyncio
@pytest.mark.zentao("TC-S1157", domain="server/auth", priority="P1")
async def test_login_nonexistent_user_401_no_enumeration(app_fixture, setup_project, tmp_project, db_engine):
    """用户名不存在应 401，文案与密码错一致（防枚举）。"""
    transport = ASGITransport(app=app_fixture)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/v1/auth/login",
            json={"username": "ghost", "password": "whatever"},
        )
    assert resp.status_code == 401
    assert resp.json()["detail"] == "用户名或密码错误"


@pytest.mark.asyncio
@pytest.mark.zentao("TC-S1158", domain="server/auth", priority="P1")
async def test_login_wrong_password_401_same_message(app_fixture, setup_project, tmp_project, db_engine):
    """密码错误应 401，文案与用户不存在完全相同（防枚举）。"""
    transport = ASGITransport(app=app_fixture)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        await register_user_status(client, username="alice", nickname="Alice", password="pass123")
        resp = await client.post(
            "/api/v1/auth/login",
            json={"username": "alice", "password": "wrongpass"},
        )
    assert resp.status_code == 401
    assert resp.json()["detail"] == "用户名或密码错误"


@pytest.mark.asyncio
@pytest.mark.zentao("TC-S1159", domain="server/auth", priority="P2")
async def test_login_disabled_account_403(app_fixture, setup_project, tmp_project, db_engine):
    """账号被禁用（is_active=false）应返回 403。"""
    transport = ASGITransport(app=app_fixture)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        await register_user_status(client, username="bob01", nickname="Bob", password="pass123")
        # 直接改 DB 禁用账号
        async with get_session_factory()() as session:
            result = await session.execute(select(User).where(User.username == "bob01"))
            user = result.scalar_one()
            user.is_active = False
            session.add(user)
            await session.commit()
        # 登录应 403
        resp = await client.post(
            "/api/v1/auth/login",
            json={"username": "bob01", "password": "pass123"},
        )
    assert resp.status_code == 403
    assert "禁用" in resp.json()["detail"]


@pytest.mark.asyncio
@pytest.mark.zentao("TC-S1160", domain="server/auth", priority="P2")
async def test_login_missing_username_422(app_fixture, setup_project, tmp_project, db_engine):
    """缺 username 字段应 422（min_length=1）。"""
    transport = ASGITransport(app=app_fixture)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/v1/auth/login",
            json={"password": "pass123"},  # 缺 username
        )
    assert resp.status_code == 422

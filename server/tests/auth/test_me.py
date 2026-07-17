"""issue #204 /me API 测试（TC-S1181 ~ TC-S1184）。

覆盖维度：边界 + 异常 — 有效 token / 无 token / 无效 token / 用户已删除。
"""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient
from sqlmodel import delete, select

from taskpps.db.engine import get_session_factory
from taskpps.main import app
from taskpps.models.user import User
from tests.auth._helpers import register_user_status


async def _login(client: AsyncClient, username: str, password: str) -> str:
    resp = await client.post("/api/v1/auth/login", json={"username": username, "password": password})
    assert resp.status_code == 200, f"login failed: {resp.text}"
    return resp.json()["access_token"]


@pytest.fixture
def app_fixture():
    return app


@pytest.mark.asyncio
@pytest.mark.zentao("TC-S1181", domain="server/auth", priority="P0")
async def test_me_valid_token_returns_user(app_fixture, setup_project, tmp_project, db_engine):
    """有效 token GET /me 应 200 返回完整用户信息。"""
    transport = ASGITransport(app=app_fixture)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        await register_user_status(client, username="alice", nickname="Alice", password="pass123")
        token = await _login(client, "alice", "pass123")
        resp = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["username"] == "alice"
    assert data["nickname"] == "Alice"
    assert data["role"] == "user"
    assert data["avatar"]
    assert "password_hash" not in data  # 不泄露密码哈希


@pytest.mark.asyncio
@pytest.mark.zentao("TC-S1182", domain="server/auth", priority="P1")
async def test_me_no_token_401(app_fixture, setup_project, tmp_project, db_engine):
    """无 token GET /me 应 401（路由层判断 guest）。"""
    transport = ASGITransport(app=app_fixture)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/v1/auth/me")
    assert resp.status_code == 401
    assert resp.json()["detail"] == "未登录"


@pytest.mark.asyncio
@pytest.mark.zentao("TC-S1183", domain="server/auth", priority="P1")
async def test_me_invalid_token_401(app_fixture, setup_project, tmp_project, db_engine):
    """无效 token GET /me 应 401（中间件设 guest，路由层 401）。"""
    transport = ASGITransport(app=app_fixture)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get(
            "/api/v1/auth/me",
            headers={"Authorization": "Bearer not.a.real.token"},
        )
    assert resp.status_code == 401


@pytest.mark.asyncio
@pytest.mark.zentao("TC-S1184", domain="server/auth", priority="P2")
async def test_me_user_deleted_401(app_fixture, setup_project, tmp_project, db_engine):
    """token 有效但用户已被删除应 401「用户不存在」。"""
    transport = ASGITransport(app=app_fixture)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        await register_user_status(client, username="alice", nickname="Alice", password="pass123")
        token = await _login(client, "alice", "pass123")
        # 从 DB 删除 alice
        async with get_session_factory()() as session:
            result = await session.execute(select(User).where(User.username == "alice"))
            user = result.scalar_one()
            await session.delete(user)
            await session.commit()
        # 用原 token 访问 /me
        resp = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 401
    assert resp.json()["detail"] == "用户不存在"

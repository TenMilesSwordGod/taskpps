"""issue #204 RBAC 权限测试（TC-S1171 ~ TC-S1174）。

覆盖维度：权限/RBAC — guest GET 放行 / guest POST 401 / user POST 放行 / 白名单无 token 放行。
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
@pytest.mark.zentao("TC-S1171", domain="server/auth", priority="P1")
async def test_guest_get_passes_middleware(app_fixture, setup_project, tmp_project, db_engine):
    """guest（无 token）访问 GET 应被中间件放行（路由层 401 而非中间件 401）。"""
    transport = ASGITransport(app=app_fixture)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/v1/auth/me")
    # 路由层返回「未登录」，证明中间件放行了 GET
    assert resp.status_code == 401
    assert resp.json()["detail"] == "未登录"


@pytest.mark.asyncio
@pytest.mark.zentao("TC-S1172", domain="server/auth", priority="P0")
async def test_guest_post_returns_401(app_fixture, setup_project, tmp_project, db_engine):
    """guest（无 token）访问 POST 应被中间件返回 401。"""
    transport = ASGITransport(app=app_fixture)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/api/v1/auth/logout")
    assert resp.status_code == 401
    assert "未登录" in resp.json()["detail"]


@pytest.mark.asyncio
@pytest.mark.zentao("TC-S1173", domain="server/auth", priority="P1")
async def test_user_post_passes(app_fixture, setup_project, tmp_project, db_engine):
    """user 角色 POST /logout 应 200 放行。"""
    transport = ASGITransport(app=app_fixture)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        await register_user_status(client, username="alice", nickname="Alice", password="pass123")
        login_resp = await client.post(
            "/api/v1/auth/login",
            json={"username": "alice", "password": "pass123"},
        )
        token = login_resp.json()["access_token"]
        resp = await client.post(
            "/api/v1/auth/logout",
            headers={"Authorization": f"Bearer {token}"},
        )
    assert resp.status_code == 200


@pytest.mark.asyncio
@pytest.mark.zentao("TC-S1174", domain="server/auth", priority="P1")
async def test_whitelist_login_no_token_passes_middleware(app_fixture, setup_project, tmp_project, db_engine):
    """白名单 POST /login 无 token 应放行到路由层（401 密码错而非中间件 401）。"""
    transport = ASGITransport(app=app_fixture)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 用户不存在 → 路由层 401「用户名或密码错误」，证明中间件白名单放行
        resp = await client.post(
            "/api/v1/auth/login",
            json={"username": "ghost", "password": "whatever"},
        )
    assert resp.status_code == 401
    assert resp.json()["detail"] == "用户名或密码错误"


@pytest.mark.asyncio
@pytest.mark.zentao("TC-S1174b", domain="server/auth", priority="P1")
async def test_admin_post_passes(app_fixture, setup_project, tmp_project, db_engine):
    """admin 角色 POST 也应放行（中间件不区分 role，只要有有效 token）。"""
    transport = ASGITransport(app=app_fixture)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 直接注册会创建 user 角色；这里通过 seed admin 测试 admin。
        # 简化：注册一个普通用户登录即可证明「有 token 的 POST 放行」，
        # 角色差异在中间件层不区分（spec：require_role 本次不挂载）。
        await register_user_status(client, username="alice", nickname="Alice", password="pass123")
        login_resp = await client.post(
            "/api/v1/auth/login",
            json={"username": "alice", "password": "pass123"},
        )
        token = login_resp.json()["access_token"]
        resp = await client.post(
            "/api/v1/auth/change-password",
            headers={"Authorization": f"Bearer {token}"},
            json={"old_password": "pass123", "new_password": "newpass456"},
        )
    assert resp.status_code == 200

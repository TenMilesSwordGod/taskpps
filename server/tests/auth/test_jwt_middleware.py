"""issue #204 JWT 中间件测试（TC-S1161 ~ TC-S1170）。

覆盖维度：边界/异常/环境 — 白名单 / GET 放行 / POST 强制 JWT /
         token 过期 / token 篡改 / 非 api 路径 / WebSocket 路径。
"""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from taskpps.auth.security import create_access_token
from taskpps.main import app
from tests.auth._helpers import register_user_status


@pytest.fixture
def app_fixture():
    return app


@pytest.mark.asyncio
@pytest.mark.zentao("TC-S1161", domain="server/auth", priority="P1")
async def test_whitelist_path_no_token_not_blocked(app_fixture, setup_project, tmp_project, db_engine):
    """白名单路径 POST /register 无 token 不应被中间件 401 拦截（应 422 或 201）。"""
    transport = ASGITransport(app=app_fixture)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 提交非法 body（密码太短），应被 pydantic 校验拦为 422，而非中间件 401
        resp = await client.post(
            "/api/v1/auth/register",
            json={"username": "ab", "nickname": "Ab", "password": "123"},  # 非法
        )
    assert resp.status_code != 401
    assert resp.status_code == 422


@pytest.mark.asyncio
@pytest.mark.zentao("TC-S1162", domain="server/auth", priority="P0")
async def test_get_no_token_sets_guest_passes_middleware(app_fixture, setup_project, tmp_project, db_engine):
    """GET /me 无 token：中间件放行（设 guest），路由层返回 401（非中间件 401）。"""
    transport = ASGITransport(app=app_fixture)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/v1/auth/me")
    # 路由层 guest → 401「未登录」，证明中间件放行了 GET
    assert resp.status_code == 401
    assert resp.json()["detail"] == "未登录"


@pytest.mark.asyncio
@pytest.mark.zentao("TC-S1163", domain="server/auth", priority="P1")
async def test_get_invalid_token_sets_guest_passes_middleware(app_fixture, setup_project, tmp_project, db_engine):
    """GET /me 带无效 token：中间件设 guest 放行，路由层 401。"""
    transport = ASGITransport(app=app_fixture)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get(
            "/api/v1/auth/me",
            headers={"Authorization": "Bearer invalid.token.here"},
        )
    assert resp.status_code == 401
    assert resp.json()["detail"] == "未登录"


@pytest.mark.asyncio
@pytest.mark.zentao("TC-S1164", domain="server/auth", priority="P0")
async def test_post_no_token_returns_401(app_fixture, setup_project, tmp_project, db_engine):
    """POST /logout 无 token 应被中间件拦截返回 401。"""
    transport = ASGITransport(app=app_fixture)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/api/v1/auth/logout")
    assert resp.status_code == 401
    assert "未登录" in resp.json()["detail"]


@pytest.mark.asyncio
@pytest.mark.zentao("TC-S1165", domain="server/auth", priority="P1")
async def test_post_fake_token_returns_401(app_fixture, setup_project, tmp_project, db_engine):
    """POST /logout 带伪造 token 应 401（decode 失败）。"""
    transport = ASGITransport(app=app_fixture)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/v1/auth/logout",
            headers={"Authorization": "Bearer fake.token.here"},
        )
    assert resp.status_code == 401


@pytest.mark.asyncio
@pytest.mark.zentao("TC-S1166", domain="server/auth", priority="P0")
async def test_post_valid_token_passes(app_fixture, setup_project, tmp_project, db_engine):
    """POST /logout 带有效 token 应 200（中间件放行）。"""
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
    assert resp.json()["message"] == "已登出"


@pytest.mark.asyncio
@pytest.mark.zentao("TC-S1167", domain="server/auth", priority="P2")
async def test_non_api_path_not_blocked(app_fixture, setup_project, tmp_project, db_engine):
    """GET / 非 /api/ 路径应直接放行（非 401）。"""
    transport = ASGITransport(app=app_fixture)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/")
    # 非 401 即可（实际可能 200 有 index.html 或 404 无静态目录）
    assert resp.status_code != 401


@pytest.mark.asyncio
@pytest.mark.zentao("TC-S1168", domain="server/auth", priority="P2")
async def test_ws_path_not_blocked(app_fixture, setup_project, tmp_project, db_engine):
    """GET /api/ws/xxx WebSocket 路径应放行（非 401）。"""
    transport = ASGITransport(app=app_fixture)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/ws/status")
    assert resp.status_code != 401


@pytest.mark.asyncio
@pytest.mark.zentao("TC-S1169", domain="server/auth", priority="P1")
async def test_expired_token_returns_401(app_fixture, setup_project, tmp_project, db_engine):
    """过期 token 的 POST 请求应 401（decode_token 返回 None）。"""
    transport = ASGITransport(app=app_fixture)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 用负数 expires_hours 签发已过期 token
        expired_token = create_access_token(username="alice", role="user", expires_hours=-1)
        resp = await client.post(
            "/api/v1/auth/logout",
            headers={"Authorization": f"Bearer {expired_token}"},
        )
    assert resp.status_code == 401


@pytest.mark.asyncio
@pytest.mark.zentao("TC-S1170", domain="server/auth", priority="P1")
async def test_tampered_token_returns_401(app_fixture, setup_project, tmp_project, db_engine):
    """篡改 token 签名应 401（签名校验失败）。"""
    transport = ASGITransport(app=app_fixture)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        await register_user_status(client, username="alice", nickname="Alice", password="pass123")
        login_resp = await client.post(
            "/api/v1/auth/login",
            json={"username": "alice", "password": "pass123"},
        )
        token = login_resp.json()["access_token"]
        # 篡改最后一段的末尾字符
        parts = token.split(".")
        tampered = parts[0] + "." + parts[1] + "." + (parts[2][:-1] + ("A" if parts[2][-1] != "A" else "B"))
        resp = await client.post(
            "/api/v1/auth/logout",
            headers={"Authorization": f"Bearer {tampered}"},
        )
    assert resp.status_code == 401

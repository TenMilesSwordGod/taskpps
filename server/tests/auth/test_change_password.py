"""issue #204 修改密码 API 测试（TC-S1175 ~ TC-S1180）。

覆盖维度：异常流 + 边界 — 旧密码错 / 新旧相同 / 新密码长度 / 未登录 / 改后旧密码失效。
"""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from taskpps.main import app
from tests.auth._helpers import register_user_status


async def _login(client: AsyncClient, username: str, password: str) -> str:
    """登录返回 token。"""
    resp = await client.post("/api/v1/auth/login", json={"username": username, "password": password})
    assert resp.status_code == 200, f"login failed: {resp.text}"
    return resp.json()["access_token"]


@pytest.fixture
def app_fixture():
    return app


@pytest.mark.asyncio
@pytest.mark.zentao("TC-S1175", domain="server/auth", priority="P0")
async def test_change_password_success(app_fixture, setup_project, tmp_project, db_engine):
    """正确旧密码 + 合法新密码应 200，且旧密码登录失败、新密码登录成功。"""
    transport = ASGITransport(app=app_fixture)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        await register_user_status(client, username="alice", nickname="Alice", password="pass123")
        token = await _login(client, "alice", "pass123")
        # 改密码
        resp = await client.post(
            "/api/v1/auth/change-password",
            headers={"Authorization": f"Bearer {token}"},
            json={"old_password": "pass123", "new_password": "newpass456"},
        )
        assert resp.status_code == 200
        assert resp.json()["message"] == "密码修改成功"
        # 旧密码登录应失败
        old_login = await client.post(
            "/api/v1/auth/login",
            json={"username": "alice", "password": "pass123"},
        )
        assert old_login.status_code == 401
        # 新密码登录应成功
        new_login = await client.post(
            "/api/v1/auth/login",
            json={"username": "alice", "password": "newpass456"},
        )
        assert new_login.status_code == 200


@pytest.mark.asyncio
@pytest.mark.zentao("TC-S1176", domain="server/auth", priority="P1")
async def test_change_password_wrong_old_401(app_fixture, setup_project, tmp_project, db_engine):
    """旧密码错误应 401。"""
    transport = ASGITransport(app=app_fixture)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        await register_user_status(client, username="alice", nickname="Alice", password="pass123")
        token = await _login(client, "alice", "pass123")
        resp = await client.post(
            "/api/v1/auth/change-password",
            headers={"Authorization": f"Bearer {token}"},
            json={"old_password": "wrongpass", "new_password": "newpass456"},
        )
    assert resp.status_code == 401
    assert resp.json()["detail"] == "旧密码错误"


@pytest.mark.asyncio
@pytest.mark.zentao("TC-S1177", domain="server/auth", priority="P2")
async def test_change_password_same_old_new_400(app_fixture, setup_project, tmp_project, db_engine):
    """新密码与旧密码相同应 400。"""
    transport = ASGITransport(app=app_fixture)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        await register_user_status(client, username="alice", nickname="Alice", password="pass123")
        token = await _login(client, "alice", "pass123")
        resp = await client.post(
            "/api/v1/auth/change-password",
            headers={"Authorization": f"Bearer {token}"},
            json={"old_password": "pass123", "new_password": "pass123"},
        )
    assert resp.status_code == 400
    assert "相同" in resp.json()["detail"]


@pytest.mark.asyncio
@pytest.mark.zentao("TC-S1178", domain="server/auth", priority="P2")
async def test_change_password_new_too_short_422(app_fixture, setup_project, tmp_project, db_engine):
    """新密码 5 字符低于 min_length=6 应 422。"""
    transport = ASGITransport(app=app_fixture)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        await register_user_status(client, username="alice", nickname="Alice", password="pass123")
        token = await _login(client, "alice", "pass123")
        resp = await client.post(
            "/api/v1/auth/change-password",
            headers={"Authorization": f"Bearer {token}"},
            json={"old_password": "pass123", "new_password": "12345"},
        )
    assert resp.status_code == 422


@pytest.mark.asyncio
@pytest.mark.zentao("TC-S1179", domain="server/auth", priority="P1")
async def test_change_password_no_token_401(app_fixture, setup_project, tmp_project, db_engine):
    """无 token 调 change-password 应被中间件 401。"""
    transport = ASGITransport(app=app_fixture)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/v1/auth/change-password",
            json={"old_password": "pass123", "new_password": "newpass456"},
        )
    assert resp.status_code == 401
    assert "未登录" in resp.json()["detail"]


@pytest.mark.asyncio
@pytest.mark.zentao("TC-S1180", domain="server/auth", priority="P1")
async def test_old_password_login_fails_after_change(app_fixture, setup_project, tmp_project, db_engine):
    """改密后用旧密码登录应 401（与 TC-S1175 互补，单独验证登录失效）。"""
    transport = ASGITransport(app=app_fixture)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        await register_user_status(client, username="alice", nickname="Alice", password="pass123")
        token = await _login(client, "alice", "pass123")
        await client.post(
            "/api/v1/auth/change-password",
            headers={"Authorization": f"Bearer {token}"},
            json={"old_password": "pass123", "new_password": "newpass456"},
        )
        resp = await client.post(
            "/api/v1/auth/login",
            json={"username": "alice", "password": "pass123"},
        )
    assert resp.status_code == 401

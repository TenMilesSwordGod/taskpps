"""issue #204 登录 API 边界值/主流程测试（TC-S1156）。

覆盖维度：边界值 — 正确凭据返回 JWT + 用户信息。
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
@pytest.mark.zentao("TC-S1156", domain="server/auth", priority="P0")
async def test_login_valid_credentials_returns_jwt(app_fixture, setup_project, tmp_project, db_engine):
    """正确凭据登录应返回 200 + access_token + 用户信息（含 nickname/role）。"""
    transport = ASGITransport(app=app_fixture)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 先注册
        reg_status, _ = await register_user_status(client, username="alice", nickname="Alice", password="pass123")
        assert reg_status == 201
        # 登录
        resp = await client.post(
            "/api/v1/auth/login",
            json={"username": "alice", "password": "pass123"},
        )
    assert resp.status_code == 200
    data = resp.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"
    user = data["user"]
    assert user["username"] == "alice"
    assert user["nickname"] == "Alice"
    assert user["role"] == "user"
    assert user["avatar"]  # 非空

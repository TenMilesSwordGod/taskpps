"""issue #204 并发测试（TC-S1185 ~ TC-S1187）。

覆盖维度：并发 — 并发注册相同用户名 / 并发登录无状态污染 / 并发改密幂等。
"""

from __future__ import annotations

import asyncio

import pytest
from httpx import ASGITransport, AsyncClient

from taskpps.main import app
from tests.auth._helpers import register_user_status


async def _login(client: AsyncClient, username: str, password: str) -> str:
    resp = await client.post("/api/v1/auth/login", json={"username": username, "password": password})
    assert resp.status_code == 200, f"login failed: {resp.text}"
    return resp.json()["access_token"]


@pytest.fixture
def app_fixture():
    return app


@pytest.mark.asyncio
@pytest.mark.zentao("TC-S1185", domain="server/auth", priority="P1")
async def test_concurrent_register_same_username_only_one_succeeds(app_fixture, setup_project, tmp_project, db_engine):
    """10 个并发请求注册相同 username，应仅 1 个 201，其余 409（唯一约束兜底）。"""
    transport = ASGITransport(app=app_fixture)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 用不同 client 实例模拟并发（共享同一 transport/app）
        async def try_register():
            return await client.post(
                "/api/v1/auth/register",
                json={"username": "alice", "nickname": "Alice", "password": "pass123"},
            )

        results = await asyncio.gather(*[try_register() for _ in range(10)])
    statuses = [r.status_code for r in results]
    success = [s for s in statuses if s == 201]
    conflict = [s for s in statuses if s == 409]
    # 允许个别 500（极端竞态下 DB 唯一约束报错被 except 捕获），但成功必须恰 1 个
    assert len(success) == 1, f"expected exactly 1 success, got {len(success)}: {statuses}"
    # 其余应主要是 409
    assert len(conflict) >= 8, f"expected >=8 conflicts, got {len(conflict)}: {statuses}"


@pytest.mark.asyncio
@pytest.mark.zentao("TC-S1186", domain="server/auth", priority="P2")
async def test_concurrent_login_no_state_pollution(app_fixture, setup_project, tmp_project, db_engine):
    """并发登录多个用户，各请求独立返回正确用户信息（无 request.state 串扰）。"""
    transport = ASGITransport(app=app_fixture)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 注册 3 个用户
        for name in ["alice", "bob01", "carol1"]:
            await register_user_status(client, username=name, nickname=name.title(), password="pass123")

        async def login_one(username: str):
            resp = await client.post(
                "/api/v1/auth/login",
                json={"username": username, "password": "pass123"},
            )
            return resp

        # 同一 client 串行调用会有连接复用，但中间件 per-request state 应隔离
        results = await asyncio.gather(
            login_one("alice"),
            login_one("bob01"),
            login_one("carol1"),
        )
    for i, username in enumerate(["alice", "bob01", "carol1"]):
        assert results[i].status_code == 200
        assert results[i].json()["user"]["username"] == username


@pytest.mark.asyncio
@pytest.mark.zentao("TC-S1187", domain="server/auth", priority="P2")
async def test_concurrent_change_password_at_most_one_succeeds(app_fixture, setup_project, tmp_project, db_engine):
    """同一 token 并发提交改密，至多 1 个成功（其余旧密码已变 401）。"""
    transport = ASGITransport(app=app_fixture)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        await register_user_status(client, username="alice", nickname="Alice", password="pass123")
        token = await _login(client, "alice", "pass123")

        async def try_change():
            return await client.post(
                "/api/v1/auth/change-password",
                headers={"Authorization": f"Bearer {token}"},
                json={"old_password": "pass123", "new_password": "newpass456"},
            )

        results = await asyncio.gather(*[try_change() for _ in range(5)])
    statuses = [r.status_code for r in results]
    success = [s for s in statuses if s == 200]
    # 至多 1 个成功（第一个改完后旧密码失效）
    assert len(success) <= 1, f"expected <=1 success, got {len(success)}: {statuses}"
    # 至少有 1 个失败（401 旧密码错 或 400 新旧相同）
    failed = [s for s in statuses if s in (400, 401)]
    assert len(failed) >= 4, f"expected >=4 failures, got {len(failed)}: {statuses}"

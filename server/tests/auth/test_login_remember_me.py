"""issue #204 remember_me（30天免登录）测试。

覆盖维度：
- remember_me=True 时 token 过期时间为 30 天（720h）
- remember_me=False 时 token 过期时间为默认 24h
- 不传 remember_me（向后兼容）时行为与 False 一致
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from httpx import ASGITransport, AsyncClient
from jose import jwt

from taskpps.auth.security import _get_jwt_secret, _JWT_ALGORITHM
from taskpps.main import app
from tests.auth._helpers import register_user_status


@pytest.fixture
def app_fixture():
    return app


def _decode_token_payload(token: str) -> dict:
    """直接解码 JWT（不校验过期），取出 payload 中的 exp。"""
    return jwt.decode(token, _get_jwt_secret(), algorithms=[_JWT_ALGORITHM], options={"verify_exp": False})


@pytest.mark.asyncio
async def test_login_remember_me_true_expires_30d(app_fixture, setup_project, tmp_project, db_engine):
    """remember_me=True 时 token 的 exp 应在 30 天左右（720h）。"""
    transport = ASGITransport(app=app_fixture)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        await register_user_status(client, username="alice", nickname="Alice", password="pass123")
        resp = await client.post(
            "/api/v1/auth/login",
            json={"username": "alice", "password": "pass123", "remember_me": True},
        )
    assert resp.status_code == 200
    token = resp.json()["access_token"]
    payload = _decode_token_payload(token)
    exp = payload["exp"]
    iat = payload["iat"]
    # 过期时间应约为 720h（允许前后 1 分钟误差）
    diff_hours = (datetime.fromtimestamp(exp, tz=timezone.utc) - datetime.fromtimestamp(iat, tz=timezone.utc)).total_seconds() / 3600
    assert 719 <= diff_hours <= 721, f"期望 ~720h，实际 {diff_hours:.2f}h"


@pytest.mark.asyncio
async def test_login_remember_me_false_expires_24h(app_fixture, setup_project, tmp_project, db_engine):
    """remember_me=False 时 token 的 exp 应在 24 小时左右。"""
    transport = ASGITransport(app=app_fixture)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        await register_user_status(client, username="bob", nickname="Bob", password="pass123")
        resp = await client.post(
            "/api/v1/auth/login",
            json={"username": "bob", "password": "pass123", "remember_me": False},
        )
    assert resp.status_code == 200
    token = resp.json()["access_token"]
    payload = _decode_token_payload(token)
    exp = payload["exp"]
    iat = payload["iat"]
    diff_hours = (datetime.fromtimestamp(exp, tz=timezone.utc) - datetime.fromtimestamp(iat, tz=timezone.utc)).total_seconds() / 3600
    assert 23 <= diff_hours <= 25, f"期望 ~24h，实际 {diff_hours:.2f}h"


@pytest.mark.asyncio
async def test_login_no_remember_me_backward_compatible(app_fixture, setup_project, tmp_project, db_engine):
    """不传 remember_me 字段（旧客户端）时，行为与 False 一致（24h）。"""
    transport = ASGITransport(app=app_fixture)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        await register_user_status(client, username="carol", nickname="Carol", password="pass123")
        resp = await client.post(
            "/api/v1/auth/login",
            json={"username": "carol", "password": "pass123"},
        )
    assert resp.status_code == 200
    token = resp.json()["access_token"]
    payload = _decode_token_payload(token)
    exp = payload["exp"]
    iat = payload["iat"]
    diff_hours = (datetime.fromtimestamp(exp, tz=timezone.utc) - datetime.fromtimestamp(iat, tz=timezone.utc)).total_seconds() / 3600
    assert 23 <= diff_hours <= 25, f"期望 ~24h，实际 {diff_hours:.2f}h"

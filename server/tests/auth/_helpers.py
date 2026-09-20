"""issue #204 用户管理系统测试共享辅助函数。

设计决策：
- 抽出注册/登录/get_token 等通用流程，避免 10 个测试文件各自重复样板代码（DRY）。
- 不使用 mock：走真实 ASGITransport + 真实 DB（tmp file），保证测试可信度。
- 所有 helper 都是 async，配合 pytest-asyncio 的 auto mode。
"""

from __future__ import annotations

from httpx import AsyncClient


async def register_user(
    client: AsyncClient,
    username: str = "alice",
    nickname: str = "Alice",
    password: str = "pass123",
) -> dict:
    """注册用户并返回响应 JSON。失败时返回响应 dict（含 status_code）。"""
    resp = await client.post(
        "/api/v1/auth/register",
        json={"username": username, "nickname": nickname, "password": password},
    )
    # 成功返回 201 + UserResponse；失败返回错误 JSON
    return resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {"_status": resp.status_code, "_text": resp.text}


async def register_user_status(
    client: AsyncClient,
    username: str = "alice",
    nickname: str = "Alice",
    password: str = "pass123",
):
    """注册用户并返回 (status_code, json)。供断言状态码的测试使用。"""
    resp = await client.post(
        "/api/v1/auth/register",
        json={"username": username, "nickname": nickname, "password": password},
    )
    try:
        body = resp.json()
    except Exception:
        body = {"_text": resp.text}
    return resp.status_code, body


async def login_and_get_token(
    client: AsyncClient,
    username: str = "alice",
    password: str = "pass123",
):
    """登录并返回 (status_code, token_or_none, user_or_none)。"""
    resp = await client.post(
        "/api/v1/auth/login",
        json={"username": username, "password": password},
    )
    if resp.status_code != 200:
        return resp.status_code, None, None
    data = resp.json()
    return 200, data["access_token"], data.get("user")


def auth_headers(token: str | None) -> dict[str, str]:
    """构造 Authorization: Bearer <token> 头；token 为 None 返回空 dict。"""
    return {"Authorization": f"Bearer {token}"} if token else {}


async def register_and_auth_headers(
    client: AsyncClient,
    username: str = "alice",
    nickname: str = "Alice",
    password: str = "pass123",
) -> dict[str, str]:
    """注册并登录测试用户，返回可直接复用的 Authorization 头。

    为什么需要：JWT 中间件对 POST/PUT/DELETE 强制认证（#204），
    而部分 api 测试仍按匿名写法调用；用本函数一行完成注册+登录，避免样板代码散落。
    """
    await register_user(client, username=username, nickname=nickname, password=password)
    status, token, _ = await login_and_get_token(client, username=username, password=password)
    assert status == 200 and token, f"测试用户登录失败: status={status}"
    return auth_headers(token)

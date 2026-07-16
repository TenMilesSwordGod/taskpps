"""JWT 认证中间件（重写）。

设计决策（spec「JWT 中间件」要求）：
- 白名单路径（/api/v1/auth/login, /api/v1/auth/register, /docs, /openapi.json, /redoc）直接放行。
- GET/HEAD/OPTIONS：尝试解析 JWT，始终放行：
  - 有效 token → request.state.user = 解码后的用户（含 role/username）
  - 无/无效 token → request.state.user = {"role": "guest"}
  - 始终放行（guest 可读 GET，降低试用门槛）
- POST/PUT/DELETE：强制校验 JWT：
  - 无/无效 token → 401
  - 有效 token → request.state.user = 解码用户，放行
- 非 /api/ 路径（静态文件、SPA fallback）直接放行，不解析 token。
- WebSocket /ws/agent 保持开放（评论4：Agent 不认证，与 user 体系解耦）。
"""

from __future__ import annotations

import logging

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from taskpps.auth.security import decode_token

logger = logging.getLogger("taskpps.auth")

# 白名单路径：无需 JWT 即可访问（登录/注册/文档）
# 注意：/docs 和 /openapi.json 不在 /api/ 下，会被前置的非 /api/ 跳过逻辑放行，
# 此处列出仅为显式声明，便于后续扩展（如 /api/v1/auth/refresh）
_WHITELIST_PATHS = {
    "/api/v1/auth/login",
    "/api/v1/auth/register",
    "/docs",
    "/openapi.json",
    "/redoc",
}

# guest 用户态（中间件设置，路由可通过 request.state.user 读取）
_GUEST_USER = {"role": "guest"}

# WebSocket 路径前缀：保持开放（评论4：Agent 不认证）
_WS_PREFIX = "/api/ws/"


class JWTAuthMiddleware(BaseHTTPMiddleware):
    """JWT 认证中间件。

    替代原 APIKeyMiddleware，实现 spec 要求的 RBAC 中间件级控制：
    - GET/HEAD/OPTIONS 放行（guest 可读）
    - POST/PUT/DELETE 强制 JWT（未登录 401）
    - 白名单路径免鉴权（登录/注册/文档）
    """

    async def dispatch(self, request: Request, call_next):  # type: ignore[no-untyped-def]
        path = request.url.path
        method = request.method.upper()

        # 1. 非 /api/ 路径（静态文件、SPA fallback）直接放行
        if not path.startswith("/api/"):
            return await call_next(request)

        # 2. WebSocket 路径保持开放（评论4：Agent 不认证）
        if path.startswith(_WS_PREFIX):
            return await call_next(request)

        # 3. 白名单路径：设置 guest 态并放行（登录/注册不需要 token）
        if path in _WHITELIST_PATHS:
            request.state.user = _GUEST_USER
            return await call_next(request)

        # 4. 提取 Authorization: Bearer <token>
        token = self._extract_token(request)

        # 5. GET/HEAD/OPTIONS：尝试解析 JWT，始终放行
        if method in ("GET", "HEAD", "OPTIONS"):
            request.state.user = self._decode_user(token) or _GUEST_USER
            return await call_next(request)

        # 6. POST/PUT/DELETE/PATCH：强制校验 JWT
        user = self._decode_user(token)
        if user is None:
            # 无/无效 token → 401
            return JSONResponse(
                status_code=401,
                content={"detail": "未登录或 token 无效", "path": path},
            )

        request.state.user = user
        return await call_next(request)

    @staticmethod
    def _extract_token(request: Request) -> str | None:
        """从 Authorization 头提取 Bearer token。

        支持 "Bearer <token>" 格式，不匹配返回 None。
        """
        auth_header = request.headers.get("Authorization")
        if not auth_header:
            return None
        parts = auth_header.split(" ", 1)
        if len(parts) != 2 or parts[0].lower() != "bearer":
            return None
        token = parts[1].strip()
        return token if token else None

    @staticmethod
    def _decode_user(token: str | None) -> dict | None:
        """解码 JWT token 为用户态 dict。

        返回 None 表示无 token 或 token 无效/过期。
        有效 token 返回 {"sub": username, "role": ..., "exp": ..., "iat": ...}。
        """
        if not token:
            return None
        return decode_token(token)

from __future__ import annotations

import logging

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware

from taskpps.config import get_settings

logger = logging.getLogger("taskpps")


class APIKeyMiddleware(BaseHTTPMiddleware):
    """API Key 认证中间件（已废弃强制执行，仅保留日志提示）。

    当 server.api_key 已配置时，记录一条警告但不再拒绝请求。
    如需恢复强制认证，取消下方注释即可。
    """

    async def dispatch(self, request: Request, call_next):
        # 静态文件（/、/assets/*、/favicon.ico 等）无需认证
        if not request.url.path.startswith("/api/"):
            return await call_next(request)

        settings = get_settings()
        api_key = settings.server.api_key

        if api_key is None:
            return await call_next(request)

        # 已废弃: 不再强制校验 X-API-Key
        # 仅首次访问时输出警告，提醒用户 api_key 配置已无效
        if not getattr(APIKeyMiddleware, "_warned", False):
            APIKeyMiddleware._warned = True
            logger.warning(
                "server.api_key 认证已废弃，所有 API 请求放行。"
                "请从 taskpps.yaml 中移除 server.api_key 配置。"
            )

        return await call_next(request)

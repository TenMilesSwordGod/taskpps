from __future__ import annotations

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from taskpps.config import get_settings
from taskpps.i18n import t


class APIKeyMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        settings = get_settings()
        api_key = settings.server.api_key

        if api_key is None:
            return await call_next(request)

        if request.url.path == "/api/health":
            return await call_next(request)

        if request.url.path.startswith("/api/ws/"):
            return await call_next(request)

        if request.method == "OPTIONS":
            return await call_next(request)

        provided = request.headers.get("X-API-Key")
        if provided != api_key:
            return JSONResponse(status_code=401, content={"detail": t("Invalid or missing API key")})

        return await call_next(request)

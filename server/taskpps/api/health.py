from fastapi import APIRouter

from taskpps.config import get_settings
from taskpps.version import __version__

router = APIRouter(tags=["health"])


@router.get("/health")
async def health_check():
    settings = get_settings()
    return {
        "status": "ok",
        "version": __version__,
        "host": settings.server.host,
        "port": settings.server.port,
    }

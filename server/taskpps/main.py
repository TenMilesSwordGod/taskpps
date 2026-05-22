from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from taskpps.api import health, runs, triggers
from taskpps.config import get_settings, load_settings
from taskpps.db.engine import init_db, close_db, get_engine, reset_engine
from taskpps.i18n import t, set_locale
from taskpps.middleware.auth import APIKeyMiddleware
from taskpps.services.plugin_manager import PluginManager


_plugin_manager: PluginManager | None = None
_external_engine = False


def mark_external_engine():
    global _external_engine
    _external_engine = True


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _plugin_manager
    settings = get_settings()
    if settings is None:
        load_settings()
        settings = get_settings()
    set_locale(settings.locale)
    await init_db()

    _plugin_manager = PluginManager()
    _plugin_manager.discover_plugins()
    _plugin_manager.start_triggers()

    yield

    if _plugin_manager:
        _plugin_manager.stop_all()
    if not _external_engine:
        await close_db()


app = FastAPI(title=t("Taskpps API"), version="0.1.0", lifespan=lifespan)

app.add_middleware(APIKeyMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router, prefix="/api")
app.include_router(runs.router, prefix="/api")
app.include_router(triggers.router, prefix="/api")


def cli():
    load_settings()
    settings = get_settings()
    uvicorn.run(
        "taskpps.main:app",
        host=settings.server.host,
        port=settings.server.port,
        reload=False,
    )

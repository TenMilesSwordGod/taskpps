import logging
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from taskpps.api import agents, health, runs, triggers, ws_agent
from taskpps.config import get_project_workdir, get_server_home, get_settings, load_settings
from taskpps.db.engine import close_db, init_db
from taskpps.i18n import set_locale, t
from taskpps.middleware.auth import APIKeyMiddleware
from taskpps.services.plugin_manager import PluginManager
from taskpps.version import __version__

logger = logging.getLogger("taskpps")

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
    logger.info("Project workdir: %s", get_project_workdir())
    logger.info("Server home: %s", get_server_home())
    if settings.server.api_key is None:
        logger.warning("No API key configured — all API endpoints are accessible without authentication")
    await init_db()

    _plugin_manager = PluginManager()
    _plugin_manager.discover_plugins()
    _plugin_manager.start_triggers()

    yield

    # Gracefully shutdown active pipeline runners
    from taskpps.engine.runner import _active_runs

    if _active_runs:
        logger.info(f"Gracefully shutting down {len(_active_runs)} active pipeline runners")
        for runner in _active_runs.values():
            await runner.cancel()
    if _plugin_manager:
        _plugin_manager.stop_all()
    from taskpps.services.agent_manager import AgentManager
    await AgentManager.instance().stop()
    if not _external_engine:
        await close_db()


app = FastAPI(title=t("Taskpps API"), version=__version__, lifespan=lifespan)

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
app.include_router(agents.router, prefix="/api")
app.include_router(ws_agent.router, prefix="/api")


def cli():
    load_settings()
    settings = get_settings()
    uvicorn.run(
        "taskpps.main:app",
        host=settings.server.host,
        port=settings.server.port,
        reload=False,
    )

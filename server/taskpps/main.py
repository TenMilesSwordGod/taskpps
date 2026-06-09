import logging
from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from taskpps.api import agents, health, pipelines, runs, triggers, ws_agent
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
app.include_router(pipelines.router, prefix="/api")
app.include_router(triggers.router, prefix="/api")
app.include_router(agents.router, prefix="/api")
app.include_router(ws_agent.router, prefix="/api")

# 挂载 Web UI 静态文件（生产模式）
# 从 SERVER_HOME/web/dist 或项目根目录的 web/dist 查找构建产物
_web_dist = Path(get_server_home()) / "web" / "dist"
if not _web_dist.is_dir():
    _web_dist = Path(__file__).resolve().parent.parent.parent / "web" / "dist"

if _web_dist.is_dir():
    # 静态资源（JS/CSS/图片等）
    app.mount("/assets", StaticFiles(directory=_web_dist / "assets"), name="web-assets")

    # SPA fallback：未匹配 /api/ 的 GET 请求回退到 index.html
    _index_html = _web_dist / "index.html"

    @app.get("/{full_path:path}")
    async def spa_fallback(full_path: str):
        """SPA 路由回退：所有非 /api/ 路径返回 index.html"""
        # 尝试匹配静态文件
        file_path = _web_dist / full_path
        if full_path and file_path.is_file():
            return FileResponse(file_path)
        # 回退到 index.html（SPA 路由）
        return FileResponse(_index_html)

    logger.info("Web UI mounted from %s", _web_dist)


def cli():
    load_settings()
    settings = get_settings()
    uvicorn.run(
        "taskpps.main:app",
        host=settings.server.host,
        port=settings.server.port,
        reload=False,
    )

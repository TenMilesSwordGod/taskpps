import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path

import uvicorn
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from taskpps.api import agents, artifacts, health, pipelines, plugins, projects, runs, triggers, ws_agent
from taskpps.config import get_project_workdir, get_server_home, get_settings, load_settings
from taskpps.db.engine import close_db, init_db
from taskpps.i18n import set_locale
from taskpps.logging_config import setup_logging
from taskpps.middleware.auth import APIKeyMiddleware
from taskpps.services.plugin_manager import PluginManager
from taskpps.version import __version__

logger = logging.getLogger("taskpps")

_plugin_manager: PluginManager | None = None
_external_engine = False


def mark_external_engine():
    global _external_engine
    _external_engine = True


async def _recover_stale_runs() -> None:
    """启动时将崩溃后卡在 RUNNING/PENDING 状态的 run 恢复为 FAILED。

    服务器崩溃时 PipelineRunner.run() 的 finally 块无法执行，
    数据库中的 run 状态会永远停留在 RUNNING。此函数在启动时扫描
    这些残留记录并重置为终态，防止幽灵运行阻塞任务槽。
    """
    from taskpps.db.engine import get_session_factory
    from taskpps.db.repository import RunRepository
    from taskpps.models.run import RunStatus, TaskStatus

    now = datetime.now(timezone.utc)
    async with get_session_factory()() as session:
        run_repo = RunRepository(session)

        # 直接按状态查询非终态 run，避免全表扫描
        stale_runs = await run_repo.list_runs_by_statuses([RunStatus.RUNNING, RunStatus.PENDING])

        if not stale_runs:
            return

        logger.warning("发现 %d 个停滞运行（状态为 RUNNING/PENDING），正在恢复为 FAILED", len(stale_runs))

        for run in stale_runs:
            # 将 run 状态重置为 FAILED
            await run_repo.update_run_status(
                run.id,
                RunStatus.FAILED,
                finished_at=now,
                error="服务器重启恢复：运行状态从 RUNNING/PENDING 重置为 FAILED",
            )

            # 批量将该 run 下 RUNNING/PENDING 的 task_runs 重置为 FAILED
            await run_repo.batch_update_stale_tasks(
                run.id, TaskStatus.FAILED,
                [TaskStatus.RUNNING, TaskStatus.PENDING],
                finished_at=now,
                error="服务器重启恢复：任务状态重置为 FAILED",
            )

            # 批量将该 run 下 RUNNING/PENDING 的 retry_records 重置为 FAILED
            await run_repo.batch_update_stale_retries(
                run.id, TaskStatus.FAILED,
                [TaskStatus.RUNNING, TaskStatus.PENDING],
                finished_at=now,
                error="服务器重启恢复：重试记录状态重置为 FAILED",
            )

        await session.commit()
        logger.info("已恢复 %d 个停滞运行", len(stale_runs))


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _plugin_manager

    setup_logging()

    settings = get_settings()
    if settings is None:
        load_settings()
        settings = get_settings()
    set_locale(settings.locale)

    # 在 lifespan 阶段用完整路径解析 server_home（含 settings.server_home）
    from taskpps.config import set_server_home

    if settings.server_home:
        set_server_home(Path(settings.server_home))

    logger.info("Project workdir: %s", get_project_workdir())
    logger.info("Server home: %s", get_server_home())
    if settings.server.api_key is None:
        logger.warning("No API key configured — all API endpoints are accessible without authentication")
    await init_db()
    await _recover_stale_runs()

    # Issue #106: 初始化全局并发信号量
    from taskpps.services.agent_manager import AgentManager

    global_max = settings.executor.global_max_concurrent
    if global_max > 0:
        AgentManager.instance().configure_global_max_concurrent(global_max)
        logger.info("Global max concurrent tasks: %d", global_max)

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


app = FastAPI(title="Taskpps API", version=__version__, lifespan=lifespan)

app.add_middleware(APIKeyMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.critical("Unhandled exception: %s %s", request.method, request.url.path, exc_info=True)
    logger.debug("Request details: headers=%s query=%s", dict(request.headers), dict(request.query_params))
    return JSONResponse(status_code=500, content={"detail": "Internal Server Error", "path": request.url.path})


app.include_router(health.router, prefix="/api")
app.include_router(runs.router, prefix="/api")
app.include_router(pipelines.router, prefix="/api")
app.include_router(triggers.router, prefix="/api")
app.include_router(agents.router, prefix="/api")
app.include_router(ws_agent.router, prefix="/api")
app.include_router(projects.router, prefix="/api")
app.include_router(artifacts.router, prefix="/api")
app.include_router(plugins.router, prefix="/api")

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
    setup_logging()
    load_settings()
    settings = get_settings()
    uvicorn.run(
        "taskpps.main:app",
        host=settings.server.host,
        port=settings.server.port,
        reload=False,
    )

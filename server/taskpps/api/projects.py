import logging
import os
from pathlib import Path

from fastapi import APIRouter, HTTPException

from taskpps.api.agents import invalidate_agents_cache
from taskpps.db.engine import get_session_factory
from taskpps.db.repository import ProjectRepository
from taskpps.schemas.project import CreateProjectRequest, ProjectResponse

logger = logging.getLogger("taskpps.api.projects")

router = APIRouter(prefix="/projects", tags=["projects"])


def _normalize_and_validate_workdir(workdir: str) -> str:
    """校验并规范化项目目录路径，返回服务端上的绝对路径。

    为什么严格校验：网页端允许手输服务端路径，若路径不存在/非目录，
    后续 pipelines/ 创建与扫描都会失败且难以排查；CLI 的 register-current-folder
    永远传已存在的当前目录，不受影响。
    """
    raw = (workdir or "").strip()
    if not raw:
        raise HTTPException(status_code=400, detail="workdir 不能为空")
    path = Path(os.path.expanduser(raw))
    if not path.is_absolute():
        raise HTTPException(status_code=400, detail="workdir 必须是绝对路径")
    if not path.is_dir():
        raise HTTPException(status_code=400, detail=f"workdir 不存在或不是目录: {path}")
    return str(path.resolve())


@router.post("/", status_code=201, response_model=ProjectResponse)
async def register_project(body: CreateProjectRequest):
    workdir = _normalize_and_validate_workdir(body.workdir)
    logger.debug("register_project: workdir=%s name=%s", workdir, body.name)
    try:
        # 先确保 pipelines/ 存在：项目注册后网页端立即可以新建/列出流水线
        (Path(workdir) / "pipelines").mkdir(parents=True, exist_ok=True)
        async with get_session_factory()() as session:
            repo = ProjectRepository(session)
            existing = await repo.get_project_by_workdir(workdir)
            if existing:
                logger.warning("Project already registered: workdir=%s id=%s", workdir, existing.id)
                raise HTTPException(status_code=409, detail=f"Project already registered with id={existing.id}")
            project = await repo.create_project(workdir=workdir, name=body.name)
            invalidate_agents_cache()
            logger.info("Project registered: id=%s workdir=%s", project.id, project.workdir)
            return project
    except HTTPException:
        raise
    except Exception:
        logger.error("register_project failed: workdir=%s name=%s", workdir, body.name, exc_info=True)
        raise HTTPException(status_code=500, detail="Internal Server Error") from None


@router.get("/", response_model=list[ProjectResponse])
async def list_projects():
    logger.debug("list_projects")
    try:
        async with get_session_factory()() as session:
            repo = ProjectRepository(session)
            projects = await repo.list_projects()
            logger.debug("list_projects: count=%d", len(projects))
            return projects
    except HTTPException:
        raise
    except Exception:
        logger.error("list_projects failed", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal Server Error") from None


@router.get("/{project_id}", response_model=ProjectResponse)
async def get_project(project_id: str):
    logger.debug("get_project: id=%s", project_id)
    try:
        async with get_session_factory()() as session:
            repo = ProjectRepository(session)
            project = await repo.get_project(project_id)
            if project is None:
                logger.debug("get_project: not found id=%s", project_id)
                raise HTTPException(status_code=404, detail="Project not found")
            return project
    except HTTPException:
        raise
    except Exception:
        logger.error("get_project failed: id=%s", project_id, exc_info=True)
        raise HTTPException(status_code=500, detail="Internal Server Error") from None


@router.delete("/{project_id}")
async def unregister_project(project_id: str):
    logger.debug("unregister_project: id=%s", project_id)
    try:
        async with get_session_factory()() as session:
            repo = ProjectRepository(session)
            success = await repo.delete_project(project_id)
            if not success:
                logger.debug("unregister_project: not found id=%s", project_id)
                raise HTTPException(status_code=404, detail="Project not found")
            invalidate_agents_cache()
            logger.info("Project unregistered: id=%s", project_id)
            return {"status": "unregistered"}
    except HTTPException:
        raise
    except Exception:
        logger.error("unregister_project failed: id=%s", project_id, exc_info=True)
        raise HTTPException(status_code=500, detail="Internal Server Error") from None

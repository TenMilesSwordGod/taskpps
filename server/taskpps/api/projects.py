import logging

from fastapi import APIRouter, HTTPException

from taskpps.db.engine import get_session_factory
from taskpps.db.repository import ProjectRepository
from taskpps.schemas.project import CreateProjectRequest, ProjectResponse

logger = logging.getLogger("taskpps.api.projects")

router = APIRouter(prefix="/projects", tags=["projects"])


@router.post("/", status_code=201, response_model=ProjectResponse)
async def register_project(body: CreateProjectRequest):
    logger.debug("register_project: workdir=%s name=%s", body.workdir, body.name)
    try:
        async with get_session_factory()() as session:
            repo = ProjectRepository(session)
            existing = await repo.get_project_by_workdir(body.workdir)
            if existing:
                logger.warning("Project already registered: workdir=%s id=%s", body.workdir, existing.id)
                raise HTTPException(status_code=409, detail=f"Project already registered with id={existing.id}")
            project = await repo.create_project(workdir=body.workdir, name=body.name)
            logger.info("Project registered: id=%s workdir=%s", project.id, project.workdir)
            return project
    except HTTPException:
        raise
    except Exception:
        logger.error("register_project failed: workdir=%s name=%s", body.workdir, body.name, exc_info=True)
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
            logger.info("Project unregistered: id=%s", project_id)
            return {"status": "unregistered"}
    except HTTPException:
        raise
    except Exception:
        logger.error("unregister_project failed: id=%s", project_id, exc_info=True)
        raise HTTPException(status_code=500, detail="Internal Server Error") from None

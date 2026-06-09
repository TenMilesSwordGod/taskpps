from fastapi import APIRouter, HTTPException

from taskpps.db.engine import get_session_factory
from taskpps.db.repository import ProjectRepository
from taskpps.schemas.project import CreateProjectRequest, ProjectResponse

router = APIRouter(prefix="/projects", tags=["projects"])


@router.post("/", status_code=201, response_model=ProjectResponse)
async def register_project(body: CreateProjectRequest):
    async with get_session_factory()() as session:
        repo = ProjectRepository(session)
        # 检查 workdir 是否已注册
        existing = await repo.get_project_by_workdir(body.workdir)
        if existing:
            raise HTTPException(status_code=409, detail=f"Project already registered with id={existing.id}")
        project = await repo.create_project(workdir=body.workdir, name=body.name)
        return project


@router.get("/", response_model=list[ProjectResponse])
async def list_projects():
    async with get_session_factory()() as session:
        repo = ProjectRepository(session)
        projects = await repo.list_projects()
        return projects


@router.get("/{project_id}", response_model=ProjectResponse)
async def get_project(project_id: str):
    async with get_session_factory()() as session:
        repo = ProjectRepository(session)
        project = await repo.get_project(project_id)
        if project is None:
            raise HTTPException(status_code=404, detail="Project not found")
        return project


@router.delete("/{project_id}")
async def unregister_project(project_id: str):
    async with get_session_factory()() as session:
        repo = ProjectRepository(session)
        success = await repo.delete_project(project_id)
        if not success:
            raise HTTPException(status_code=404, detail="Project not found")
        return {"status": "unregistered"}

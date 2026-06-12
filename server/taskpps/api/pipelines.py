from __future__ import annotations

import os
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query

from taskpps.config import get_pipelines_dir, get_project_workdir_by_id
from taskpps.db.engine import get_session_factory
from taskpps.db.repository import RunRepository
from taskpps.loaders.pipeline_loader import PipelineLoader

router = APIRouter(prefix="/pipelines", tags=["pipelines"])


@router.get("/")
async def list_pipelines(project_id: str | None = Query(None)):
    """列出已加载流水线摘要（按文件夹分组）

    支持 project_id 查询参数，指定后加载对应项目的 pipelines/ 目录。
    不指定 project_id 时，加载所有已注册项目的 pipelines，每条记录附 project_id。
    """
    # 确定要加载的项目列表（(project_id, base_dir) pairs）
    project_dirs: list[tuple[str | None, Path | None]] = []
    if project_id:
        project_workdir = get_project_workdir_by_id(project_id)
        if project_workdir:
            project_dirs.append((project_id, get_pipelines_dir(project_workdir)))
        else:
            raise HTTPException(status_code=404, detail=f"Project not found: {project_id}")
    else:
        # 加载所有已注册项目
        async with get_session_factory()() as session:
            from taskpps.db.repository import ProjectRepository

            repo = ProjectRepository(session)
            projects = await repo.list_projects()
            for proj in projects:
                project_dirs.append((proj.id, get_pipelines_dir(proj.workdir)))
        # 如果没有注册项目，回退到默认 loader
        if not project_dirs:
            project_dirs.append((None, None))

    items = []
    async with get_session_factory()() as session:
        run_repo = RunRepository(session)
        for pid, pdir in project_dirs:
            loader = PipelineLoader(base_dir=pdir)
            all_pipelines = loader.load_all_with_files()
            for file, spec in all_pipelines.items():
                task_count = 0
                subpipeline_count = len(spec.pipelines) if spec.pipelines else 0
                if spec.pipelines:
                    for sub in spec.pipelines:
                        task_count += len(sub.tasks)
                elif spec.tasks:
                    task_count = len(spec.tasks)

                runs = await run_repo.list_runs(pipeline_file=file, limit=1)
                last_run = None
                if runs:
                    r = runs[0]
                    last_run = {
                        "id": r.id,
                        "status": r.status,
                        "created_at": r.created_at.isoformat() if r.created_at else None,
                    }

                total_count = await run_repo.count_runs(pipeline_file=file)
                success_count = await run_repo.count_runs(pipeline_file=file, status="success")
                success_rate = round(success_count / total_count * 100) if total_count > 0 else 0

                folder = os.path.dirname(file)

                items.append(
                    {
                        "name": spec.name,
                        "file": file,
                        "folder": folder,
                        "project_id": pid,
                        "task_count": task_count,
                        "subpipeline_count": subpipeline_count,
                        "last_run": last_run,
                        "success_rate": success_rate,
                    }
                )

    return {"items": items}


@router.get("/{file:path}")
async def get_pipeline(file: str, project_id: str | None = Query(None)):
    """返回 YAML 解析后的完整 JSON"""
    if project_id:
        project_workdir = get_project_workdir_by_id(project_id)
        if project_workdir:
            loader = PipelineLoader(base_dir=get_pipelines_dir(project_workdir))
        else:
            raise HTTPException(status_code=404, detail=f"Project not found: {project_id}")
        try:
            spec = loader.load(file)
        except FileNotFoundError as e:
            raise HTTPException(status_code=404, detail=str(e)) from e
        except Exception as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
        return spec.model_dump()

    # 未指定 project_id 时，遍历所有已注册项目查找 pipeline
    async with get_session_factory()() as session:
        from taskpps.db.repository import ProjectRepository

        repo = ProjectRepository(session)
        projects = await repo.list_projects()

    for proj in projects:
        loader = PipelineLoader(base_dir=get_pipelines_dir(proj.workdir))
        try:
            spec = loader.load(file)
            return spec.model_dump()
        except FileNotFoundError:
            continue

    # 回退到默认目录
    loader = PipelineLoader()
    try:
        spec = loader.load(file)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    return spec.model_dump()

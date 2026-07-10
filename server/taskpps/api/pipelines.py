from __future__ import annotations

import os
from pathlib import Path

import yaml
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

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
    # 缓存 project_id -> project_name 映射
    project_name_map: dict[str | None, str | None] = {}
    if project_id:
        project_workdir = get_project_workdir_by_id(project_id)
        if project_workdir:
            project_dirs.append((project_id, get_pipelines_dir(project_workdir)))
            # 查询指定项目的名称
            async with get_session_factory()() as session:
                from taskpps.db.repository import ProjectRepository

                proj = await ProjectRepository(session).get_project(project_id)
                if proj:
                    pname = proj.name if proj.name else Path(proj.workdir).name
                    project_name_map[project_id] = pname or None
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
                # 解析项目名称：优先 name，否则用 workdir 最后一段路径
                pname = proj.name if proj.name else Path(proj.workdir).name
                project_name_map[proj.id] = pname or None
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

                # Issue #184: 取最近 10 次运行 + task_summary，供前端折线图使用
                recent_runs_data = await run_repo.list_runs(pipeline_file=file, limit=10)
                recent_run_ids = [r.id for r in recent_runs_data]
                recent_summaries = await run_repo.get_task_summaries(recent_run_ids) if recent_run_ids else {}
                # recent_runs 按时间倒序（最近在前），前端折线图需反转
                recent_runs = [{"task_summary": recent_summaries.get(r.id, {})} for r in recent_runs_data]

                last_run = None
                if recent_runs_data:
                    r = recent_runs_data[0]
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
                        "project_name": project_name_map.get(pid),
                        "task_count": task_count,
                        "subpipeline_count": subpipeline_count,
                        "last_run": last_run,
                        "success_rate": success_rate,
                        "recent_runs": recent_runs,
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


class SavePipelineRequest(BaseModel):
    content: str


@router.put("/{file:path}")
async def save_pipeline(file: str, body: SavePipelineRequest, project_id: str | None = Query(None)):
    """保存 pipeline YAML 内容到文件"""
    if project_id:
        project_workdir = get_project_workdir_by_id(project_id)
        if not project_workdir:
            raise HTTPException(status_code=404, detail=f"Project not found: {project_id}")
        pipelines_dir = get_pipelines_dir(project_workdir)
    else:
        pipelines_dir = get_pipelines_dir()

    file_path = (pipelines_dir / file).resolve()
    # 安全检查：路径不能逃逸出 pipelines 目录
    if not str(file_path).startswith(str(pipelines_dir.resolve())):
        raise HTTPException(status_code=400, detail="Invalid file path")

    # 验证 YAML 格式合法
    try:
        yaml.safe_load(body.content)
    except yaml.YAMLError as e:
        raise HTTPException(status_code=400, detail=f"Invalid YAML: {e}") from e

    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text(body.content, encoding="utf-8")
    return {"status": "ok", "file": file}

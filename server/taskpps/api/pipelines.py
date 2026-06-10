import os

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
    """
    base_dir = None
    if project_id:
        project_workdir = get_project_workdir_by_id(project_id)
        if project_workdir:
            base_dir = get_pipelines_dir(project_workdir)
        else:
            raise HTTPException(status_code=404, detail=f"Project not found: {project_id}")

    loader = PipelineLoader(base_dir=base_dir)
    all_pipelines = loader.load_all_with_files()

    items = []
    async with get_session_factory()() as session:
        run_repo = RunRepository(session)
        for file, spec in all_pipelines.items():
            # 计算任务数和子流水线数
            task_count = 0
            subpipeline_count = len(spec.pipelines) if spec.pipelines else 0
            if spec.pipelines:
                for sub in spec.pipelines:
                    task_count += len(sub.tasks)
            elif spec.tasks:
                task_count = len(spec.tasks)

            # 查询最近运行
            runs = await run_repo.list_runs(pipeline=spec.name, limit=1)
            last_run = None
            if runs:
                r = runs[0]
                last_run = {
                    "id": r.id,
                    "status": r.status,
                    "created_at": r.created_at.isoformat() if r.created_at else None,
                }

            # 计算成功率
            total_count = await run_repo.count_runs(pipeline=spec.name)
            success_count = await run_repo.count_runs(pipeline=spec.name, status="success")
            success_rate = round(success_count / total_count * 100) if total_count > 0 else 0

            # 文件夹分组（debug/debug.yaml → folder="debug"）
            folder = os.path.dirname(file)

            items.append(
                {
                    "name": spec.name,
                    "file": file,
                    "folder": folder,
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
    base_dir = None
    if project_id:
        project_workdir = get_project_workdir_by_id(project_id)
        if project_workdir:
            base_dir = get_pipelines_dir(project_workdir)
        else:
            raise HTTPException(status_code=404, detail=f"Project not found: {project_id}")

    loader = PipelineLoader(base_dir=base_dir)
    try:
        spec = loader.load(file)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    return spec.model_dump()

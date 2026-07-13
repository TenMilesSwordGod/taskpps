from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import yaml
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from taskpps.config import get_pipelines_dir, get_project_workdir_by_id
from taskpps.db.engine import get_session_factory
from taskpps.db.repository import PipelineDefinitionRepository, RunRepository
from taskpps.loaders.pipeline_loader import PipelineLoader

router = APIRouter(prefix="/pipelines", tags=["pipelines"])


async def _sync_pipeline_definitions(
    project_id: str, base_dir: Path, loader: PipelineLoader
) -> dict[str, str]:
    """同步 pipeline_definitions 表与文件系统，返回 {file_path: definition_id}"""
    from taskpps.db.engine import get_session_factory as _gsf

    definitions: dict[str, str] = {}
    active_paths: set[str] = set()

    async with _gsf()() as session:
        repo = PipelineDefinitionRepository(session)
        for path in sorted(base_dir.glob("**/*.yaml")):
            try:
                rel = str(path.relative_to(base_dir))
            except ValueError:
                continue
            try:
                raw = path.read_text(encoding="utf-8")
                file_hash = hashlib.sha256(raw.encode()).hexdigest()[:8]
                data = yaml.safe_load(raw)
                if data is None:
                    continue
                spec = loader.parse_dict(data)
                content = json.dumps(spec.model_dump(), ensure_ascii=False)
                name = data.get("name", "")
                definition, _ = await repo.upsert(
                    project_id=project_id,
                    file_path=rel,
                    name=name,
                    content=content,
                    raw_content=raw,
                    file_hash=file_hash,
                )
                definitions[rel] = definition.id
                active_paths.add(rel)
            except Exception:
                continue
        for path in sorted(base_dir.glob("**/*.yml")):
            try:
                rel = str(path.relative_to(base_dir))
            except ValueError:
                continue
            try:
                raw = path.read_text(encoding="utf-8")
                file_hash = hashlib.sha256(raw.encode()).hexdigest()[:8]
                data = yaml.safe_load(raw)
                if data is None:
                    continue
                spec = loader.parse_dict(data)
                content = json.dumps(spec.model_dump(), ensure_ascii=False)
                name = data.get("name", "")
                definition, _ = await repo.upsert(
                    project_id=project_id,
                    file_path=rel,
                    name=name,
                    content=content,
                    raw_content=raw,
                    file_hash=file_hash,
                )
                definitions[rel] = definition.id
                active_paths.add(rel)
            except Exception:
                continue
        await repo.deactivate_others(project_id, active_paths)
    return definitions


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

            definitions: dict[str, str] = {}
            # Phase 2 (2026-07): fallback 路径（无注册项目）也需同步 definition，
            # 否则列表 API 返回的 item.id 为空，前端通过 UUID 路由无法访问详情
            if pid is not None and pdir is not None:
                definitions = await _sync_pipeline_definitions(pid, pdir, loader)
            elif pdir is None and pid is None and all_pipelines:
                # 无注册项目时使用默认 pipelines/ 目录，以 workdir 最后一段作 project_id
                definitions = await _sync_pipeline_definitions("__default__", get_pipelines_dir(), loader)

            for file, spec in all_pipelines.items():
                task_count = 0
                subpipeline_count = len(spec.pipelines) if spec.pipelines else 0
                if spec.pipelines:
                    for sub in spec.pipelines:
                        task_count += len(sub.tasks)
                elif spec.tasks:
                    task_count = len(spec.tasks)

                # Phase 2 (2026-07): 用 definition_id 定位 run 历史
                # 列表API已通过 _sync_pipeline_definitions 确保每个pipeline都有UUID
                # 不存在 definition_id 的 pipeline 不会出现在列表中
                def_id = definitions.get(file, "")
                recent_runs_data = await run_repo.list_runs(definition_id=def_id, limit=10) if def_id else []
                recent_run_ids = [r.id for r in recent_runs_data]
                recent_summaries = await run_repo.get_task_summaries(recent_run_ids) if recent_run_ids else {}
                recent_runs = [{"task_summary": recent_summaries.get(r.id, {})} for r in recent_runs_data]

                last_run = None
                if recent_runs_data:
                    r = recent_runs_data[0]
                    last_run = {
                        "id": r.id,
                        "status": r.status,
                        "created_at": r.created_at.isoformat() if r.created_at else None,
                    }

                total_count = await run_repo.count_runs(definition_id=def_id) if def_id else 0
                success_count = await run_repo.count_runs(definition_id=def_id, status="success") if def_id else 0
                success_rate = round(success_count / total_count * 100) if total_count > 0 else 0

                folder = os.path.dirname(file)

                items.append(
                    {
                        "id": definitions.get(file, ""),
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


@router.get("/by-id/{definition_id}")
async def get_pipeline_by_id(definition_id: str, project_id: str | None = Query(None)):
    """通过 definition_id 返回流水线完整 JSON"""
    async with get_session_factory()() as session:
        repo = PipelineDefinitionRepository(session)
        d = await repo.get(definition_id)
        if d is None:
            raise HTTPException(status_code=404, detail=f"Definition not found: {definition_id}")
        if project_id and d.project_id != project_id:
            raise HTTPException(status_code=404, detail="Definition not found in project")
        return json.loads(d.content)


class SavePipelineByIdRequest(BaseModel):
    content: str


@router.put("/by-id/{definition_id}")
async def save_pipeline_by_id(definition_id: str, body: SavePipelineByIdRequest):
    """保存 pipeline YAML：查定义→定位文件→写磁盘→同步DB"""
    async with get_session_factory()() as session:
        repo = PipelineDefinitionRepository(session)
        d = await repo.get(definition_id)
        if d is None:
            raise HTTPException(status_code=404, detail=f"Definition not found: {definition_id}")

    project_workdir = get_project_workdir_by_id(d.project_id)
    if not project_workdir:
        raise HTTPException(status_code=404, detail=f"Project not found: {d.project_id}")
    pipelines_dir = get_pipelines_dir(project_workdir)
    file_path = (pipelines_dir / d.file_path).resolve()

    if not str(file_path).startswith(str(pipelines_dir.resolve())):
        raise HTTPException(status_code=400, detail="Invalid file path")

    import yaml as _yaml
    try:
        _yaml.safe_load(body.content)
    except _yaml.YAMLError as e:
        raise HTTPException(status_code=400, detail=f"Invalid YAML: {e}") from e

    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text(body.content, encoding="utf-8")

    file_hash_val = hashlib.sha256(body.content.encode()).hexdigest()[:8]
    data = _yaml.safe_load(body.content)
    if data is not None:
        loader = PipelineLoader(base_dir=pipelines_dir)
        spec = loader.parse_dict(data)
        content_json = json.dumps(spec.model_dump(), ensure_ascii=False)
        name = data.get("name", "")
        async with get_session_factory()() as session:
            repo = PipelineDefinitionRepository(session)
            await repo.upsert(
                project_id=d.project_id, file_path=d.file_path,
                name=name, content=content_json, raw_content=body.content, file_hash=file_hash_val,
            )

    return {"status": "ok", "definition_id": definition_id, "file_path": d.file_path}

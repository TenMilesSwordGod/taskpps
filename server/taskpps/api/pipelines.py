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
            if pid is not None and pdir is not None:
                definitions = await _sync_pipeline_definitions(pid, pdir, loader)

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


@router.get("/{file:path}")
async def get_pipeline(file: str, project_id: str | None = Query(None), definition_id: str | None = Query(None)):
    """返回 YAML 解析后的完整 JSON

    支持 definition_id 参数，指定后返回 pipeline_definitions 中缓存的 content。
    """
    if definition_id:
        async with get_session_factory()() as session:
            repo = PipelineDefinitionRepository(session)
            d = await repo.get(definition_id)
            if d is None:
                raise HTTPException(status_code=404, detail=f"Definition not found: {definition_id}")
            return json.loads(d.content)

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
    """保存 pipeline YAML 内容到文件，并同步 pipeline_definitions 表"""
    if project_id:
        project_workdir = get_project_workdir_by_id(project_id)
        if not project_workdir:
            raise HTTPException(status_code=404, detail=f"Project not found: {project_id}")
        pipelines_dir = get_pipelines_dir(project_workdir)
    else:
        # 与 GET 一致的逻辑: 遍历所有已注册项目，找到第一个匹配的
        async with get_session_factory()() as session:
            from taskpps.db.repository import ProjectRepository

            repo = ProjectRepository(session)
            projects = await repo.list_projects()

        project_workdir = None
        pipelines_dir = None
        for proj in projects:
            project_pipelines = get_pipelines_dir(proj.workdir)
            if (project_pipelines / file).resolve().exists():
                pipelines_dir = project_pipelines
                project_workdir = proj.workdir
                project_id = proj.id
                break

        if pipelines_dir is None:
            pipelines_dir = get_pipelines_dir()
            project_workdir = None
            project_id = None

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

    # 同步 pipeline_definitions 表
    if project_id is not None:
        file_hash = hashlib.sha256(body.content.encode()).hexdigest()[:8]
        data = yaml.safe_load(body.content)
        if data is not None:
            loader = PipelineLoader(base_dir=pipelines_dir)
            spec = loader.parse_dict(data)
            content = json.dumps(spec.model_dump(), ensure_ascii=False)
            name = data.get("name", "")
            try:
                rel = str(Path(file).relative_to(pipelines_dir.resolve()))
            except ValueError:
                rel = file
            async with get_session_factory()() as session:
                repo = PipelineDefinitionRepository(session)
                await repo.upsert(
                    project_id=project_id,
                    file_path=rel,
                    name=name,
                    content=content,
                    raw_content=body.content,
                    file_hash=file_hash,
                )

    return {"status": "ok", "file": file}

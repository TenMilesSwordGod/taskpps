from __future__ import annotations

import hashlib
import json
import os
import shutil
from pathlib import Path

import yaml
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from taskpps.config import get_pipelines_dir, get_project_workdir_by_id
from taskpps.db.engine import get_session_factory
from taskpps.db.repository import PipelineDefinitionRepository, RunRepository
from taskpps.loaders.pipeline_loader import PipelineLoader

router = APIRouter(prefix="/pipelines", tags=["pipelines"])


def _get_project_pipelines_dir(project_id: str) -> Path:
    """解析项目 pipelines 根目录；项目未注册统一抛 404，避免各端点重复判断。"""
    project_workdir = get_project_workdir_by_id(project_id)
    if not project_workdir:
        raise HTTPException(status_code=404, detail=f"Project not found: {project_id}")
    return get_pipelines_dir(project_workdir)


def _resolve_under(base_dir: Path, rel_path: str, label: str) -> Path:
    """把用户输入的相对路径安全解析到 base_dir 下（允许目标尚不存在）。

    为什么这么写：新建场景目标不存在，无法用 exists() 校验；先 resolve 再判断
    base_dir 是否为父级，可同时拦截绝对路径、`..` 穿越以及符号链接逃逸。
    """
    raw = (rel_path or "").strip().replace("\\", "/")
    if not raw:
        raise HTTPException(status_code=400, detail=f"{label} 不能为空")
    if Path(raw).is_absolute():
        raise HTTPException(status_code=400, detail=f"{label} 必须是相对路径")
    base_resolved = base_dir.resolve()
    resolved = (base_dir / raw).resolve()
    if base_resolved not in resolved.parents:
        raise HTTPException(status_code=400, detail=f"Invalid {label} path")
    return resolved


def _relative_path_str(base_dir: Path, resolved: Path) -> str:
    """返回相对 pipelines 目录的路径字符串，与 _sync_pipeline_definitions 的存储格式一致。"""
    return str(resolved.relative_to(base_dir.resolve()))


def _validate_yaml_suffix(path: Path) -> None:
    if path.suffix.lower() not in (".yaml", ".yml"):
        raise HTTPException(status_code=400, detail="流水线文件必须以 .yaml 或 .yml 结尾")


async def _write_pipeline_content(
    project_id: str, pipelines_dir: Path, file_path: Path, rel_path: str, content: str
) -> str | None:
    """写流水线 YAML 到磁盘并尽力同步 DB，返回 definition_id（结构非法时为 None）。

    为什么结构非法也允许写盘：沿用 by-file 保存的既有设计——用户可先保存半成品，
    待 YAML 结构修好后再次保存自动入库；仅语法错误（无法解析）才拒绝。
    """
    try:
        yaml.safe_load(content)
    except yaml.YAMLError as e:
        raise HTTPException(status_code=400, detail=f"Invalid YAML syntax: {e}") from e

    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text(content, encoding="utf-8")

    file_hash_val = hashlib.sha256(content.encode()).hexdigest()[:8]
    data = yaml.safe_load(content)

    definition_id: str | None = None
    if data is not None:
        try:
            loader = PipelineLoader(base_dir=pipelines_dir)
            spec = loader.parse_dict(data)
            content_json = json.dumps(spec.model_dump(), ensure_ascii=False)
            name = data.get("name", file_path.stem)
            async with get_session_factory()() as session:
                repo = PipelineDefinitionRepository(session)
                definition, _ = await repo.upsert(
                    project_id=project_id, file_path=rel_path,
                    name=name, content=content_json, raw_content=content, file_hash=file_hash_val,
                )
            definition_id = definition.id
        except Exception:
            # pydantic 校验失败：只写磁盘，不同步 DB；下次合法保存时自动同步
            pass
    return definition_id


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
    # v3 (2026-09): 新增 folders — 空文件夹无法从 YAML 文件路径推导，需扫描真实目录
    folders: list[dict] = []
    async with get_session_factory()() as session:
        run_repo = RunRepository(session)
        for pid, pdir in project_dirs:
            loader = PipelineLoader(base_dir=pdir)
            all_pipelines, invalid_pipelines = loader.load_all_with_files_and_errors()

            definitions: dict[str, str] = {}
            if pid is not None and pdir is not None:
                definitions = await _sync_pipeline_definitions(pid, pdir, loader)

                # 扫描真实子目录（跳过隐藏目录），让刚创建但尚无 YAML 的文件夹也能展示
                if pdir.is_dir():
                    for root, dirs, _files in os.walk(pdir):
                        dirs[:] = [d for d in dirs if not d.startswith(".")]
                        rel_root = Path(root).relative_to(pdir)
                        if rel_root == Path("."):
                            continue
                        folders.append(
                            {
                                "project_id": pid,
                                "folder": rel_root.as_posix(),
                                # 空文件夹所在项目可能没有任何流水线，前端需要项目名做分组标题
                                "project_name": project_name_map.get(pid),
                            }
                        )

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
                last_operator = None
                if recent_runs_data:
                    r = recent_runs_data[0]
                    last_run = {
                        "id": r.id,
                        "status": r.status,
                        "created_at": r.created_at.isoformat() if r.created_at else None,
                    }
                    # 最近一次运行的触发人（username），用于「最后操作人」展示
                    last_operator = getattr(r, "operator", None)

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
                        "last_operator": last_operator,
                        "success_rate": success_rate,
                        "recent_runs": recent_runs,
                        # v1 (2026-07): issue #195 — 合法 pipeline 的校验字段
                        "valid": True,
                        "validation_error": None,
                    }
                )

            # v1 (2026-07): issue #195 — 将非法 pipeline 也纳入返回列表
            # 非法项无 DB 记录、无运行历史，仅展示文件+校验错误
            # v2 (2026-07): 增加 raw_content 字段，让前端能拿到原始 YAML 填入编辑器
            for inv in invalid_pipelines:
                inv_file = inv["file"]
                inv_folder = os.path.dirname(inv_file)
                items.append(
                    {
                        "id": "",
                        "name": inv.get("name", inv_file),
                        "file": inv_file,
                        "folder": inv_folder,
                        "project_id": pid,
                        "project_name": project_name_map.get(pid),
                        "task_count": 0,
                        "subpipeline_count": 0,
                        "last_run": None,
                        "success_rate": 0,
                        "recent_runs": [],
                        "valid": False,
                        "validation_error": inv.get("validation_error"),
                        "raw_content": inv.get("raw_content", ""),
                    }
                )

    # 批量解析「最后操作人」昵称（避免 N+1 查询）：一次查 users 表做 username→nickname 映射
    operators = {it.get("last_operator") for it in items} - {None}
    operator_nickname_map: dict[str, str] = {}
    if operators:
        from taskpps.services.pipeline_service import _resolve_operator_nicknames

        async with get_session_factory()() as session:
            operator_nickname_map = await _resolve_operator_nicknames(session, operators)
    for it in items:
        op = it.get("last_operator")
        it["last_operator_nickname"] = operator_nickname_map.get(op) if op else None

    return {"items": items, "folders": folders}


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


# v2 (2026-07): issue #195 补充 — 按文件路径读/写 pipeline YAML
# 非法 pipeline 无 definition_id，无法用 /by-id/{id} 加载
# 新增 /by-file 端点通过 file 查询参数定位文件，支持读取原始 YAML 和保存

class PipelineByFileResponse(BaseModel):
    name: str
    file: str
    raw_content: str


class SavePipelineByFileRequest(BaseModel):
    file: str
    content: str


@router.get("/by-file/{project_id}", response_model=PipelineByFileResponse)
async def get_pipeline_by_file(project_id: str, file: str = Query(..., description="相对 pipelines 目录的文件路径")):
    """通过文件路径读取原始 YAML 内容，用于非法 pipeline 的编辑器加载"""
    pipelines_dir = _get_project_pipelines_dir(project_id)
    file_path = _resolve_under(pipelines_dir, file, "file")

    if not file_path.exists():
        raise HTTPException(status_code=404, detail=f"File not found: {file}")

    raw_content = file_path.read_text(encoding="utf-8")
    data = yaml.safe_load(raw_content)
    name = data.get("name", file_path.stem) if isinstance(data, dict) else file_path.stem

    return PipelineByFileResponse(name=name, file=file, raw_content=raw_content)


@router.put("/by-file/{project_id}")
async def save_pipeline_by_file(project_id: str, body: SavePipelineByFileRequest):
    """通过文件路径保存 pipeline YAML（已存在则覆盖）：写磁盘 + 同步 DB"""
    pipelines_dir = _get_project_pipelines_dir(project_id)
    file_path = _resolve_under(pipelines_dir, body.file, "file")
    _validate_yaml_suffix(file_path)
    rel_path = _relative_path_str(pipelines_dir, file_path)
    definition_id = await _write_pipeline_content(
        project_id, pipelines_dir, file_path, rel_path, body.content
    )

    return {
        "status": "ok",
        "file": rel_path,
        "definition_id": definition_id,
    }


# v3 (2026-09): 网页端新建/重命名/删除流水线与文件夹
# 设计决策：与 PUT /by-file 同路径，POST=新建（409 防覆盖）、PATCH=重命名、DELETE=删除；
# 删除定义用软删除保留运行历史；文件夹操作用独立 /folders 子资源。

class RenamePipelineRequest(BaseModel):
    file: str
    new_file: str


@router.post("/by-file/{project_id}", status_code=201)
async def create_pipeline_by_file(project_id: str, body: SavePipelineByFileRequest):
    """新建流水线 YAML；文件已存在返回 409，避免网页端误覆盖已有流水线。"""
    pipelines_dir = _get_project_pipelines_dir(project_id)
    file_path = _resolve_under(pipelines_dir, body.file, "file")
    _validate_yaml_suffix(file_path)
    if file_path.exists():
        raise HTTPException(status_code=409, detail=f"流水线文件已存在: {body.file}")
    rel_path = _relative_path_str(pipelines_dir, file_path)
    definition_id = await _write_pipeline_content(
        project_id, pipelines_dir, file_path, rel_path, body.content
    )
    return {"status": "ok", "file": rel_path, "definition_id": definition_id}


@router.patch("/by-file/{project_id}")
async def rename_pipeline_by_file(project_id: str, body: RenamePipelineRequest):
    """重命名/移动流水线文件，并原地更新 DB 定义路径（保留 definition_id 与运行历史）。"""
    pipelines_dir = _get_project_pipelines_dir(project_id)
    old_path = _resolve_under(pipelines_dir, body.file, "file")
    _validate_yaml_suffix(old_path)
    if not old_path.is_file():
        raise HTTPException(status_code=404, detail=f"File not found: {body.file}")
    new_path = _resolve_under(pipelines_dir, body.new_file, "new_file")
    _validate_yaml_suffix(new_path)
    if new_path == old_path:
        raise HTTPException(status_code=400, detail="新文件名与原文件名相同")
    if new_path.exists():
        raise HTTPException(status_code=409, detail=f"流水线文件已存在: {body.new_file}")

    old_rel = _relative_path_str(pipelines_dir, old_path)
    new_rel = _relative_path_str(pipelines_dir, new_path)
    new_path.parent.mkdir(parents=True, exist_ok=True)
    os.rename(old_path, new_path)

    async with get_session_factory()() as session:
        repo = PipelineDefinitionRepository(session)
        updated = await repo.rename_file_path(project_id, old_rel, new_rel)
    return {"status": "ok", "file": new_rel, "definition_id_updated": updated}


@router.delete("/by-file/{project_id}")
async def delete_pipeline_by_file(
    project_id: str, file: str = Query(..., description="相对 pipelines 目录的文件路径")
):
    """删除流水线文件，并软删除 DB 定义（保留历史运行记录）。"""
    pipelines_dir = _get_project_pipelines_dir(project_id)
    file_path = _resolve_under(pipelines_dir, file, "file")
    _validate_yaml_suffix(file_path)
    if not file_path.is_file():
        raise HTTPException(status_code=404, detail=f"File not found: {file}")

    rel_path = _relative_path_str(pipelines_dir, file_path)
    file_path.unlink()
    async with get_session_factory()() as session:
        repo = PipelineDefinitionRepository(session)
        await repo.deactivate_file(project_id, rel_path)
    return {"status": "deleted", "file": rel_path}


class CreateFolderRequest(BaseModel):
    folder: str


class RenameFolderRequest(BaseModel):
    folder: str
    new_folder: str


def _resolve_folder_path(pipelines_dir: Path, folder: str, label: str = "folder") -> Path:
    """文件夹路径解析：必须严格位于 pipelines 目录之下（不能是根目录本身）。"""
    resolved = _resolve_under(pipelines_dir, folder, label)
    if resolved == pipelines_dir.resolve():
        raise HTTPException(status_code=400, detail=f"{label} 不能是 pipelines 根目录")
    return resolved


@router.post("/folders/{project_id}", status_code=201)
async def create_pipeline_folder(project_id: str, body: CreateFolderRequest):
    """新建流水线文件夹（支持多级路径，自动创建父目录）；已存在返回 409。"""
    pipelines_dir = _get_project_pipelines_dir(project_id)
    folder_path = _resolve_folder_path(pipelines_dir, body.folder)
    if folder_path.exists():
        raise HTTPException(status_code=409, detail=f"文件夹已存在: {body.folder}")
    folder_path.mkdir(parents=True, exist_ok=True)
    return {"status": "ok", "folder": _relative_path_str(pipelines_dir, folder_path)}


@router.patch("/folders/{project_id}")
async def rename_pipeline_folder(project_id: str, body: RenameFolderRequest):
    """重命名/移动文件夹，并批量原地更新 DB 定义路径前缀（保留运行历史关联）。"""
    pipelines_dir = _get_project_pipelines_dir(project_id)
    old_path = _resolve_folder_path(pipelines_dir, body.folder)
    if not old_path.is_dir():
        raise HTTPException(status_code=404, detail=f"Folder not found: {body.folder}")
    new_path = _resolve_folder_path(pipelines_dir, body.new_folder, label="new_folder")
    if new_path == old_path:
        raise HTTPException(status_code=400, detail="新文件夹名与原文件夹名相同")
    if new_path.exists():
        raise HTTPException(status_code=409, detail=f"文件夹已存在: {body.new_folder}")
    # 禁止移动到自身子目录，否则 os.rename 会失败或产生不可预期结果
    if old_path in new_path.parents:
        raise HTTPException(status_code=400, detail="不能把文件夹移动到其自身子目录下")

    old_rel = _relative_path_str(pipelines_dir, old_path)
    new_rel = _relative_path_str(pipelines_dir, new_path)
    new_path.parent.mkdir(parents=True, exist_ok=True)
    os.rename(old_path, new_path)

    async with get_session_factory()() as session:
        repo = PipelineDefinitionRepository(session)
        updated = await repo.rename_prefix(project_id, old_rel + os.sep, new_rel + os.sep)
    return {"status": "ok", "folder": new_rel, "definition_id_updated": updated}


@router.delete("/folders/{project_id}")
async def delete_pipeline_folder(
    project_id: str,
    folder: str = Query(..., description="相对 pipelines 目录的文件夹路径"),
    recursive: bool = Query(False, description="非空文件夹需显式 recursive=true 才允许删除"),
):
    """删除流水线文件夹；非空时必须 recursive=true，避免网页端误删整棵目录树。"""
    pipelines_dir = _get_project_pipelines_dir(project_id)
    folder_path = _resolve_folder_path(pipelines_dir, folder)
    if not folder_path.is_dir():
        raise HTTPException(status_code=404, detail=f"Folder not found: {folder}")

    file_count = sum(1 for p in folder_path.rglob("*") if p.is_file())
    if file_count > 0 and not recursive:
        raise HTTPException(
            status_code=409,
            detail=f"文件夹非空（含 {file_count} 个文件），请先清空或使用 recursive=true 递归删除",
        )

    rel_path = _relative_path_str(pipelines_dir, folder_path)
    shutil.rmtree(folder_path)
    async with get_session_factory()() as session:
        repo = PipelineDefinitionRepository(session)
        await repo.deactivate_prefix(project_id, rel_path + os.sep)
    return {"status": "deleted", "folder": rel_path, "file_count": file_count}

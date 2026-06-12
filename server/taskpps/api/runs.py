from __future__ import annotations

import asyncio
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse
from sse_starlette.sse import EventSourceResponse

from taskpps.config import build_pipeline_log_path
from taskpps.db.engine import get_session_factory
from taskpps.db.repository import RunRepository, TaskRunRepository
from taskpps.i18n import t
from taskpps.schemas.run import CleanResponse, CreateRunRequest, RunListResponse, RunResponse
from taskpps.services.pipeline_service import PipelineService

router = APIRouter(prefix="/runs", tags=["runs"])

_pipeline_service = PipelineService()


@router.post("/", status_code=201)
async def create_run(body: CreateRunRequest):
    try:
        result = await _pipeline_service.create_run(body.pipeline, body.params, project_id=body.project_id)
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.get("/", response_model=RunListResponse)
async def list_runs(
    pipeline: str | None = Query(None),
    status: str | None = Query(None),
    project_id: str | None = Query(None),
    limit: int = Query(50, ge=1, le=500),
):
    runs_data = await _pipeline_service.list_runs(pipeline=pipeline, status=status, project_id=project_id, limit=limit)
    return runs_data


@router.get("/{run_id}", response_model=RunResponse)
async def get_run(run_id: str):
    run = await _pipeline_service.get_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail=t("Run not found"))
    return run


@router.get("/{run_id}/logs")
async def get_run_logs(
    run_id: str,
    task: str | None = Query(None),
    tail: int | None = Query(None, ge=1),
    follow: bool = Query(False),
):
    async with get_session_factory()() as session:
        run_repo = RunRepository(session)
        run = await run_repo.get_run(run_id)
        if run is None:
            raise HTTPException(status_code=404, detail=t("Run not found"))
        task_repo = TaskRunRepository(session)
        task_runs = await task_repo.list_task_runs(run_id)

    if task:
        task_runs = [t for t in task_runs if t.task_name == task]

    if not task_runs:
        return {"logs": {}}

    if not follow:
        result = {}
        for tr in task_runs:
            log_path = Path(tr.log_path)
            if log_path.exists():
                if tail:
                    with open(log_path, "rb") as f:
                        f.seek(0, 2)
                        file_size = f.tell()
                        chunk_size = min(file_size, tail * 256)
                        f.seek(max(0, file_size - chunk_size))
                        raw = f.read().decode("utf-8", errors="replace")
                        lines = raw.split("\n")
                        if file_size > chunk_size:
                            lines = lines[1:]
                        result[tr.task_name] = "\n".join(lines[-tail:])
                else:
                    with open(log_path) as f:
                        result[tr.task_name] = f.read()
            else:
                result[tr.task_name] = ""
        return {"logs": result}

    async def _log_stream():
        log_paths = {}
        for tr in task_runs:
            log_paths[tr.task_name] = Path(tr.log_path)

        positions = {name: 0 for name in log_paths}
        task_ids = {tr.task_name: tr.id for tr in task_runs}
        active = True

        from taskpps.models.run import TaskStatus as TS

        while active:
            active = False

            async with get_session_factory()() as session:
                task_repo = TaskRunRepository(session)
                statuses: dict[str, TS | None] = {}
                for task_name, tid in task_ids.items():
                    tr = await task_repo.get_task_run(tid)
                    statuses[task_name] = tr.status if tr else None

            for task_name, log_path in log_paths.items():
                if not log_path.exists():  # pragma: no cover
                    active = True  # pragma: no cover
                    continue  # pragma: no cover

                had_output = False
                with open(log_path) as f:
                    f.seek(positions[task_name])
                    new_content = f.read()
                    if new_content:
                        had_output = True
                        positions[task_name] = f.tell()
                        for line in new_content.splitlines():
                            if line:
                                yield {"event": "log", "data": f"{task_name}: {line}"}

                task_status = statuses.get(task_name)
                is_active = task_status and task_status not in (
                    TS.SUCCESS, TS.FAILED, TS.CANCELLED, TS.SKIPPED,
                )

                if is_active:  # pragma: no cover
                    active = True  # pragma: no cover
                    if had_output:  # pragma: no cover
                        await asyncio.sleep(0.05)  # pragma: no cover
                        with open(log_path) as f:  # pragma: no cover
                            f.seek(positions[task_name])  # pragma: no cover
                            more = f.read()  # pragma: no cover
                            if more:  # pragma: no cover
                                positions[task_name] = f.tell()  # pragma: no cover
                                for line in more.splitlines():  # pragma: no cover
                                    if line:  # pragma: no cover
                                        yield {"event": "log", "data": f"{task_name}: {line}"}  # pragma: no cover

            if active:  # pragma: no cover
                await asyncio.sleep(0.3)  # pragma: no cover

        yield {"event": "done", "data": ""}

    return EventSourceResponse(_log_stream())


@router.post("/{run_id}/cancel")
async def cancel_run(run_id: str):
    success = await _pipeline_service.cancel_run(run_id)
    if not success:
        raise HTTPException(status_code=404, detail=t("Run not found or cannot be cancelled"))
    return {"status": "cancelled", "run_id": run_id}


@router.get("/{run_id}/console")
async def get_run_console(
    run_id: str,
    tail: int | None = Query(None, ge=1, description="仅返回末尾 N 行"),
):
    """获取 pipeline console.log（engine 写入的结构化日志）
    - 包含 [INFO]/[WARN]/[ERROR]/[CMD]/[SUCCESS]/[FAILED] 等级别
    - 失败时是 root cause 的最佳入口
    """
    async with get_session_factory()() as session:
        run_repo = RunRepository(session)
        run = await run_repo.get_run(run_id)
        if run is None:
            raise HTTPException(status_code=404, detail=t("Run not found"))
        pipeline_id = run.pipeline_id
        pipeline_version = run.pipeline_version

    log_path = build_pipeline_log_path(pipeline_id, pipeline_version, run_id)
    headers = {"Cache-Control": "private, max-age=30"}

    if not log_path.exists():
        return JSONResponse(
            content={"log_path": str(log_path), "content": "", "lines": 0, "exists": False},
            headers=headers,
        )

    if tail:
        with open(log_path, "rb") as f:
            f.seek(0, 2)
            size = f.tell()
            block = min(size, tail * 512)
            f.seek(max(0, size - block))
            raw = f.read().decode("utf-8", errors="replace")
            lines = raw.splitlines()
            if size > block:
                lines = lines[1:]
            return JSONResponse(
                content={
                    "log_path": str(log_path),
                    "content": "\n".join(lines[-tail:]),
                    "lines": len(lines[-tail:]),
                    "exists": True,
                },
                headers=headers,
            )

    with open(log_path) as f:
        content = f.read()
    return JSONResponse(
        content={
            "log_path": str(log_path),
            "content": content,
            "lines": content.count("\n") + (1 if content and not content.endswith("\n") else 0),
            "exists": True,
        },
        headers=headers,
    )


@router.delete("/", response_model=CleanResponse)
async def clean_runs(
    older_than: int | None = Query(None, description="Delete runs older than N days", ge=1),
    keep: int | None = Query(None, description="Keep only N most recent runs", ge=0),
    force: bool = Query(False, description="Delete all runs"),
):
    try:
        result = await _pipeline_service.clean_runs(older_than=older_than, keep=keep, force=force)
        return result
    except Exception as e:
        import traceback

        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"{type(e).__name__}: {e}") from e

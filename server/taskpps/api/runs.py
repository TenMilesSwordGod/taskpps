from __future__ import annotations

import asyncio
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, HTTPException, Query
from sse_starlette.sse import EventSourceResponse

from taskpps.config import get_logs_dir
from taskpps.db.engine import get_session_factory
from taskpps.db.repository import RunRepository, TaskRunRepository
from taskpps.schemas.run import CreateRunRequest, RunResponse, CleanResponse
from taskpps.services.pipeline_service import PipelineService

router = APIRouter(prefix="/runs", tags=["runs"])

_pipeline_service = PipelineService()


@router.post("/", status_code=201)
async def create_run(body: CreateRunRequest):
    try:
        result = await _pipeline_service.create_run(body.pipeline, body.params)
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/")
async def list_runs(
    pipeline: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=500),
):
    runs = await _pipeline_service.list_runs(pipeline=pipeline, status=status, limit=limit)
    return runs


@router.get("/{run_id}")
async def get_run(run_id: str):
    run = await _pipeline_service.get_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")
    return run


@router.get("/{run_id}/logs")
async def get_run_logs(
    run_id: str,
    task: Optional[str] = Query(None),
    tail: Optional[int] = Query(None, ge=1),
    follow: bool = Query(False),
):
    async with get_session_factory()() as session:
        run_repo = RunRepository(session)
        run = await run_repo.get_run(run_id)
        if run is None:
            raise HTTPException(status_code=404, detail="Run not found")

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
                with open(log_path) as f:
                    lines = f.readlines()
                if tail:
                    lines = lines[-tail:]
                result[tr.task_name] = "".join(lines)
            else:  # pragma: no cover
                result[tr.task_name] = ""  # pragma: no cover
        return {"logs": result}

    async def _log_stream():
        log_paths = {}
        for tr in task_runs:
            log_paths[tr.task_name] = Path(tr.log_path)

        positions = {name: 0 for name in log_paths}
        active = True

        while active:
            active = False
            for task_name, log_path in log_paths.items():
                if not log_path.exists():  # pragma: no cover
                    active = True  # pragma: no cover
                    continue  # pragma: no cover

                with open(log_path) as f:
                    f.seek(positions[task_name])
                    new_content = f.read()
                    if new_content:
                        positions[task_name] = f.tell()
                        yield {"event": "log", "data": f"{task_name}: {new_content}"}

                    from taskpps.models.run import TaskStatus
                    async with get_session_factory()() as session:
                        task_repo = TaskRunRepository(session)
                        task_run = await task_repo.get_task_run(
                            next((t.id for t in task_runs if t.task_name == task_name), "")
                        )
                        if task_run and task_run.status in (TaskStatus.SUCCESS, TaskStatus.FAILED, TaskStatus.CANCELLED, TaskStatus.SKIPPED):
                            pass
                        else:  # pragma: no cover
                            active = True  # pragma: no cover

            if active:  # pragma: no cover
                await asyncio.sleep(0.5)  # pragma: no cover

        yield {"event": "done", "data": ""}

    return EventSourceResponse(_log_stream())


@router.post("/{run_id}/cancel")
async def cancel_run(run_id: str):
    success = await _pipeline_service.cancel_run(run_id)
    if not success:
        raise HTTPException(status_code=404, detail="Run not found or cannot be cancelled")
    return {"status": "cancelled", "run_id": run_id}


@router.delete("/")
async def clean_runs(
    older_than: Optional[int] = Query(None, description="Delete runs older than N days"),
    keep: Optional[int] = Query(None, description="Keep only N most recent runs"),
    force: bool = Query(False, description="Delete all runs"),
):
    result = await _pipeline_service.clean_runs(older_than=older_than, keep=keep, force=force)
    return result

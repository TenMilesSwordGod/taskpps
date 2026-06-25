from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse, StreamingResponse

from taskpps.db.engine import get_session_factory
from taskpps.db.repository import ArtifactRepository, RunRepository
from taskpps.i18n import t
from taskpps.schemas.artifact import (
    ArtifactItem,
    ArtifactListResponse,
    PromoteRequest,
    PromoteResponse,
    UploadResponse,
)
from taskpps.services.artifact_service import (
    get_artifact_file_path,
    get_artifacts_dir,
    promote_artifact,
    upload_artifacts,
)

router = APIRouter(prefix="/runs/{run_id}/artifacts", tags=["artifacts"])


@router.get("", response_model=ArtifactListResponse)
async def list_artifacts(run_id: str):
    async with get_session_factory()() as session:
        run_repo = RunRepository(session)
        run = await run_repo.get_run(run_id)
        if run is None:
            raise HTTPException(status_code=404, detail=t("Run not found"))

        repo = ArtifactRepository(session)
        artifacts = await repo.list_artifacts(run_id)

    default_items = []
    artifact_items = []
    for a in artifacts:
        item = ArtifactItem(
            task_name=a.task_name,
            path=a.path,
            size=a.size,
            mtime=a.mtime,
            content_type=a.content_type,
        )
        if a.task_name == "default":
            default_items.append(item)
        else:
            artifact_items.append(item)

    return ArtifactListResponse(
        run_id=run_id,
        default=default_items,
        artifacts=artifact_items,
    )


@router.get("/{path:path}")
async def download_artifact(run_id: str, path: str):
    parts = path.split("/", 1)
    if len(parts) < 2:
        raise HTTPException(status_code=400, detail="Path must be in format task_name/file_path")

    task_name = parts[0]
    file_path = parts[1]

    async with get_session_factory()() as session:
        repo = ArtifactRepository(session)
        artifact = await repo.get_artifact(run_id, task_name, file_path)
        if artifact is None:
            raise HTTPException(status_code=404, detail=t("Artifact not found"))

    abs_path = get_artifact_file_path(run_id, task_name, file_path)
    if abs_path is None:
        raise HTTPException(status_code=404, detail=t("Artifact file not found"))

    filename = Path(file_path).name
    return FileResponse(
        path=str(abs_path),
        media_type=artifact.content_type,
        filename=filename,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/zip")
async def download_artifacts_zip(
    run_id: str,
    task: str | None = Query(None, description="Filter by task name"),
):
    async with get_session_factory()() as session:
        run_repo = RunRepository(session)
        run = await run_repo.get_run(run_id)
        if run is None:
            raise HTTPException(status_code=404, detail=t("Run not found"))

        repo = ArtifactRepository(session)
        artifacts = await repo.list_artifacts(run_id)

    if task:
        artifacts = [a for a in artifacts if a.task_name == task]

    if not artifacts:
        raise HTTPException(status_code=404, detail=t("No artifacts found"))

    artifacts_dir = get_artifacts_dir(run_id)

    def _generate_zip():
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            for a in artifacts:
                file_path = artifacts_dir / a.task_name / a.path
                if file_path.exists() and file_path.is_file():
                    arcname = f"{a.task_name}/{a.path}"
                    zf.write(file_path, arcname)
        buf.seek(0)
        yield buf.read()

    filename = f"artifacts-{run_id}.zip"
    if task:
        filename = f"artifacts-{run_id}-{task}.zip"

    return StreamingResponse(
        _generate_zip(),
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/promote", response_model=PromoteResponse)
async def promote(run_id: str, body: PromoteRequest):
    async with get_session_factory()() as session:
        run_repo = RunRepository(session)
        run = await run_repo.get_run(run_id)
        if run is None:
            raise HTTPException(status_code=404, detail=t("Run not found"))

    try:
        item = await promote_artifact(
            run_id=run_id,
            task_name=body.task_name,
            source_path=body.path,
            move=body.move,
        )
        return PromoteResponse(artifact=item)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except FileExistsError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e


@router.post("/upload", response_model=UploadResponse)
async def upload(
    run_id: str,
    task_name: str = Form(...),
    paths: str = Form(..., description="JSON array of relative file paths"),
    files: list[UploadFile] = File(...),
):
    async with get_session_factory()() as session:
        run_repo = RunRepository(session)
        run = await run_repo.get_run(run_id)
        if run is None:
            raise HTTPException(status_code=404, detail=t("Run not found"))

    try:
        path_list = json.loads(paths)
    except json.JSONDecodeError as e:
        raise HTTPException(status_code=400, detail="Invalid paths JSON") from e

    if len(path_list) != len(files):
        raise HTTPException(status_code=400, detail="Number of paths must match number of files")

    file_data = []
    for upload_file, file_path in zip(files, path_list, strict=True):
        content = await upload_file.read()
        file_data.append((file_path, content))

    items = await upload_artifacts(run_id, task_name, file_data)
    return UploadResponse(uploaded=items)

from __future__ import annotations

import contextlib
import json
import logging
import mimetypes
import os
import shutil
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from taskpps.config import get_logs_dir
from taskpps.db.engine import get_session_factory
from taskpps.db.repository import ArtifactRepository
from taskpps.schemas.artifact import ArtifactItem, ArtifactRef

logger = logging.getLogger("taskpps.services.artifact_service")

_ARTIFACT_REF_PATTERN = __import__("re").compile(r"\$\{artifact:([^}]+)\}")


def get_artifacts_dir(run_id: str) -> Path:
    artifacts_dir = get_logs_dir() / "artifacts" / run_id
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    return artifacts_dir


def _guess_content_type(path: str) -> str:
    ct, _ = mimetypes.guess_type(path)
    return ct or "application/octet-stream"


def _normalize_path_segments(segments: list[str]) -> list[str]:
    """Resolve . and .. in a list of path segments."""
    result: list[str] = []
    for seg in segments:
        if seg == "." or not seg:
            continue
        if seg == "..":
            if result:
                result.pop()
            continue
        result.append(seg)
    return result


def parse_artifact_ref(ref: str) -> ArtifactRef | None:
    """Parse ${artifact:...} reference into structured parts.

    Supported formats:
    - ${artifact:task/path} (same subpipeline, 2 parts)
    - ${artifact:task/path/deep} (same subpipeline, 3 parts, path has slashes)
    - ${artifact:subpipeline/task/path} (cross subpipeline, 4 parts)
    - ${artifact:run_id/subpipeline/task/path} (cross run, 5+ parts)

    If the raw value contains . or .. segments, they are normalized first
    and the result is treated as same-subpipeline (task_name + path).
    """
    match = _ARTIFACT_REF_PATTERN.search(ref)
    if not match:
        return None

    raw = match.group(1).strip("/")
    parts = [p for p in raw.split("/") if p]

    if len(parts) < 2:
        return None

    has_traversal = any(p in (".", "..") for p in parts)

    if has_traversal:
        parts = _normalize_path_segments(parts)
        if len(parts) < 2:
            return None
        return ArtifactRef(task_name=parts[0], path="/".join(parts[1:]))

    if len(parts) == 2:
        return ArtifactRef(task_name=parts[0], path=parts[1])
    elif len(parts) == 3:
        return ArtifactRef(task_name=parts[0], path="/".join(parts[1:]))
    elif len(parts) == 4:
        return ArtifactRef(subpipeline=parts[0], task_name=parts[1], path="/".join(parts[2:]))
    else:
        return ArtifactRef(run_id=parts[0], subpipeline=parts[1], task_name=parts[2], path="/".join(parts[3:]))


def resolve_artifact_ref(
    ref: ArtifactRef,
    current_run_id: str,
    current_subpipeline: str | None = None,
) -> Path | None:
    """Resolve an artifact reference to an absolute filesystem path."""
    run_id = ref.run_id or current_run_id
    artifacts_dir = get_artifacts_dir(run_id)

    task_name = ref.task_name
    if ref.subpipeline:
        task_name = f"{ref.subpipeline}.{ref.task_name}"
    elif current_subpipeline:
        task_name = f"{current_subpipeline}.{ref.task_name}"

    artifact_path = artifacts_dir / task_name / ref.path
    if artifact_path.exists():
        return artifact_path
    return None


def substitute_artifact_refs(
    text: str,
    current_run_id: str,
    current_subpipeline: str | None = None,
) -> str:
    """Replace all ${artifact:...} references in a string with resolved paths."""

    def _replace(match: Any) -> str:
        ref = parse_artifact_ref(match.group(0))
        if ref is None:
            return match.group(0)
        resolved = resolve_artifact_ref(ref, current_run_id, current_subpipeline)
        if resolved is None:
            logger.warning("Artifact not found: %s", match.group(0))
            return match.group(0)
        return str(resolved)

    return _ARTIFACT_REF_PATTERN.sub(_replace, text)


async def collect_default_artifacts(
    run_id: str,
    pipeline_name: str,
    pipeline_id: str,
    pipeline_version: str,
    status: str,
    started_at: datetime | None,
    finished_at: datetime | None,
    task_names: list[str],
) -> None:
    """Collect default artifacts (log.txt + meta.json) for a run."""
    artifacts_dir = get_artifacts_dir(run_id)
    default_dir = artifacts_dir / "default"
    default_dir.mkdir(parents=True, exist_ok=True)

    log_content = ""
    logs_dir = get_logs_dir()
    if pipeline_id and pipeline_version:
        run_logs_dir = logs_dir / pipeline_id / f"v_{pipeline_version}" / "builds" / run_id
        console_log = run_logs_dir / "console.log"
        if console_log.exists():
            with contextlib.suppress(OSError):
                log_content = console_log.read_text(errors="replace")

    log_path = default_dir / "log.txt"
    log_path.write_text(log_content)

    meta = {
        "run_id": run_id,
        "pipeline": pipeline_name,
        "start_at": started_at.isoformat() if started_at else None,
        "end_at": finished_at.isoformat() if finished_at else None,
        "status": status,
        "tasks": task_names,
    }
    meta_path = default_dir / "meta.json"
    meta_path.write_text(json.dumps(meta, indent=2, ensure_ascii=False))

    async with get_session_factory()() as session:
        repo = ArtifactRepository(session)
        await repo.create_artifact(
            run_id=run_id,
            task_name="default",
            path="log.txt",
            size=log_path.stat().st_size,
            content_type="text/plain",
        )
        await repo.create_artifact(
            run_id=run_id,
            task_name="default",
            path="meta.json",
            size=meta_path.stat().st_size,
            content_type="application/json",
        )


async def collect_task_artifacts(
    run_id: str,
    task_name: str,
    artifacts_config: list[dict[str, Any]],
    workdir: Path,
) -> list[ArtifactItem]:
    """Collect declared artifacts for a task after execution."""
    collected: list[ArtifactItem] = []
    artifacts_dir = get_artifacts_dir(run_id)
    task_artifacts_dir = artifacts_dir / task_name
    task_artifacts_dir.mkdir(parents=True, exist_ok=True)

    async with get_session_factory()() as session:
        repo = ArtifactRepository(session)

        for art_cfg in artifacts_config:
            path_pattern = art_cfg.get("path", "")
            if not path_pattern:
                continue

            matches = sorted(workdir.glob(path_pattern))

            if not matches:
                resolved = workdir / path_pattern
                if resolved.is_dir():
                    zip_name = path_pattern.rstrip("/") + ".zip"
                    zip_path = task_artifacts_dir / zip_name
                    _zip_directory(resolved, zip_path)
                    item = ArtifactItem(
                        task_name=task_name,
                        path=zip_name,
                        size=zip_path.stat().st_size,
                        mtime=datetime.now(timezone.utc),
                        content_type="application/zip",
                    )
                    await repo.create_artifact(
                        run_id=run_id,
                        task_name=task_name,
                        path=zip_name,
                        size=item.size,
                        content_type="application/zip",
                    )
                    collected.append(item)
                continue

            for src in matches:
                if src.is_dir():
                    zip_name = src.name + ".zip"
                    zip_path = task_artifacts_dir / zip_name
                    _zip_directory(src, zip_path)
                    item = ArtifactItem(
                        task_name=task_name,
                        path=zip_name,
                        size=zip_path.stat().st_size,
                        mtime=datetime.now(timezone.utc),
                        content_type="application/zip",
                    )
                    await repo.create_artifact(
                        run_id=run_id,
                        task_name=task_name,
                        path=zip_name,
                        size=item.size,
                        content_type="application/zip",
                    )
                else:
                    dst = task_artifacts_dir / src.name
                    shutil.copy2(src, dst)
                    item = ArtifactItem(
                        task_name=task_name,
                        path=src.name,
                        size=dst.stat().st_size,
                        mtime=datetime.now(timezone.utc),
                        content_type=_guess_content_type(src.name),
                    )
                    await repo.create_artifact(
                        run_id=run_id,
                        task_name=task_name,
                        path=src.name,
                        size=item.size,
                        content_type=_guess_content_type(src.name),
                    )
                collected.append(item)

    return collected


def _zip_directory(src_dir: Path, dst_zip: Path) -> None:
    with zipfile.ZipFile(dst_zip, "w", zipfile.ZIP_DEFLATED) as zf:
        for root, _dirs, files in os.walk(src_dir):
            for file in files:
                file_path = Path(root) / file
                arcname = file_path.relative_to(src_dir)
                zf.write(file_path, arcname)


async def promote_artifact(
    run_id: str,
    task_name: str,
    source_path: str,
    move: bool = False,
) -> ArtifactItem:
    """Promote a file to an artifact."""
    src = Path(source_path)
    if not src.exists():
        raise FileNotFoundError(f"Source file not found: {source_path}")

    artifacts_dir = get_artifacts_dir(run_id)
    task_dir = artifacts_dir / task_name
    task_dir.mkdir(parents=True, exist_ok=True)

    filename = src.name
    dst = task_dir / filename

    async with get_session_factory()() as session:
        repo = ArtifactRepository(session)
        existing = await repo.get_artifact(run_id, task_name, filename)
        if existing is not None:
            raise FileExistsError(f"Artifact already exists: {task_name}/{filename}")

        if move:
            shutil.move(str(src), str(dst))
        else:
            shutil.copy2(str(src), str(dst))

        stat = dst.stat()
        ct = _guess_content_type(filename)
        await repo.create_artifact(
            run_id=run_id,
            task_name=task_name,
            path=filename,
            size=stat.st_size,
            content_type=ct,
        )

    return ArtifactItem(
        task_name=task_name,
        path=filename,
        size=stat.st_size,
        mtime=datetime.now(timezone.utc),
        content_type=ct,
    )


async def upload_artifacts(
    run_id: str,
    task_name: str,
    files: list[tuple[str, bytes]],
) -> list[ArtifactItem]:
    """Upload artifacts from remote agent."""
    artifacts_dir = get_artifacts_dir(run_id)
    task_dir = artifacts_dir / task_name
    task_dir.mkdir(parents=True, exist_ok=True)

    results: list[ArtifactItem] = []

    async with get_session_factory()() as session:
        repo = ArtifactRepository(session)

        for file_path, content in files:
            dst = task_dir / file_path
            dst.parent.mkdir(parents=True, exist_ok=True)
            dst.write_bytes(content)

            ct = _guess_content_type(file_path)
            await repo.create_artifact(
                run_id=run_id,
                task_name=task_name,
                path=file_path,
                size=len(content),
                content_type=ct,
            )
            results.append(
                ArtifactItem(
                    task_name=task_name,
                    path=file_path,
                    size=len(content),
                    mtime=datetime.now(timezone.utc),
                    content_type=ct,
                )
            )

    return results


def get_artifact_file_path(run_id: str, task_name: str, path: str) -> Path | None:
    """Get the absolute file path for an artifact."""
    artifacts_dir = get_artifacts_dir(run_id)
    file_path = artifacts_dir / task_name / path
    if file_path.exists() and file_path.is_file():
        return file_path
    return None

from __future__ import annotations


import json
from datetime import datetime, timezone
from pathlib import Path

import pytest
import pytest_asyncio

from taskpps.db.engine import get_session_factory
from taskpps.db.repository import ArtifactRepository, RunRepository
from taskpps.main import app as _app
from taskpps.models.run import PipelineRun, RunStatus
from taskpps.services.artifact_service import get_artifacts_dir


@pytest.fixture
def app():
    return _app


@pytest_asyncio.fixture
async def sample_run(db_engine):
    """Create a sample pipeline run in the database."""
    async with get_session_factory()() as session:
        repo = RunRepository(session)
        run = PipelineRun(
            id="test_run_001",
            pipeline_name="test-pipeline",
            pipeline_file="test.yaml",
            pipeline_id="pid_001",
            pipeline_version="1",
            status=RunStatus.SUCCESS,
            started_at=datetime(2026, 6, 25, 10, 0, 0, tzinfo=timezone.utc),
            finished_at=datetime(2026, 6, 25, 10, 5, 0, tzinfo=timezone.utc),
        )
        session.add(run)
        await session.commit()
        await session.refresh(run)
    return run


@pytest.fixture
def artifacts_dir(sample_run):
    """Ensure artifacts directory exists for the sample run and return its path."""
    d = get_artifacts_dir(sample_run.id)
    return d


@pytest.fixture
def default_artifacts(artifacts_dir):
    """Create default artifacts (log.txt + meta.json) on disk and in DB."""
    import asyncio

    default_dir = artifacts_dir / "default"
    default_dir.mkdir(parents=True, exist_ok=True)

    log_path = default_dir / "log.txt"
    log_path.write_text("task1 executed\ntask2 executed\n")

    meta = {
        "run_id": "test_run_001",
        "definition_id": "test-def-001",
        # v2 (2026-07): 旧的 pipeline 字段已废弃，改为 definition_id
        # "pipeline": "test-pipeline",
        "start_at": "2026-06-25T10:00:00+00:00",
        "end_at": "2026-06-25T10:05:00+00:00",
        "status": "success",
        "tasks": ["task1", "task2"],
    }
    meta_path = default_dir / "meta.json"
    meta_path.write_text(json.dumps(meta, indent=2))

    async def _insert():
        async with get_session_factory()() as session:
            repo = ArtifactRepository(session)
            await repo.create_artifact(
                run_id="test_run_001",
                task_name="default",
                path="log.txt",
                size=log_path.stat().st_size,
                content_type="text/plain",
            )
            await repo.create_artifact(
                run_id="test_run_001",
                task_name="default",
                path="meta.json",
                size=meta_path.stat().st_size,
                content_type="application/json",
            )

    asyncio.get_event_loop().run_until_complete(_insert())
    return artifacts_dir


@pytest.fixture
def build_artifacts(artifacts_dir):
    """Create build task artifacts on disk and in DB."""
    import asyncio

    build_dir = artifacts_dir / "build"
    build_dir.mkdir(parents=True, exist_ok=True)

    files = {
        "app.tar.gz": b"\x1f\x8b" + b"\x00" * 100,
        "config.yaml": b"version: 1\nname: test\n",
    }

    for name, content in files.items():
        (build_dir / name).write_bytes(content)

    dist_dir = build_dir / "dist"
    dist_dir.mkdir(exist_ok=True)
    (dist_dir / "app.tar.gz").write_bytes(b"\x1f\x8b" + b"\x00" * 200)

    async def _insert():
        async with get_session_factory()() as session:
            repo = ArtifactRepository(session)
            for name, content in files.items():
                await repo.create_artifact(
                    run_id="test_run_001",
                    task_name="build",
                    path=name,
                    size=len(content),
                    content_type="application/gzip" if name.endswith(".gz") else "text/yaml",
                )
            await repo.create_artifact(
                run_id="test_run_001",
                task_name="build",
                path="dist/app.tar.gz",
                size=200,
                content_type="application/gzip",
            )

    asyncio.get_event_loop().run_until_complete(_insert())
    return build_dir

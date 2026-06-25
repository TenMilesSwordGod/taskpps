"""并发测试 — 并发请求/重复提交/竞态/幂等场景。"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from taskpps.db.engine import get_session_factory
from taskpps.db.repository import ArtifactRepository
from taskpps.services.artifact_service import collect_task_artifacts, promote_artifact


class TestConcurrentPromote:
    @pytest.mark.zentao("TC-C0001", domain="server/artifacts", priority="P1")
    async def test_concurrent_promote_same_path(
        self, app, sample_run, artifacts_dir, default_artifacts, db_engine, tmp_path
    ):
        """并发: 两个请求同时 promote 同一路径，只有一个成功。"""
        source = tmp_path / "race.txt"
        source.write_bytes(b"race-content")

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            results = await asyncio.gather(
                client.post(
                    f"/api/runs/{sample_run.id}/artifacts/promote",
                    json={"task_name": "build", "path": str(source), "move": False},
                ),
                client.post(
                    f"/api/runs/{sample_run.id}/artifacts/promote",
                    json={"task_name": "build", "path": str(source), "move": False},
                ),
                return_exceptions=True,
            )

        statuses = [r.status_code if hasattr(r, "status_code") else None for r in results]
        assert 200 in statuses, "At least one promote should succeed"
        assert 409 in statuses, "The duplicate promote should get 409"


class TestConcurrentZipDownload:
    @pytest.mark.zentao("TC-C0002", domain="server/artifacts", priority="P2")
    async def test_concurrent_zip_downloads(
        self, app, sample_run, artifacts_dir, default_artifacts, db_engine, tmp_path
    ):
        """并发: 多个客户端同时下载同一 run 的 zip。"""
        workdir = tmp_path / "workdir"
        workdir.mkdir()
        for i in range(5):
            (workdir / f"file{i}.txt").write_bytes(f"content-{i}".encode())

        await collect_task_artifacts(
            run_id=sample_run.id,
            task_name="concurrent-task",
            artifacts_config=[{"path": "file*.txt"}],
            workdir=workdir,
        )

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            results = await asyncio.gather(
                client.get(f"/api/runs/{sample_run.id}/artifacts/zip"),
                client.get(f"/api/runs/{sample_run.id}/artifacts/zip"),
                client.get(f"/api/runs/{sample_run.id}/artifacts/zip"),
            )

        for resp in results:
            assert resp.status_code == 200
            assert resp.headers["content-type"] == "application/zip"


class TestConcurrentArtifactCollection:
    @pytest.mark.zentao("TC-C0003", domain="server/artifacts", priority="P1")
    async def test_parallel_task_artifact_collection(
        self, sample_run, artifacts_dir, db_engine, tmp_path
    ):
        """并发: 同 subpipeline 多 task 并行收集 artifacts 无竞态。"""
        workdir = tmp_path / "workdir"
        workdir.mkdir()

        for task_name in ["compile", "test", "package"]:
            task_dir = workdir / task_name
            task_dir.mkdir()
            (task_dir / "output.txt").write_bytes(f"{task_name}-output".encode())

        results = await asyncio.gather(
            collect_task_artifacts(
                run_id=sample_run.id,
                task_name="compile",
                artifacts_config=[{"path": "output.txt"}],
                workdir=workdir / "compile",
            ),
            collect_task_artifacts(
                run_id=sample_run.id,
                task_name="test",
                artifacts_config=[{"path": "output.txt"}],
                workdir=workdir / "test",
            ),
            collect_task_artifacts(
                run_id=sample_run.id,
                task_name="package",
                artifacts_config=[{"path": "output.txt"}],
                workdir=workdir / "package",
            ),
        )

        assert len(results) == 3
        for items in results:
            assert len(items) == 1

        async with get_session_factory()() as session:
            repo = ArtifactRepository(session)
            all_arts = await repo.list_artifacts(sample_run.id)

        task_names = {a.task_name for a in all_arts}
        assert "compile" in task_names
        assert "test" in task_names
        assert "package" in task_names


class TestConcurrentUpload:
    @pytest.mark.zentao("TC-C0004", domain="server/artifacts", priority="P1")
    async def test_concurrent_uploads_from_multiple_agents(
        self, app, sample_run, artifacts_dir, default_artifacts, db_engine
    ):
        """并发: 多个远程 Agent 同时 upload 到同一 run。"""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            results = await asyncio.gather(
                client.post(
                    f"/api/runs/{sample_run.id}/artifacts/upload",
                    data={
                        "task_name": "agent-a-build",
                        "paths": json.dumps(["output.txt"]),
                    },
                    files=[("files", ("output.txt", b"agent-a-output", "text/plain"))],
                ),
                client.post(
                    f"/api/runs/{sample_run.id}/artifacts/upload",
                    data={
                        "task_name": "agent-b-build",
                        "paths": json.dumps(["output.txt"]),
                    },
                    files=[("files", ("output.txt", b"agent-b-output", "text/plain"))],
                ),
                client.post(
                    f"/api/runs/{sample_run.id}/artifacts/upload",
                    data={
                        "task_name": "agent-c-build",
                        "paths": json.dumps(["result.bin"]),
                    },
                    files=[("files", ("result.bin", b"\x00\x01\x02", "application/octet-stream"))],
                ),
            )

        for resp in results:
            assert resp.status_code == 200
            assert len(resp.json()["uploaded"]) == 1

        async with get_session_factory()() as session:
            repo = ArtifactRepository(session)
            all_arts = await repo.list_artifacts(sample_run.id)

        task_names = {a.task_name for a in all_arts}
        assert "agent-a-build" in task_names
        assert "agent-b-build" in task_names
        assert "agent-c-build" in task_names

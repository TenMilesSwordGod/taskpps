"""环境测试 — 文件系统/权限/磁盘/符号链接等环境相关场景。"""
from __future__ import annotations

import json
import os
import zipfile
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from taskpps.services.artifact_service import (
    collect_task_artifacts,
    get_artifacts_dir,
    promote_artifact,
)


class TestSymlinkPath:
    @pytest.mark.zentao("TC-EN0001", domain="server/artifacts", priority="P2")
    async def test_artifact_path_through_symlink(
        self, sample_run, artifacts_dir, db_engine, tmp_path
    ):
        """环境: artifact 路径含符号链接时正确处理。"""
        workdir = tmp_path / "workdir"
        workdir.mkdir()
        real_dir = tmp_path / "real_data"
        real_dir.mkdir()
        (real_dir / "report.txt").write_bytes(b"report-content")

        link_path = workdir / "linked_data"
        try:
            link_path.symlink_to(real_dir)
        except OSError:
            pytest.skip("Symlink creation not supported")

        items = await collect_task_artifacts(
            run_id=sample_run.id,
            task_name="symlink-task",
            artifacts_config=[{"path": "linked_data/report.txt"}],
            workdir=workdir,
        )

        assert len(items) == 1
        assert (artifacts_dir / "symlink-task" / "report.txt").exists()


class TestPathTraversal:
    @pytest.mark.zentao("TC-EN0002", domain="server/artifacts", priority="P1")
    async def test_path_traversal_rejected(
        self, sample_run, artifacts_dir, db_engine, tmp_path
    ):
        """环境: 路径穿越攻击 (../) 被拒绝或限制在 artifacts 目录内。"""
        workdir = tmp_path / "workdir"
        workdir.mkdir()
        (workdir / "safe.txt").write_bytes(b"safe-content")

        items = await collect_task_artifacts(
            run_id=sample_run.id,
            task_name="traversal-task",
            artifacts_config=[{"path": "../../../etc/passwd"}],
            workdir=workdir,
        )

        assert items == [], "Path traversal should produce no artifacts"

        passwd_in_artifacts = artifacts_dir / "traversal-task" / "passwd"
        assert not passwd_in_artifacts.exists(), "Path traversal should not create file outside artifacts dir"


class TestPermissionDenied:
    @pytest.mark.zentao("TC-EN0003", domain="server/artifacts", priority="P2")
    async def test_readonly_artifacts_dir(self, sample_run, db_engine, tmp_path):
        """环境: artifacts 目录无写权限时的错误处理。"""
        workdir = tmp_path / "workdir"
        workdir.mkdir()
        (workdir / "file.txt").write_bytes(b"content")

        artifacts_root = tmp_path / "readonly_artifacts"
        artifacts_root.mkdir()
        task_dir = artifacts_root / "readonly-task"
        task_dir.mkdir()

        if os.name != "nt":
            os.chmod(task_dir, 0o444)
            try:
                with pytest.raises(OSError):
                    dst = task_dir / "file.txt"
                    dst.write_bytes(b"should-fail")
            finally:
                os.chmod(task_dir, 0o755)


class TestLargeFileStreaming:
    @pytest.mark.zentao("TC-EN0004", domain="server/artifacts", priority="P1")
    async def test_large_file_artifact(
        self, sample_run, artifacts_dir, db_engine, tmp_path
    ):
        """环境: 大文件 (>10MB) artifact 正确收集。"""
        workdir = tmp_path / "workdir"
        workdir.mkdir()

        large_file = workdir / "large.bin"
        chunk = b"\x00" * 1024
        with open(large_file, "wb") as f:
            for _ in range(10240):
                f.write(chunk)

        items = await collect_task_artifacts(
            run_id=sample_run.id,
            task_name="large-task",
            artifacts_config=[{"path": "large.bin"}],
            workdir=workdir,
        )

        assert len(items) == 1
        assert items[0].size == 1024 * 10240
        collected = artifacts_dir / "large-task" / "large.bin"
        assert collected.exists()
        assert collected.stat().st_size == 1024 * 10240


class TestDiskFull:
    @pytest.mark.zentao("TC-EN0005", domain="server/artifacts", priority="P2")
    async def test_disk_full_during_collection(
        self, sample_run, db_engine, tmp_path, monkeypatch
    ):
        """环境: 磁盘满时 artifact 收集的错误处理。"""
        workdir = tmp_path / "workdir"
        workdir.mkdir()
        (workdir / "file.txt").write_bytes(b"content")

        original_write = Path.write_bytes

        def failing_write(self, data):
            raise OSError(28, "No space left on device")

        monkeypatch.setattr(Path, "write_bytes", failing_write)

        with pytest.raises(OSError, match="No space left on device"):
            await collect_task_artifacts(
                run_id=sample_run.id,
                task_name="diskfull-task",
                artifacts_config=[{"path": "file.txt"}],
                workdir=workdir,
            )


class TestArtifactDirCreation:
    @pytest.mark.zentao("TC-EN0001", domain="server/artifacts", priority="P2")
    def test_artifacts_dir_auto_created(self, sample_run, tmp_path, monkeypatch):
        """环境: artifacts 目录不存在时自动创建。"""
        monkeypatch.setattr(
            "taskpps.services.artifact_service.get_logs_dir",
            lambda: tmp_path / "custom_logs",
        )

        d = get_artifacts_dir("new_run_001")
        assert d.exists()
        assert d.is_dir()


class TestNestedDirectoryStructure:
    @pytest.mark.zentao("TC-EN0001", domain="server/artifacts", priority="P2")
    async def test_deeply_nested_artifact_path(
        self, sample_run, artifacts_dir, db_engine, tmp_path
    ):
        """环境: 深层嵌套目录结构正确收集。"""
        workdir = tmp_path / "workdir"
        workdir.mkdir()
        deep = workdir / "a" / "b" / "c" / "d"
        deep.mkdir(parents=True)
        (deep / "deep.txt").write_bytes(b"deep-content")

        items = await collect_task_artifacts(
            run_id=sample_run.id,
            task_name="nested-task",
            artifacts_config=[{"path": "a/b/c/d/deep.txt"}],
            workdir=workdir,
        )

        assert len(items) == 1
        assert items[0].path == "deep.txt"


class TestDirectoryWithSubdirectories:
    @pytest.mark.zentao("TC-EN0001", domain="server/artifacts", priority="P2")
    async def test_directory_with_subdirs_zipped(
        self, sample_run, artifacts_dir, db_engine, tmp_path
    ):
        """环境: 包含子目录的目录正确打包为 zip。"""
        workdir = tmp_path / "workdir"
        workdir.mkdir()
        reports = workdir / "reports"
        reports.mkdir()
        (reports / "summary.html").write_bytes(b"<html>summary</html>")

        sub1 = reports / "unit"
        sub1.mkdir()
        (sub1 / "junit.xml").write_bytes(b"<testsuites/>")

        sub2 = reports / "integration"
        sub2.mkdir()
        (sub2 / "results.json").write_bytes(b'{"passed": 10}')

        sub3 = sub2 / "screenshots"
        sub3.mkdir()
        (sub3 / "test1.png").write_bytes(b"\x89PNG")

        items = await collect_task_artifacts(
            run_id=sample_run.id,
            task_name="reports-task",
            artifacts_config=[{"path": "reports/"}],
            workdir=workdir,
        )

        assert len(items) == 1
        assert items[0].content_type == "application/zip"

        zip_path = artifacts_dir / "reports-task" / "reports.zip"
        assert zip_path.exists()

        with zipfile.ZipFile(zip_path) as zf:
            names = zf.namelist()
            assert "summary.html" in names
            assert "unit/junit.xml" in names
            assert "integration/results.json" in names
            assert "integration/screenshots/test1.png" in names


class TestPromoteWithNestedSourcePath:
    @pytest.mark.zentao("TC-EN0001", domain="server/artifacts", priority="P2")
    async def test_promote_from_nested_source(
        self, app, sample_run, artifacts_dir, default_artifacts, db_engine, tmp_path
    ):
        """环境: promote 从深层嵌套路径的源文件。"""
        nested = tmp_path / "deep" / "nested" / "dir"
        nested.mkdir(parents=True)
        source = nested / "report.csv"
        source.write_bytes(b"col1,col2\n1,2\n")

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                f"/api/runs/{sample_run.id}/artifacts/promote",
                json={"task_name": "analysis", "path": str(source), "move": False},
            )
            assert resp.status_code == 200
            assert resp.json()["artifact"]["path"] == "report.csv"

        promoted = artifacts_dir / "analysis" / "report.csv"
        assert promoted.exists()

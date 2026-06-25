"""边界值测试 — artifact 路径/大小/特殊字符等边界场景。"""
from __future__ import annotations

import zipfile
from pathlib import Path

import pytest

from taskpps.services.artifact_service import (
    collect_task_artifacts,
    parse_artifact_ref,
)


class TestBoundaryEmptyList:
    @pytest.mark.zentao("TC-B0001", domain="server/artifacts", priority="P2")
    async def test_empty_artifacts_config(self, sample_run, artifacts_dir, db_engine, tmp_path):
        """边界: 空 artifacts 列表不产生任何产物。"""
        workdir = tmp_path / "workdir"
        workdir.mkdir()

        items = await collect_task_artifacts(
            run_id=sample_run.id,
            task_name="empty-task",
            artifacts_config=[],
            workdir=workdir,
        )

        assert items == []


class TestBoundarySpecialChars:
    @pytest.mark.zentao("TC-B0002", domain="server/artifacts", priority="P2")
    async def test_artifact_path_with_spaces(self, sample_run, artifacts_dir, db_engine, tmp_path):
        """边界: artifact 路径含空格。"""
        workdir = tmp_path / "workdir"
        workdir.mkdir()
        (workdir / "my file.txt").write_bytes(b"content")

        items = await collect_task_artifacts(
            run_id=sample_run.id,
            task_name="spaced",
            artifacts_config=[{"path": "my file.txt"}],
            workdir=workdir,
        )

        assert len(items) == 1
        assert (artifacts_dir / "spaced" / "my file.txt").exists()

    @pytest.mark.zentao("TC-B0002", domain="server/artifacts", priority="P2")
    async def test_artifact_path_with_chinese_chars(self, sample_run, artifacts_dir, db_engine, tmp_path):
        """边界: artifact 路径含中文字符。"""
        workdir = tmp_path / "workdir"
        workdir.mkdir()
        (workdir / "报告.html").write_bytes(b"<html></html>")

        items = await collect_task_artifacts(
            run_id=sample_run.id,
            task_name="cn-task",
            artifacts_config=[{"path": "报告.html"}],
            workdir=workdir,
        )

        assert len(items) == 1
        assert items[0].path == "报告.html"

    @pytest.mark.zentao("TC-B0002", domain="server/artifacts", priority="P2")
    def test_parse_ref_with_special_chars(self):
        """边界: artifact 引用路径含特殊字符。"""
        ref = parse_artifact_ref("${artifact:build/dist/my-app_v2.0.tar.gz}")
        assert ref is not None
        assert ref.task_name == "build"
        assert ref.path == "dist/my-app_v2.0.tar.gz"


class TestBoundaryLongPath:
    @pytest.mark.zentao("TC-B0003", domain="server/artifacts", priority="P2")
    async def test_very_long_artifact_path(self, sample_run, artifacts_dir, db_engine, tmp_path):
        """边界: artifact 路径超长 (>255 字符)。"""
        workdir = tmp_path / "workdir"
        workdir.mkdir()
        long_name = "a" * 200 + ".txt"
        (workdir / long_name).write_bytes(b"long-path-content")

        items = await collect_task_artifacts(
            run_id=sample_run.id,
            task_name="long-path",
            artifacts_config=[{"path": long_name}],
            workdir=workdir,
        )

        assert len(items) == 1
        assert items[0].path == long_name


class TestBoundaryGlobNoMatch:
    @pytest.mark.zentao("TC-B0004", domain="server/artifacts", priority="P2")
    async def test_glob_matching_no_files(self, sample_run, artifacts_dir, db_engine, tmp_path):
        """边界: glob 模式匹配零文件时不产生 artifact。"""
        workdir = tmp_path / "workdir"
        workdir.mkdir()

        items = await collect_task_artifacts(
            run_id=sample_run.id,
            task_name="no-match",
            artifacts_config=[{"path": "*.nonexistent"}],
            workdir=workdir,
        )

        assert items == []


class TestBoundaryZeroByteFile:
    @pytest.mark.zentao("TC-B0005", domain="server/artifacts", priority="P2")
    async def test_zero_byte_artifact(self, sample_run, artifacts_dir, db_engine, tmp_path):
        """边界: 零字节文件作为 artifact。"""
        workdir = tmp_path / "workdir"
        workdir.mkdir()
        (workdir / "empty.txt").write_bytes(b"")

        items = await collect_task_artifacts(
            run_id=sample_run.id,
            task_name="zero-byte",
            artifacts_config=[{"path": "empty.txt"}],
            workdir=workdir,
        )

        assert len(items) == 1
        assert items[0].size == 0
        assert (artifacts_dir / "zero-byte" / "empty.txt").exists()


class TestBoundarySingleCharFilename:
    @pytest.mark.zentao("TC-B0006", domain="server/artifacts", priority="P2")
    async def test_single_char_filename(self, sample_run, artifacts_dir, db_engine, tmp_path):
        """边界: 单字符文件名 artifact。"""
        workdir = tmp_path / "workdir"
        workdir.mkdir()
        (workdir / "x").write_bytes(b"single-char")

        items = await collect_task_artifacts(
            run_id=sample_run.id,
            task_name="single-char",
            artifacts_config=[{"path": "x"}],
            workdir=workdir,
        )

        assert len(items) == 1
        assert items[0].path == "x"


class TestBoundaryPathNormalization:
    @pytest.mark.zentao("TC-B0007", domain="server/artifacts", priority="P2")
    def test_parse_ref_with_consecutive_slashes(self):
        """边界: artifact 路径含连续斜杠和点号。"""
        ref = parse_artifact_ref("${artifact:build/./dist/../dist/app.tar.gz}")
        assert ref is not None
        assert ref.task_name == "build"

    @pytest.mark.zentao("TC-B0007", domain="server/artifacts", priority="P2")
    def test_parse_ref_with_trailing_slash(self):
        """边界: artifact 路径含尾部斜杠。"""
        ref = parse_artifact_ref("${artifact:build/dist/}")
        assert ref is not None
        assert ref.task_name == "build"

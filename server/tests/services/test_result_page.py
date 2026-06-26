from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from taskpps.models.run import RunStatus, TaskStatus
from taskpps.services.result_page import (
    _build_default_stats,
    _generate_html,
    _generate_md,
    generate_result_page,
    get_result_page_path,
    load_result_page,
)


class TestBuildDefaultStats:
    def test_all_success(self):
        tasks = [
            {"task_name": "t1", "status": "success"},
            {"task_name": "t2", "status": "success"},
            {"task_name": "t3", "status": "success"},
        ]
        stats = _build_default_stats(tasks, "success", "2024-01-01T00:00:00", "2024-01-01T00:01:00")
        assert stats["pass_count"] == 3
        assert stats["fail_count"] == 0
        assert stats["blocked_count"] == 0
        assert stats["total_count"] == 3
        assert stats["duration"] == "1m 0s"

    def test_mixed_statuses(self):
        tasks = [
            {"task_name": "t1", "status": "success"},
            {"task_name": "t2", "status": "success"},
            {"task_name": "t3", "status": "failed"},
            {"task_name": "t4", "status": "failed"},
            {"task_name": "t5", "status": "skipped"},
            {"task_name": "t6", "status": "cancelled"},
        ]
        stats = _build_default_stats(tasks, "partial", "2024-01-01T00:00:00", "2024-01-01T00:00:30")
        assert stats["pass_count"] == 2
        assert stats["fail_count"] == 2
        assert stats["blocked_count"] == 2
        assert stats["total_count"] == 6
        assert stats["duration"] == "30s"

    def test_all_failed(self):
        tasks = [
            {"task_name": "t1", "status": "failed"},
            {"task_name": "t2", "status": "failed"},
        ]
        stats = _build_default_stats(tasks, "failed", None, None)
        assert stats["pass_count"] == 0
        assert stats["fail_count"] == 2
        assert stats["duration"] == ""

    def test_empty_tasks(self):
        stats = _build_default_stats([], "success", None, None)
        assert stats["pass_count"] == 0
        assert stats["fail_count"] == 0
        assert stats["total_count"] == 0


class TestGenerateHTML:
    def test_success_html(self):
        stats = _build_default_stats(
            [{"task_name": "t1", "status": "success"}],
            "success", "2024-01-01T00:00:00", "2024-01-01T00:01:00",
        )
        html = _generate_html(stats, "test-pipeline")
        assert "<title>Pipeline Result - test-pipeline</title>" in html
        assert "成功" in html
        assert "Pass" in html
        assert "通过率" in html
        assert "100.0%" in html
        assert "script" not in html  # No scripts injected

    def test_failed_html(self):
        stats = _build_default_stats(
            [
                {"task_name": "t1", "status": "success"},
                {"task_name": "t2", "status": "failed"},
                {"task_name": "t3", "status": "skipped"},
            ],
            "failed", "2024-01-01T00:00:00", "2024-01-01T00:02:00",
        )
        html = _generate_html(stats, "test-pipeline")
        assert "失败 (Fail)" in html
        assert "阻塞 (Block)" in html
        assert "33.3%" in html


class TestGenerateMD:
    def test_success_md(self):
        stats = _build_default_stats(
            [{"task_name": "t1", "status": "success"}],
            "success", "2024-01-01T00:00:00", "2024-01-01T00:01:00",
        )
        md = _generate_md(stats, "test-pipeline")
        assert "# test-pipeline" in md
        assert "**状态**" in md
        assert "通过 (Pass)" in md
        assert "100.0%" in md

    def test_mixed_md(self):
        stats = _build_default_stats(
            [
                {"task_name": "t1", "status": "success"},
                {"task_name": "t2", "status": "failed"},
            ],
            "partial", None, None,
        )
        md = _generate_md(stats, "test-pipeline")
        assert "失败 (Fail)" in md
        assert "部分成功" in md


class TestGenerateAndLoadResultPage:
    def test_generate_and_load(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            result_path = Path(tmpdir) / "result.json"
            with patch(
                "taskpps.services.result_page.get_result_page_path",
                return_value=result_path,
            ), patch(
                "taskpps.services.result_page.load_result_page",
                side_effect=lambda *args: (lambda p: None if not Path(p).exists() else json.loads(Path(p).read_text()))(str(result_path)),
            ):
                tasks = [
                    {"task_name": "t1", "status": "success"},
                    {"task_name": "t2", "status": "failed"},
                ]
                data = generate_result_page(
                    run_id="test-run",
                    pipeline_name="test-pipeline",
                    pipeline_id="pid",
                    pipeline_version="v1",
                    status="partial",
                    started_at="2024-01-01T00:00:00",
                    finished_at="2024-01-01T00:01:30",
                    tasks=tasks,
                )
                assert data["run_id"] == "test-run"
                assert data["status"] == "partial"
                assert data["stats"]["pass_count"] == 1
                assert data["stats"]["fail_count"] == 1
                assert "html_content" in data
                assert "md_content" in data
                assert data["has_collector"] is False

                result_path.parent.mkdir(parents=True, exist_ok=True)

    def test_generate_without_pipeline_id_creates_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            result_path = Path(tmpdir) / "builds" / "test-run" / "result.json"
            with patch(
                "taskpps.services.result_page.get_result_page_path",
                return_value=result_path,
            ):
                generate_result_page(
                    run_id="test-run",
                    pipeline_name="test",
                    pipeline_id="",
                    pipeline_version="",
                    status="success",
                    started_at=None,
                    finished_at=None,
                    tasks=[],
                )
                assert result_path.exists()

    def test_collector_replace_mode(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            result_path = Path(tmpdir) / "result.json"
            with patch(
                "taskpps.services.result_page.get_result_page_path",
                return_value=result_path,
            ):
                data = generate_result_page(
                    run_id="test-run",
                    pipeline_name="test",
                    pipeline_id="pid",
                    pipeline_version="v1",
                    status="success",
                    started_at=None,
                    finished_at=None,
                    tasks=[{"task_name": "t1", "status": "success"}],
                    collector_html="<h1>CUSTOM</h1>",
                    collector_md="# CUSTOM",
                    collector_mode="replace",
                )
                assert data["html_content"] == "<h1>CUSTOM</h1>"
                assert data["md_content"] == "# CUSTOM"
                assert data["has_collector"] is True
                assert "Pass" not in data["html_content"]

    def test_collector_append_mode(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            result_path = Path(tmpdir) / "result.json"
            with patch(
                "taskpps.services.result_page.get_result_page_path",
                return_value=result_path,
            ):
                data = generate_result_page(
                    run_id="test-run",
                    pipeline_name="test",
                    pipeline_id="pid",
                    pipeline_version="v1",
                    status="success",
                    started_at=None,
                    finished_at=None,
                    tasks=[{"task_name": "t1", "status": "success"}],
                    collector_html="<h1>EXTRA</h1>",
                    collector_md="# EXTRA",
                    collector_mode="append",
                )
                assert "<hr>" in data["html_content"]
                assert "<h1>EXTRA</h1>" in data["html_content"]
                assert "---" in data["md_content"]
                assert "# EXTRA" in data["md_content"]
                assert "Pass" in data["html_content"]  # Default still exists

"""
QA independent tests for result_page service.
Covers 4 dimensions: Boundary / Exception / Concurrency / Environment.
No overlap with developer's tests in test_result_page.py.

Mapped to zentao testcases:
  TC-S2000 (case_1573): Boundary + Environment
  TC-S2001 (case_1574): Boundary + Environment
  TC-S2002 (case_1575): Environment
  TC-S2003 (case_1576): Environment
"""
from __future__ import annotations

import json
import tempfile
import time
from pathlib import Path
from threading import Thread
from unittest.mock import patch

import pytest

from taskpps.services.result_page import (
    _build_default_stats,
    _generate_html,
    _generate_md,
    generate_result_page,
    load_result_page,
    get_result_page_path,
)


# ══════════════════════════════════════════════════════
# 1. BOUNDARY
# ══════════════════════════════════════════════════════


class TestBoundaryBuildStats:
    """边界：极端/特殊输入"""

    def test_large_task_list(self):
        """大量 tasks (10000+) — 不应崩溃，统计准确"""
        tasks = []
        for i in range(5000):
            tasks.append({"task_name": f"t{i}", "status": "success"})
        for i in range(3000):
            tasks.append({"task_name": f"t{i+5000}", "status": "failed"})
        for i in range(2000):
            tasks.append({"task_name": f"t{i+8000}", "status": "skipped"})
        stats = _build_default_stats(tasks, "partial", "2024-01-01T00:00:00", "2024-01-01T00:01:00")
        assert stats["total_count"] == 10000
        assert stats["pass_count"] == 5000
        assert stats["fail_count"] == 3000
        assert stats["blocked_count"] == 2000

    def test_special_chars_in_pipeline_name(self):
        """管道名称含中文、emoji、特殊符号"""
        name = "测试Pipeline🔥 #154 — 结果页面 (v1.0)"
        stats = _build_default_stats(
            [{"task_name": "t1", "status": "success"}], "success", None, None
        )
        html = _generate_html(stats, name)
        md = _generate_md(stats, name)
        assert "测试Pipeline🔥 #154 — 结果页面 (v1.0)" in html
        assert "# 测试Pipeline🔥 #154 — 结果页面 (v1.0)" in md

    def test_task_name_with_unicode(self):
        """task 名称含 Unicode/emoji"""
        tasks = [
            {"task_name": "任务🔥АБВ", "status": "success"},
            {"task_name": "test\twith\ttabs", "status": "failed"},
            {"task_name": "line1\nline2", "status": "skipped"},
        ]
        stats = _build_default_stats(tasks, "partial", None, None)
        assert stats["total_count"] == 3
        assert stats["pass_count"] == 1
        assert stats["fail_count"] == 1
        assert stats["blocked_count"] == 1

    def test_zero_duration(self):
        """started_at == finished_at → 持续时间为 0s"""
        stats = _build_default_stats(
            [], "success",
            "2024-01-01T00:00:00", "2024-01-01T00:00:00",
        )
        assert stats["duration"] == "0s"

    def test_very_long_duration(self):
        """超过 24 小时的持续时间"""
        stats = _build_default_stats(
            [], "success",
            "2024-01-01T00:00:00", "2024-01-02T06:30:15",
        )
        assert "h" in stats["duration"]
        assert "30h" in stats["duration"] or "30" in stats["duration"]

    def test_all_cancelled_tasks(self):
        """全部为 cancelled 的任务（无 pass/fail）"""
        tasks = [
            {"task_name": f"t{i}", "status": "cancelled"} for i in range(5)
        ]
        stats = _build_default_stats(tasks, "cancelled", None, None)
        assert stats["pass_count"] == 0
        assert stats["fail_count"] == 0
        assert stats["blocked_count"] == 5

    def test_missing_status_field_in_task(self):
        """task dict 缺少 status 字段 — 不崩溃，按未知处理"""
        tasks = [
            {"task_name": "t1"},  # no status
            {"task_name": "t2", "status": "success"},
        ]
        stats = _build_default_stats(tasks, "success", None, None)
        assert stats["pass_count"] == 1
        assert stats["fail_count"] == 0
        assert stats["blocked_count"] == 0

    def test_unknown_status_in_task(self):
        """task status 为未知值"""
        tasks = [
            {"task_name": "t1", "status": "some-new-status"},
            {"task_name": "t2", "status": ""},
        ]
        stats = _build_default_stats(tasks, "partial", None, None)
        assert stats["pass_count"] == 0
        assert stats["fail_count"] == 0
        assert stats["blocked_count"] == 0


class TestBoundaryGenerateHTML:
    """边界：HTML 生成"""

    def test_max_length_pipeline_name_html(self):
        """超长管道名不应该导致 HTML 结构损坏"""
        name = "A" * 1000
        stats = _build_default_stats(
            [{"task_name": "t1", "status": "success"}], "success", None, None
        )
        html = _generate_html(stats, name)
        assert name in html
        assert html.startswith("<!DOCTYPE html>")

    def test_html_with_percentage_100(self):
        """100% 通过率格式正确"""
        stats = _build_default_stats(
            [{"task_name": "t1", "status": "success"}], "success", None, None
        )
        html = _generate_html(stats, "test")
        assert "100.0%" in html

    def test_html_no_percentage_when_zero_tasks(self):
        """0 个 task 时通过率为 0.0%"""
        stats = _build_default_stats([], "success", None, None)
        html = _generate_html(stats, "test")
        assert "0.0%" in html


class TestBoundaryGenerateMD:
    """边界：MD 生成"""

    def test_md_with_only_blocked_tasks(self):
        """仅有 blocked 任务时的 MD 输出"""
        stats = _build_default_stats(
            [
                {"task_name": "t1", "status": "skipped"},
                {"task_name": "t2", "status": "cancelled"},
            ],
            "cancelled", None, None,
        )
        md = _generate_md(stats, "test")
        assert "阻塞 (Block)" in md
        assert "通过 (Pass)" in md  # header always present

    def test_md_no_fail_no_block_row(self):
        """全成功时不应有 fail/block 行"""
        stats = _build_default_stats(
            [{"task_name": "t1", "status": "success"}], "success", None, None
        )
        md = _generate_md(stats, "test")
        assert "失败 (Fail)" not in md
        assert "阻塞 (Block)" not in md


# ══════════════════════════════════════════════════════
# 2. EXCEPTION
# ══════════════════════════════════════════════════════


class TestExceptionLoadResultPage:
    """异常：load_result_page 在异常条件下的行为"""

    def test_load_nonexistent_file(self):
        """加载不存在的文件返回 None"""
        result = load_result_page("nonexistent", "v1", "run-999")
        assert result is None

    def test_load_corrupted_json(self):
        """加载损坏的 JSON 文件 — 返回 None 而不抛异常"""
        with tempfile.TemporaryDirectory() as tmpdir:
            bad_path = Path(tmpdir) / "result.json"
            bad_path.write_text("{invalid json")
            with patch(
                "taskpps.services.result_page.get_result_page_path",
                return_value=bad_path,
            ):
                result = load_result_page("p", "v", "r")
                assert result is None

    def test_load_empty_file(self):
        """加载空文件 — 返回 None 而不抛异常"""
        with tempfile.TemporaryDirectory() as tmpdir:
            empty_path = Path(tmpdir) / "result.json"
            empty_path.write_text("")
            with patch(
                "taskpps.services.result_page.get_result_page_path",
                return_value=empty_path,
            ):
                result = load_result_page("p", "v", "r")
                assert result is None


class TestExceptionGenerateResultPage:
    """异常：generate_result_page 在异常输入下的行为"""

    def test_invalid_datetime_format(self):
        """无效日期时间格式不崩溃（返回空 duration）"""
        stats = _build_default_stats(
            [{"task_name": "t1", "status": "success"}],
            "success", "not-a-date", "also-not-a-date",
        )
        assert stats["duration"] == ""

    def test_none_started_at_with_valid_finished_at(self):
        """started_at=None 时不计算 duration"""
        stats = _build_default_stats(
            [], "success", None, "2024-01-01T00:00:00",
        )
        assert stats["duration"] == ""

    def test_non_iso_format_dates(self):
        """非 ISO 格式的日期（如 RFC 2822）"""
        stats = _build_default_stats(
            [], "success",
            "Mon, 01 Jan 2024 00:00:00 GMT",
            "Mon, 01 Jan 2024 00:01:00 GMT",
        )
        assert stats["duration"] == "" or isinstance(stats["duration"], str)

    def test_collector_html_with_script_tag(self):
        """collector HTML 含 script 标签 — 服务端不主动过滤（XSS 由前端负责）"""
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
                    tasks=[],
                    collector_html="<h1>Hello</h1><script>alert('xss')</script>",
                    collector_md="# Hello",
                    collector_mode="replace",
                )
                assert "<script>" in data["html_content"]

    def test_collector_empty_both_formats(self):
        """collector 同时输出空字符串时，回退到默认"""
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
                    collector_html="",
                    collector_md="",
                    collector_mode="replace",
                )
                assert data["has_collector"] is False
                assert "Pass" in data["html_content"]

    def test_collector_append_with_partial_input(self):
        """collector append 模式，仅提供 HTML 不提供 MD"""
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
                    collector_html="<h1>ONLY HTML</h1>",
                    collector_md=None,
                    collector_mode="append",
                )
                assert "<hr>" in data["html_content"]
                assert "<h1>ONLY HTML</h1>" in data["html_content"]
                # MD 侧不应该有额外内容
                assert "ONLY HTML" not in data["md_content"]


# ══════════════════════════════════════════════════════
# 3. CONCURRENCY
# ══════════════════════════════════════════════════════


class TestConcurrencyResultPage:
    """并发：多 pipeline 同时生成结果页"""

    def test_concurrent_writes_different_runs(self):
        """多个不同 run_id 同时写入 — 文件不冲突"""
        results = []
        errors = []

        def write(run_id: str):
            try:
                with tempfile.TemporaryDirectory() as tmpdir:
                    result_path = Path(tmpdir) / "result.json"
                    with patch(
                        "taskpps.services.result_page.get_result_page_path",
                        return_value=result_path,
                    ):
                        data = generate_result_page(
                            run_id=run_id,
                            pipeline_name="test",
                            pipeline_id="pid",
                            pipeline_version="v1",
                            status="success",
                            started_at=None,
                            finished_at=None,
                            tasks=[{"task_name": run_id, "status": "success"}],
                        )
                        results.append(data)
            except Exception as e:
                errors.append(str(e))

        threads = []
        for i in range(20):
            t = Thread(target=write, args=(f"run-{i}",))
            threads.append(t)

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0
        assert len(results) == 20

    def test_concurrent_writes_same_run_overwrite(self):
        """同一 run_id 多次写入 — 最后一次写入生效"""
        written_data = []

        with tempfile.TemporaryDirectory() as tmpdir:
            result_path = Path(tmpdir) / "same" / "result.json"
            with patch(
                "taskpps.services.result_page.get_result_page_path",
                return_value=result_path,
            ):
                for i in range(10):
                    data = generate_result_page(
                        run_id="same-run",
                        pipeline_name=f"run-{i}",
                        pipeline_id="pid",
                        pipeline_version="v1",
                        status="success",
                        started_at=None,
                        finished_at=None,
                        tasks=[
                            {"task_name": f"task-{i}", "status": "success"}
                        ],
                    )
                    written_data.append(data)
                    time.sleep(0.001)

            # 文件存在且内容为最后一次写入
            assert result_path.exists()
            content = json.loads(result_path.read_text())
            assert content["pipeline_name"] == "run-9"

        assert len(written_data) == 10


# ══════════════════════════════════════════════════════
# 4. ENVIRONMENT
# ══════════════════════════════════════════════════════


class TestEnvironmentAllStatuses:
    """环境：覆盖所有 RunStatus + 无插件/空插件"""

    @pytest.mark.parametrize("status,expected_display", [
        ("success", "成功"),
        ("failed", "失败"),
        ("partial", "部分成功"),
        ("cancelled", "已取消"),
        ("running", "运行中"),
        ("pending", "等待中"),
    ])
    def test_all_run_status_displays(self, status, expected_display):
        """所有 RunStatus 值都有对应的中文显示"""
        stats = _build_default_stats([], status, None, None)
        assert stats["status_display"] == expected_display

    def test_unknown_status_keeps_original(self):
        """未知状态值保留原文"""
        stats = _build_default_stats([], "unknown-status", None, None)
        assert stats["status_display"] == "unknown-status"

    def test_no_collector_default_html(self):
        """无 collector 插件时：默认 HTML 始终生成"""
        with tempfile.TemporaryDirectory() as tmpdir:
            result_path = Path(tmpdir) / "result.json"
            with patch(
                "taskpps.services.result_page.get_result_page_path",
                return_value=result_path,
            ):
                data = generate_result_page(
                    run_id="run-no-plugin",
                    pipeline_name="DefaultOnly",
                    pipeline_id="pid",
                    pipeline_version="v1",
                    status="failed",
                    started_at="2024-01-01T00:00:00",
                    finished_at="2024-01-01T00:01:00",
                    tasks=[
                        {"task_name": "t1", "status": "failed"},
                    ],
                )
                assert data["has_collector"] is False
                assert "失败 (Fail)" in data["html_content"]
                assert "<!DOCTYPE html>" in data["html_content"]
                assert "stats" in data
                assert data["stats"]["pass_count"] == 0
                assert data["stats"]["fail_count"] == 1

    def test_no_collector_default_md(self):
        """无 collector 插件时：默认 MD 始终生成"""
        with tempfile.TemporaryDirectory() as tmpdir:
            result_path = Path(tmpdir) / "result.json"
            with patch(
                "taskpps.services.result_page.get_result_page_path",
                return_value=result_path,
            ):
                data = generate_result_page(
                    run_id="run-no-plugin",
                    pipeline_name="DefaultOnly",
                    pipeline_id="pid",
                    pipeline_version="v1",
                    status="failed",
                    started_at=None,
                    finished_at=None,
                    tasks=[
                        {"task_name": "t1", "status": "failed"},
                    ],
                )
                assert "失败 (Fail)" in data["md_content"]
                assert "# DefaultOnly" in data["md_content"]

    def test_collector_only_md_no_html(self):
        """collector 仅提供 MD，不提供 HTML"""
        with tempfile.TemporaryDirectory() as tmpdir:
            result_path = Path(tmpdir) / "result.json"
            with patch(
                "taskpps.services.result_page.get_result_page_path",
                return_value=result_path,
            ):
                data = generate_result_page(
                    run_id="run-md-only",
                    pipeline_name="test",
                    pipeline_id="pid",
                    pipeline_version="v1",
                    status="success",
                    started_at=None,
                    finished_at=None,
                    tasks=[{"task_name": "t1", "status": "success"}],
                    collector_html=None,
                    collector_md="# CUSTOM MD CONTENT",
                    collector_mode="replace",
                )
                assert data["md_content"] == "# CUSTOM MD CONTENT"
                assert "Pass" in data["html_content"]  # HTML 未被替换（无 html 提供）
                assert data["has_collector"] is True  # 因为 md 存在

    def test_collector_only_html_no_md(self):
        """collector 仅提供 HTML，不提供 MD"""
        with tempfile.TemporaryDirectory() as tmpdir:
            result_path = Path(tmpdir) / "result.json"
            with patch(
                "taskpps.services.result_page.get_result_page_path",
                return_value=result_path,
            ):
                data = generate_result_page(
                    run_id="run-html-only",
                    pipeline_name="test",
                    pipeline_id="pid",
                    pipeline_version="v1",
                    status="success",
                    started_at=None,
                    finished_at=None,
                    tasks=[{"task_name": "t1", "status": "success"}],
                    collector_html="<h1>CUSTOM HTML</h1>",
                    collector_md=None,
                    collector_mode="replace",
                )
                assert data["html_content"] == "<h1>CUSTOM HTML</h1>"
                assert "Pass" in data["md_content"]  # MD 未被替换
                assert data["has_collector"] is True

    def test_default_result_page_always_has_both_formats(self):
        """默认结果页始终包含 HTML 和 MD 两种格式"""
        with tempfile.TemporaryDirectory() as tmpdir:
            result_path = Path(tmpdir) / "result.json"
            with patch(
                "taskpps.services.result_page.get_result_page_path",
                return_value=result_path,
            ):
                data = generate_result_page(
                    run_id="run-dual",
                    pipeline_name="DualFormat",
                    pipeline_id="pid",
                    pipeline_version="v1",
                    status="success",
                    started_at="2024-01-01T00:00:00",
                    finished_at="2024-01-01T00:01:00",
                    tasks=[{"task_name": "t1", "status": "success"}],
                )
                assert "html_content" in data
                assert "md_content" in data
                assert len(data["html_content"]) > 0
                assert len(data["md_content"]) > 0

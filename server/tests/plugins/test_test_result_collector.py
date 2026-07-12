"""TestResultCollector 插件单元测试"""

from __future__ import annotations

import importlib.util
import json
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

script_path = (
    Path(__file__).resolve().parent.parent.parent.parent
    / "official_plugins"
    / "test_result_collector"
    / "test_result_collector.py"
)
spec = importlib.util.spec_from_file_location("_trc_test", str(script_path))
_trc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(_trc)


class TestApplyRule:
    def test_last_match(self):
        rule = {"regex": r"(\d+) passed", "target": "passed"}
        log = "1 passed, 5 passed, 42 passed"
        assert _trc._apply_rule(rule, log) == "42"

    def test_first_match(self):
        rule = {"regex": r"(\d+) passed", "target": "passed", "match": "first"}
        log = "1 passed, 5 passed, 42 passed"
        assert _trc._apply_rule(rule, log) == "1"

    def test_sum_match(self):
        rule = {"regex": r"(\d+) passed", "target": "passed", "match": "sum"}
        log = "1 passed, 5 passed, 42 passed"
        assert _trc._apply_rule(rule, log) == "48"

    def test_nth_match(self):
        rule = {"regex": r"(\d+) passed", "target": "passed", "match": "nth:2"}
        log = "1 passed, 5 passed, 42 passed"
        assert _trc._apply_rule(rule, log) == "5"

    def test_no_match(self):
        rule = {"regex": r"(\d+) passed", "target": "passed"}
        log = "no results here"
        assert _trc._apply_rule(rule, log) is None

    def test_default_match_is_last(self):
        rule = {"regex": r"(\d+) failed", "target": "failed"}
        log = "1 failed, 3 failed, 0 failed"
        assert _trc._apply_rule(rule, log) == "0"

    def test_pytest_summary_line(self):
        rule = {"regex": r"(\d+) passed", "target": "passed"}
        log = "collected 46 items\n\ntest_a.py::test_x PASSED\ntest_b.py::test_y PASSED\n\n======= 42 passed, 3 failed, 1 warning in 2.3s ======="
        assert _trc._apply_rule(rule, log) == "42"

    def test_complex_regex(self):
        rule = {"regex": r"Report: (https?://[^\s>]+)", "target": "report_url"}
        log = "Output: /tmp/output.xml\nReport: http://reports.example.com/run/12345\n"
        assert _trc._apply_rule(rule, log) == "http://reports.example.com/run/12345"


class TestApplyRules:
    def test_multiple_rules(self):
        rules = [
            {"regex": r"(\d+) passed", "target": "passed"},
            {"regex": r"(\d+) failed", "target": "failed"},
        ]
        log = "42 passed, 3 failed"
        result = _trc.apply_rules(rules, log)
        assert result == {"passed": "42", "failed": "3"}

    def test_partial_match(self):
        rules = [
            {"regex": r"(\d+) passed", "target": "passed"},
            {"regex": r"(\d+) errored", "target": "errored"},
        ]
        log = "42 passed, 3 failed"
        result = _trc.apply_rules(rules, log)
        assert result["passed"] == "42"
        assert result["errored"] is None


class TestCleanValue:
    def test_int_conversion(self):
        assert _trc._clean_value("42", "int") == 42

    def test_int_default_on_none(self):
        assert _trc._clean_value(None, "int") == 0

    def test_int_default_on_invalid(self):
        assert _trc._clean_value("abc", "int") == 0

    def test_float_conversion(self):
        assert _trc._clean_value("3.14", "float") == 3.14

    def test_float_default_on_none(self):
        assert _trc._clean_value(None, "float") == 0.0

    def test_string_conversion(self):
        assert _trc._clean_value("hello", "string") == "hello"

    def test_string_default_on_none(self):
        assert _trc._clean_value(None, "string") == "-"


class TestCleanRow:
    def test_cleans_all_fields(self):
        raw = {"passed": "42", "failed": "3", "task_name": "test"}
        type_map = {"passed": "int", "failed": "int"}
        cleaned = _trc.clean_row(raw, type_map)
        assert cleaned["passed"] == 42
        assert cleaned["failed"] == 3
        assert cleaned["task_name"] == "test"

    def test_default_type_is_string(self):
        raw = {"custom_field": "abc"}
        cleaned = _trc.clean_row(raw, {})
        assert cleaned["custom_field"] == "abc"


class TestMergeRules:
    def test_append_objects(self):
        template = [
            {"regex": r"(\d+) passed", "target": "passed"},
            {"regex": r"(\d+) failed", "target": "failed"},
        ]
        custom = [
            {"regex": r"(\d+) warnings", "target": "warnings"},
        ]
        merged = _trc.merge_rules(template, custom)
        assert len(merged) == 3
        assert merged[-1]["target"] == "warnings"

    def test_remove_by_string(self):
        template = [
            {"regex": r"(\d+) passed", "target": "passed"},
            {"regex": r"(\d+) failed", "target": "failed"},
            {"regex": r"(\d+) warnings", "target": "warnings"},
        ]
        custom = ["warnings"]
        merged = _trc.merge_rules(template, custom)
        assert len(merged) == 2
        targets = [r["target"] for r in merged]
        assert "warnings" not in targets

    def test_remove_and_add(self):
        template = [
            {"regex": r"(\d+) passed", "target": "passed"},
            {"regex": r"(\d+) failed", "target": "failed"},
            {"regex": r"(\d+) warnings", "target": "warnings"},
        ]
        custom = [
            "warnings",
            {"regex": r"(\d+) errored", "target": "error"},
        ]
        merged = _trc.merge_rules(template, custom)
        targets = [r["target"] for r in merged]
        assert targets == ["passed", "failed", "error"]

    def test_empty_custom(self):
        template = [{"regex": r"(\d+) passed", "target": "passed"}]
        merged = _trc.merge_rules(template, [])
        assert merged == template

    def test_no_template(self):
        custom = [{"regex": r"(\d+) passed", "target": "passed"}]
        merged = _trc.merge_rules([], custom)
        assert merged == [{"regex": r"(\d+) passed", "target": "passed"}]


class TestMergeClean:
    def test_removes_clean_for_removed_targets(self):
        template = [
            {"target": ["passed", "failed"], "type": "int"},
            {"target": ["duration"], "type": "string"},
        ]
        custom = []
        merged = _trc.merge_clean(template, custom, {"duration"})
        assert len(merged) == 1
        assert merged[0]["target"] == ["passed", "failed"]

    def test_appends_custom(self):
        template = [{"target": ["passed"], "type": "int"}]
        custom = [{"target": ["error"], "type": "int"}]
        merged = _trc.merge_clean(template, custom, set())
        assert len(merged) == 2
        assert merged[-1]["target"] == ["error"]


class TestMergeSummary:
    def test_removes_fields_for_removed_targets(self):
        template = {
            "rows": [
                {"label": "合计", "passed": "sum", "failed": "sum", "warnings": "sum"},
            ]
        }
        merged = _trc.merge_summary(template, None, {"warnings"})
        row = merged["rows"][0]
        assert "warnings" not in row
        assert "passed" in row
        assert "failed" in row

    def test_removes_row_when_all_fields_removed(self):
        template = {
            "rows": [
                {"label": "警告统计", "warnings": "sum"},
            ]
        }
        merged = _trc.merge_summary(template, None, {"warnings"})
        assert len(merged["rows"]) == 0

    def test_appends_custom(self):
        template = {
            "rows": [{"label": "合计", "passed": "sum"}]
        }
        custom = {
            "rows": [{"label": "通过率", "pass_rate": "sum(passed) / sum(total) * 100"}]
        }
        merged = _trc.merge_summary(template, custom, set())
        assert len(merged["rows"]) == 2
        assert merged["rows"][1]["label"] == "通过率"


class TestComputeSummary:
    def test_sum_aggregation(self):
        rows = [
            {"task_name": "a", "passed": 42, "failed": 3},
            {"task_name": "b", "passed": 18, "failed": 1},
        ]
        config = {
            "rows": [
                {"label": "合计", "passed": "sum", "failed": "sum"},
            ]
        }
        result = _trc.compute_summary(rows, config)
        assert result[0]["passed"] == 60
        assert result[0]["failed"] == 4

    def test_sum_with_missing_values(self):
        rows = [
            {"task_name": "a", "passed": 42},
            {"task_name": "b", "passed": 0},  # default value
        ]
        config = {
            "rows": [{"label": "合计", "passed": "sum"}]
        }
        result = _trc.compute_summary(rows, config)
        assert result[0]["passed"] == 42

    def test_expression_eval(self):
        rows = [
            {"task_name": "a", "passed": 42, "total": 46},
            {"task_name": "b", "passed": 18, "total": 18},
        ]
        config = {
            "rows": [
                {"label": "通过率", "rate": "sum(passed) / sum(total) * 100"},
            ]
        }
        result = _trc.compute_summary(rows, config)
        assert abs(result[0]["rate"] - 93.75) < 0.01

    def test_empty_rows(self):
        config = {"rows": [{"label": "合计", "passed": "sum"}]}
        result = _trc.compute_summary([], config)
        assert result[0]["passed"] == 0

    def test_avg_function(self):
        rows = [
            {"task_name": "a", "duration": 2.3},
            {"task_name": "b", "duration": 5.7},
        ]
        config = {"rows": [{"label": "平均", "avg_d": "avg(duration)"}]}
        result = _trc.compute_summary(rows, config)
        assert abs(result[0]["avg_d"] - 4.0) < 0.01


class TestBuildColumns:
    def test_default_order(self):
        rules = [
            {"regex": r"(\d+) passed", "target": "passed"},
            {"regex": r"(\d+) failed", "target": "failed"},
        ]
        cols = _trc.build_columns(rules)
        assert cols == ["Task", "passed", "failed"]

    def test_explicit_idx(self):
        rules = [
            {"regex": r"(\d+) failed", "target": "failed", "idx": 2},
            {"regex": r"(\d+) passed", "target": "passed", "idx": 1},
            {"regex": r"(\d+) total", "target": "total", "idx": 3},
        ]
        cols = _trc.build_columns(rules)
        assert cols == ["Task", "passed", "failed", "total"]

    def test_same_idx_preserves_order(self):
        rules = [
            {"regex": r"(\d+) failed", "target": "failed", "idx": 1},
            {"regex": r"(\d+) passed", "target": "passed", "idx": 1},
        ]
        cols = _trc.build_columns(rules)
        assert cols == ["Task", "failed", "passed"]

    def test_mixed_idx_and_default(self):
        rules = [
            {"regex": r"(\d+) failed", "target": "failed"},  # default idx 999
            {"regex": r"(\d+) passed", "target": "passed", "idx": 1},
        ]
        cols = _trc.build_columns(rules)
        assert cols == ["Task", "passed", "failed"]

    def test_include_summary_columns(self):
        rules = [
            {"regex": r"(\d+) passed", "target": "passed"},
            {"regex": r"(\d+) failed", "target": "failed"},
        ]
        summary = {"rows": [{"label": "通过率", "pass_rate": "sum(passed) / sum(total) * 100"}]}
        cols = _trc.build_columns(rules, summary)
        assert cols == ["Task", "passed", "failed", "pass_rate"]


class TestRenderMarkdown:
    def test_basic_table(self):
        columns = ["Task", "passed", "failed"]
        rows = [
            {"task_name": "unit-test", "passed": 42, "failed": 3},
            {"task_name": "integration", "passed": 18, "failed": 1},
        ]
        summary = [
            {"label": "合计", "passed": 60, "failed": 4},
        ]
        output = _trc.render_markdown(columns, rows, summary)
        assert "| Task | passed | failed |" in output
        assert "| unit-test | 42 | 3 |" in output
        assert "| **合计** | **60** | **4** |" in output

    def test_empty_rows(self):
        columns = ["Task", "passed"]
        rows: list[dict] = []
        summary: list[dict] = []
        output = _trc.render_markdown(columns, rows, summary)
        assert "| Task | passed |" in output
        assert "|------|------|" in output


class TestRenderJson:
    def test_basic_json(self):
        columns = ["Task", "passed"]
        rows = [{"task_name": "test", "passed": 42}]
        summary = [{"label": "合计", "passed": 42}]
        output = _trc.render_json(columns, rows, summary)
        data = json.loads(output)
        assert data["columns"] == columns
        assert data["rows"] == rows
        assert data["summary"] == summary


class TestPytestTemplate:
    def test_template_rules_are_valid(self):
        rules = _trc.PYTEST_TEMPLATE["rules"]
        assert len(rules) > 0
        for rule in rules:
            assert "regex" in rule
            assert "target" in rule

    def test_template_clean_is_valid(self):
        clean = _trc.PYTEST_TEMPLATE["clean"]
        for c in clean:
            assert "target" in c
            assert "type" in c

    def test_parse_pytest_output(self):
        log = (
            "collected 46 items\n"
            "test_a.py::test_x PASSED\n"
            "test_b.py::test_y FAILED\n"
            "======= 42 passed, 3 failed, 1 warning in 2.3s ======="
        )
        rules = _trc.PYTEST_TEMPLATE["rules"]
        result = _trc.apply_rules(rules, log)
        assert result["passed"] == "42"
        assert result["failed"] == "3"
        assert result["warnings"] == "1"
        assert result["duration"] == "2.3s"


class TestRobotFrameworkTemplate:
    def test_parse_rf_output_new_format(self):
        log = (
            "Example.Main                                                          | FAIL |\n"
            "================================================================================\n"
            "3 tests, 0 passed, 3 failed\n"
            "================================================================================\n"
            "Output:  /home/admin/workdir/AutomationTestTool-RF/_Reports/example/output.xml\n"
            "Log:     /home/admin/workdir/AutomationTestTool-RF/_Reports/example/log.html\n"
            "Report:  /home/admin/workdir/AutomationTestTool-RF/_Reports/example/report.html\n"
        )
        rules = _trc.ROBOTFRAMEWORK_TEMPLATE["rules"]
        result = _trc.apply_rules(rules, log)
        assert result["passed"] == "0"
        assert result["failed"] == "3"
        assert result["total"] == "3"
        assert result["report_url"] == "/home/admin/workdir/AutomationTestTool-RF/_Reports/example/report.html"

    def test_parse_rf_output_multiple_suites(self):
        log = (
            "Suite1 :: Test1                                                       | PASS |\n"
            "Suite1                                                                | FAIL |\n"
            "2 tests, 1 passed, 1 failed\n"
            "==============================================================================\n"
            "Suite2 :: Test2                                                       | FAIL |\n"
            "Suite2                                                                | FAIL |\n"
            "3 tests, 0 passed, 3 failed\n"
            "==============================================================================\n"
        )
        rules = _trc.ROBOTFRAMEWORK_TEMPLATE["rules"]
        result = _trc.apply_rules(rules, log)
        assert result["passed"] == "0"
        assert result["failed"] == "3"
        assert result["total"] == "3"


class TestPluginCommand:
    def test_build_command(self):
        plugin_path = (
            Path(__file__).resolve().parent.parent.parent.parent
            / "official_plugins"
            / "test_result_collector"
            / "plugin.py"
        )
        spec = importlib.util.spec_from_file_location("_trc_plugin_test", str(plugin_path))
        plugin_module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(plugin_module)

        plugin = plugin_module.TestResultCollectorPlugin(
            output_format="markdown",
            template="pytest",
            rules=["warnings", {"regex": r"(\d+) errored", "target": "error"}],
            clean=[{"target": ["error"], "type": "int"}],
            summary={"rows": [{"label": "总错误", "error": "sum"}]},
        )

        cmd = plugin.build_command()
        assert "python3" in cmd
        assert "test_result_collector.py" in cmd
        assert ".json" in cmd

    def test_build_command_default_params(self):
        plugin_path = (
            Path(__file__).resolve().parent.parent.parent.parent
            / "official_plugins"
            / "test_result_collector"
            / "plugin.py"
        )
        spec = importlib.util.spec_from_file_location("_trc_plugin_test2", str(plugin_path))
        plugin_module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(plugin_module)

        plugin = plugin_module.TestResultCollectorPlugin()
        cmd = plugin.build_command()
        assert "markdown" in cmd or ".json" in cmd

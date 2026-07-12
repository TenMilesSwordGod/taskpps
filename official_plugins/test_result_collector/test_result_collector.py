#!/usr/bin/env python3
"""TestResultCollector 核心脚本 —— 从任务控制台日志中提取测试结果并输出格式化表格。

数据来源：每个 task 的 task.log（控制台输出）
上下文输入：环境变量 TASKPPS_* + config JSON 文件
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path
from typing import Any

# ── 预置模板 ──────────────────────────────────────────

PYTEST_TEMPLATE: dict[str, Any] = {
    "rules": [
        {"regex": r"(\d+) passed", "target": "passed", "match": "last"},
        {"regex": r"(\d+) failed", "target": "failed", "match": "last"},
        {"regex": r"(\d+) warnings?", "target": "warnings", "match": "last"},
        {"regex": r"in ([\d.]+[sm])", "target": "duration", "match": "last"},
    ],
    "clean": [
        {"target": ["passed", "failed", "warnings"], "type": "int"},
        {"target": ["duration"], "type": "string"},
    ],
    "summary": {
        "rows": [
            {"label": "合计", "passed": "sum", "failed": "sum", "warnings": "sum"},
        ]
    },
}

ROBOTFRAMEWORK_TEMPLATE: dict[str, Any] = {
    "rules": [
        {"regex": r"(\d+) passed", "target": "passed", "match": "last"},
        {"regex": r"(\d+) failed", "target": "failed", "match": "last"},
        {"regex": r"(\d+) skipped", "target": "skipped", "match": "last"},
        {"regex": r"(\d+) tests?\b", "target": "total", "match": "last"},
        {"regex": r"(?:Report|Output):\s*(https?://[^\s>]+|/[^\s>]+)",
         "target": "report_url", "match": "last"},
    ],
    "clean": [
        {"target": ["passed", "failed", "skipped", "total"], "type": "int"},
        {"target": ["report_url"], "type": "string"},
    ],
    "summary": {
        "rows": [
            {
                "label": "合计",
                "passed": "sum",
                "failed": "sum",
                "skipped": "sum",
                "total": "sum",
            },
            {"label": "通过率", "pass_rate": "sum(passed) / sum(total) * 100"},
        ]
    },
}

TEMPLATES: dict[str, dict[str, Any]] = {
    "pytest": PYTEST_TEMPLATE,
    "robotframework": ROBOTFRAMEWORK_TEMPLATE,
}

# ── 缺省值 ────────────────────────────────────────────

DEFAULTS: dict[str, Any] = {
    "int": 0,
    "float": 0.0,
    "string": "-",
}

MAX_LOG_LINES = 500

# ── 模板合并 ──────────────────────────────────────────

def merge_rules(
    template_rules: list[dict],
    custom_rules: list[Any],
) -> list[dict]:
    if not custom_rules:
        return list(template_rules)

    remove_targets = {item for item in custom_rules if isinstance(item, str)}

    merged = [r for r in template_rules if r["target"] not in remove_targets]

    for item in custom_rules:
        if isinstance(item, dict):
            merged.append(item)

    return merged


def merge_clean(
    template_clean: list[dict],
    custom_clean: list[dict],
    removed_targets: set[str],
) -> list[dict]:
    result: list[dict] = []
    for c in template_clean:
        targets = [t for t in c["target"] if t not in removed_targets]
        if targets:
            result.append({"target": targets, "type": c["type"]})

    if custom_clean:
        result.extend(custom_clean)

    return result


def merge_summary(
    template_summary: dict[str, Any] | None,
    custom_summary: dict[str, Any] | None,
    removed_targets: set[str],
) -> dict[str, Any]:
    result_rows: list[dict] = []
    if template_summary:
        for row in template_summary.get("rows", []):
            new_row: dict[str, Any] = {"label": row["label"]}
            for key, val in row.items():
                if key == "label":
                    continue
                if key not in removed_targets:
                    new_row[key] = val
            if len(new_row) > 1:  # 有除 label 之外的字段
                result_rows.append(new_row)

    if custom_summary:
        result_rows.extend(custom_summary.get("rows", []))

    return {"rows": result_rows}


# ── 规则匹配 ──────────────────────────────────────────

DEFAULT_MATCH = "last"


def _apply_rule(rule: dict, log_text: str) -> Any | None:
    regex = rule["regex"]
    match_strategy = rule.get("match", DEFAULT_MATCH)
    matches = re.findall(regex, log_text, re.IGNORECASE)

    if not matches:
        return None

    if match_strategy == "first":
        return matches[0]
    elif match_strategy == "last":
        return matches[-1]
    elif match_strategy == "sum":
        try:
            ivals = [int(m) for m in matches]
            return str(sum(ivals))
        except ValueError:
            try:
                fvals = [float(m) for m in matches]
                return str(sum(fvals))
            except ValueError:
                return None
    elif match_strategy.startswith("nth:"):
        try:
            n = int(match_strategy.split(":")[1])
            if 1 <= n <= len(matches):
                return matches[n - 1]
        except (ValueError, IndexError):
            pass
        return None
    return matches[-1]


def apply_rules(rules: list[dict], log_text: str) -> dict[str, Any | None]:
    result: dict[str, Any | None] = {}
    for rule in rules:
        raw = _apply_rule(rule, log_text)
        result[rule["target"]] = raw
    return result


# ── 数据清洗 ──────────────────────────────────────────

def _clean_value(value: Any | None, target_type: str) -> Any:
    if value is None:
        return DEFAULTS.get(target_type, "-")

    if target_type == "int":
        try:
            return int(value)
        except (ValueError, TypeError):
            return DEFAULTS["int"]
    elif target_type == "float":
        try:
            return float(value)
        except (ValueError, TypeError):
            return DEFAULTS["float"]
    elif target_type == "string":
        return str(value)
    return value


def build_type_map(clean_rules: list[dict]) -> dict[str, str]:
    type_map: dict[str, str] = {}
    for c in clean_rules:
        for target in c["target"]:
            type_map[target] = c["type"]
    return type_map


def clean_row(raw: dict[str, Any | None], type_map: dict[str, str]) -> dict[str, Any]:
    cleaned: dict[str, Any] = {}
    for target, raw_value in raw.items():
        target_type = type_map.get(target, "string")
        cleaned[target] = _clean_value(raw_value, target_type)
    return cleaned


# ── 汇总计算 ──────────────────────────────────────────

ALLOWED_FUNCTIONS = {"sum", "avg", "min", "max", "count"}


def _build_aggregated(rows: list[dict]) -> dict[str, list]:
    aggregated: dict[str, list] = {}
    for row in rows:
        for target, value in row.items():
            if target == "task_name":
                continue
            if target not in aggregated:
                aggregated[target] = []
            aggregated[target].append(value)
    return aggregated


def _safe_eval(expr: str, aggregated: dict[str, list]) -> Any:
    safe_dict: dict[str, Any] = {}
    safe_dict.update(aggregated)

    def _sum(items: list) -> float:
        vals = [v for v in items if isinstance(v, (int, float))]
        return sum(vals) if vals else 0.0

    def _avg(items: list) -> float:
        vals = [v for v in items if isinstance(v, (int, float))]
        return sum(vals) / len(vals) if vals else 0.0

    def _min(items: list) -> float:
        vals = [v for v in items if isinstance(v, (int, float))]
        return min(vals) if vals else 0.0

    def _max(items: list) -> float:
        vals = [v for v in items if isinstance(v, (int, float))]
        return max(vals) if vals else 0.0

    def _count(items: list) -> int:
        return len([v for v in items if v not in (None, "-", "", 0)])

    safe_dict["sum"] = _sum
    safe_dict["avg"] = _avg
    safe_dict["min"] = _min
    safe_dict["max"] = _max
    safe_dict["count"] = _count

    try:
        return eval(expr, {"__builtins__": {}}, safe_dict)
    except Exception:
        return "-"


def compute_summary(
    rows: list[dict],
    summary_config: dict[str, Any],
) -> list[dict]:
    aggregated = _build_aggregated(rows)

    result_rows: list[dict] = []
    for row_config in summary_config.get("rows", []):
        result_row: dict[str, Any] = {"label": row_config["label"]}
        for key, val in row_config.items():
            if key == "label":
                continue
            if val == "sum":
                vals = [
                    v for v in aggregated.get(key, [])
                    if isinstance(v, (int, float))
                ]
                result_row[key] = sum(vals) if vals else 0
            else:
                result_row[key] = _safe_eval(str(val), aggregated)
        result_rows.append(result_row)
    return result_rows


# ── 列顺序 ────────────────────────────────────────────

def build_columns(rules: list[dict], summary_config: dict[str, Any] | None = None) -> list[str]:
    columns: list[str] = ["Task"]

    for i, rule in enumerate(rules):
        rule["_order"] = (rule.get("idx", 999), i)

    sorted_rules = sorted(rules, key=lambda r: r["_order"])

    for rule in sorted_rules:
        target = rule.get("target", "")
        if target and target not in columns:
            columns.append(target)

    if summary_config:
        for row in summary_config.get("rows", []):
            for key in row:
                if key != "label" and key not in columns:
                    columns.append(key)

    return columns


# ── 日志发现 ──────────────────────────────────────────

def discover_task_logs(env: dict[str, str]) -> list[dict]:
    logs_dir = Path(env["TASKPPS_LOGS_DIR"])
    pipeline_id = env["TASKPPS_PIPELINE_ID"]
    pipeline_version = env["TASKPPS_PIPELINE_VERSION"]
    run_id = env["TASKPPS_RUN_ID"]
    self_task = env["TASKPPS_TASK_ID"]

    base_dir = logs_dir / pipeline_id / f"v_{pipeline_version}" / "builds" / run_id
    if not base_dir.exists():
        return []

    tasks: list[dict] = []
    for task_dir in sorted(base_dir.iterdir()):
        if not task_dir.is_dir():
            continue
        task_name = task_dir.name
        if task_name == self_task:
            continue
        log_file = task_dir / "task.log"
        if log_file.exists():
            tasks.append({"task_name": task_name, "log_path": str(log_file)})

    return tasks


def read_log_last_lines(log_path: str, max_lines: int) -> str:
    try:
        with open(log_path, encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
            if len(lines) > max_lines:
                return "".join(lines[-max_lines:])
            return "".join(lines)
    except Exception:
        return ""


# ── 渲染 ──────────────────────────────────────────────

def render_markdown(
    columns: list[str],
    rows: list[dict],
    summary_rows: list[dict],
) -> str:
    lines: list[str] = []
    lines.append("| " + " | ".join(columns) + " |")
    lines.append("|" + "|".join(["------"] * len(columns)) + "|")

    for row in rows:
        vals: list[str] = []
        for c in columns:
            if c == "Task":
                vals.append(str(row.get("task_name", "-")))
            else:
                v = row.get(c, "-")
                vals.append(str(v))
        lines.append("| " + " | ".join(vals) + " |")

    for row in summary_rows:
        vals = []
        for c in columns:
            if c == "Task":
                vals.append("**" + str(row.get("label", "")) + "**")
            else:
                v = row.get(c, "-")
                vals.append("**" + str(v) + "**")
        lines.append("| " + " | ".join(vals) + " |")

    return "\n".join(lines)


def render_json(
    columns: list[str],
    rows: list[dict],
    summary_rows: list[dict],
) -> str:
    return json.dumps(
        {
            "columns": columns,
            "rows": rows,
            "summary": summary_rows,
        },
        ensure_ascii=False,
        indent=2,
        default=str,
    )


def render_html(
    columns: list[str],
    rows: list[dict],
    summary_rows: list[dict],
) -> str:
    parts: list[str] = ["<table>"]
    parts.append(
        "<thead><tr>" + "".join(f"<th>{c}</th>" for c in columns) + "</tr></thead>"
    )
    parts.append("<tbody>")

    for row in rows:
        tds = []
        for c in columns:
            if c == "Task":
                tds.append(f"<td>{row.get('task_name', '-')}</td>")
            else:
                tds.append(f"<td>{row.get(c, '-')}</td>")
        parts.append("<tr>" + "".join(tds) + "</tr>")

    for row in summary_rows:
        tds = []
        for c in columns:
            if c == "Task":
                tds.append(f"<td><strong>{row.get('label', '')}</strong></td>")
            else:
                tds.append(f"<td><strong>{row.get(c, '-')}</strong></td>")
        parts.append("<tr>" + "".join(tds) + "</tr>")

    parts.append("</tbody></table>")
    return "\n".join(parts)


# ── 主函数 ────────────────────────────────────────────

OUTPUT_MARKER_START = "---TRC_OUTPUT_START---"
OUTPUT_MARKER_END = "---TRC_OUTPUT_END---"


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: test_result_collector.py <config_file>", file=sys.stderr)
        sys.exit(1)

    config_path = sys.argv[1]
    with open(config_path) as f:
        config = json.load(f)

    env = {
        "TASKPPS_RUN_ID": os.environ.get("TASKPPS_RUN_ID", ""),
        "TASKPPS_PIPELINE_ID": os.environ.get("TASKPPS_PIPELINE_ID", ""),
        "TASKPPS_PIPELINE_VERSION": os.environ.get("TASKPPS_PIPELINE_VERSION", ""),
        "TASKPPS_LOGS_DIR": os.environ.get("TASKPPS_LOGS_DIR", ""),
        "TASKPPS_TASK_ID": os.environ.get("TASKPPS_TASK_ID", ""),
    }

    if not all(env.values()):
        print("Missing required environment variables", file=sys.stderr)
        sys.exit(1)

    template_name = config.get("template")
    template = TEMPLATES.get(template_name) if template_name else None

    custom_rules: list[Any] = config.get("rules", [])
    if template:
        rules = merge_rules(template.get("rules", []), custom_rules)
    else:
        rules = [r for r in custom_rules if isinstance(r, dict)]

    if not rules:
        print("No rules configured", file=sys.stderr)
        sys.exit(1)

    removed_targets = {item for item in custom_rules if isinstance(item, str)}

    custom_clean = config.get("clean", [])
    if template and template.get("clean"):
        clean_rules = merge_clean(template["clean"], custom_clean, removed_targets)
    else:
        clean_rules = custom_clean

    custom_summary = config.get("summary")
    if template and template.get("summary"):
        summary_config = merge_summary(
            template["summary"], custom_summary, removed_targets
        )
    elif custom_summary:
        summary_config = custom_summary
    else:
        summary_config = {"rows": []}

    columns = build_columns(rules, summary_config)

    type_map = build_type_map(clean_rules)

    tasks = discover_task_logs(env)

    rows: list[dict] = []
    for task in tasks:
        log_text = read_log_last_lines(task["log_path"], MAX_LOG_LINES)
        raw_values = apply_rules(rules, log_text)
        raw_values["task_name"] = task["task_name"]
        cleaned = clean_row(raw_values, type_map)
        rows.append(cleaned)

    rows = [r for r in rows if isinstance(r.get("total"), (int, float)) and r.get("total") > 0]

    summary_rows = compute_summary(rows, summary_config)

    output_format = config.get("output_format", "markdown")
    if output_format == "json":
        output = render_json(columns, rows, summary_rows)
    elif output_format == "html":
        output = render_html(columns, rows, summary_rows)
    else:
        output = render_markdown(columns, rows, summary_rows)

    print(OUTPUT_MARKER_START)
    print(output)
    print(OUTPUT_MARKER_END)


if __name__ == "__main__":
    main()

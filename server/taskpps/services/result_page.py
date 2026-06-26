from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from taskpps.config import get_logs_dir
from taskpps.models.run import RunStatus, TaskStatus

logger = logging.getLogger("taskpps.services.result_page")

DEFAULT_RESULT_FORMAT = "html"


def get_result_page_path(pipeline_id: str, pipeline_version: str, run_id: str) -> Path:
    logs_dir = get_logs_dir()
    v = pipeline_version or "unknown"
    return logs_dir / pipeline_id / f"v_{v}" / "builds" / run_id / "result.json"


def _build_default_stats(
    tasks: list[dict],
    status: str,
    started_at: str | None,
    finished_at: str | None,
) -> dict:
    pass_count = 0
    fail_count = 0
    blocked_count = 0
    for t in tasks:
        s = t.get("status", "")
        if s == TaskStatus.SUCCESS.value:
            pass_count += 1
        elif s == TaskStatus.FAILED.value:
            fail_count += 1
        elif s in (TaskStatus.SKIPPED.value, TaskStatus.CANCELLED.value):
            blocked_count += 1

    duration_str = ""
    if started_at and finished_at:
        try:
            start = datetime.fromisoformat(started_at.replace("Z", "+00:00"))
            end = datetime.fromisoformat(finished_at.replace("Z", "+00:00"))
        except (ValueError, TypeError):
            start = started_at
            end = finished_at

        if isinstance(start, datetime) and isinstance(end, datetime):
            delta = end - start
            total_seconds = int(delta.total_seconds())
            h, rem = divmod(total_seconds, 3600)
            m, s_val = divmod(rem, 60)
            parts = []
            if h > 0:
                parts.append(f"{h}h")
            if m > 0 or h > 0:
                parts.append(f"{m}m")
            parts.append(f"{s_val}s")
            duration_str = " ".join(parts)

    status_display = {
        RunStatus.SUCCESS.value: "成功",
        RunStatus.FAILED.value: "失败",
        RunStatus.PARTIAL.value: "部分成功",
        RunStatus.CANCELLED.value: "已取消",
        RunStatus.RUNNING.value: "运行中",
        RunStatus.PENDING.value: "等待中",
    }.get(status, status)

    return {
        "status": status,
        "status_display": status_display,
        "pass_count": pass_count,
        "fail_count": fail_count,
        "blocked_count": blocked_count,
        "total_count": len(tasks),
        "started_at": started_at,
        "finished_at": finished_at,
        "duration": duration_str,
    }


def _generate_html(stats: dict, pipeline_name: str) -> str:
    s = stats
    pass_c = s["pass_count"]
    fail_c = s["fail_count"]
    block_c = s["blocked_count"]
    total_c = s["total_count"]
    pass_pct = f"{(pass_c / max(total_c, 1) * 100):.1f}%"

    failed_row = ""
    if fail_c > 0:
        failed_row = f"""
        <tr>
            <td style="color:#ef4444;font-weight:600;">❌ 失败 (Fail)</td>
            <td style="text-align:right;">{fail_c}</td>
        </tr>"""
    blocked_row = ""
    if block_c > 0:
        blocked_row = f"""
        <tr>
            <td style="color:#f59e0b;font-weight:600;">⏸️ 阻塞 (Block)</td>
            <td style="text-align:right;">{block_c}</td>
        </tr>"""

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Pipeline Result - {pipeline_name}</title>
<style>
  body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; margin: 0; padding: 24px; background: #f9fafb; color: #1f2937; }}
  .card {{ background: #fff; border-radius: 8px; border: 1px solid #e5e7eb; padding: 24px; max-width: 640px; margin: 0 auto; box-shadow: 0 1px 3px rgba(0,0,0,0.05); }}
  h1 {{ font-size: 20px; margin: 0 0 4px 0; }}
  .status {{ display: inline-block; padding: 2px 10px; border-radius: 12px; font-size: 13px; font-weight: 600; margin-bottom: 16px; }}
  .status.success {{ background: #ecfdf5; color: #065f46; }}
  .status.failed {{ background: #fef2f2; color: #991b1b; }}
  .status.partial {{ background: #fffbeb; color: #92400e; }}
  .status.cancelled {{ background: #fff7ed; color: #9a3412; }}
  .status.running {{ background: #eff6ff; color: #1e40af; }}
  .status.pending {{ background: #f3f4f6; color: #374151; }}
  table {{ width: 100%; border-collapse: collapse; margin: 12px 0; }}
  th, td {{ padding: 8px 12px; text-align: left; border-bottom: 1px solid #f3f4f6; }}
  th {{ font-weight: 600; color: #6b7280; font-size: 12px; text-transform: uppercase; }}
  .time {{ color: #6b7280; font-size: 13px; margin-top: 16px; }}
  .summary-value {{ font-size: 24px; font-weight: 700; }}
  .summary-label {{ font-size: 12px; color: #6b7280; }}
  .summary-grid {{ display: flex; gap: 24px; margin: 16px 0; }}
  .summary-item {{ text-align: center; }}
  .divider {{ border-top: 1px solid #e5e7eb; margin: 16px 0; }}
</style>
</head>
<body>
<div class="card">
  <h1>{pipeline_name}</h1>
  <span class="status {s["status"]}">{s["status_display"]}</span>

  <div class="summary-grid">
    <div class="summary-item">
      <div class="summary-value" style="color:#10b981;">{pass_c}</div>
      <div class="summary-label">Pass</div>
    </div>
    <div class="summary-item">
      <div class="summary-value" style="color:#ef4444;">{fail_c}</div>
      <div class="summary-label">Fail</div>
    </div>
    <div class="summary-item">
      <div class="summary-value" style="color:#f59e0b;">{block_c}</div>
      <div class="summary-label">Block</div>
    </div>
    <div class="summary-item">
      <div class="summary-value" style="color:#3b82f6;">{pass_pct}</div>
      <div class="summary-label">通过率</div>
    </div>
  </div>

  <table>
    <tr><th>指标</th><th>数量</th></tr>
    <tr>
      <td style="color:#10b981;font-weight:600;">✅ 通过 (Pass)</td>
      <td style="text-align:right;">{pass_c}</td>
    </tr>{failed_row}{blocked_row}
    <tr style="font-weight:600;">
      <td>总计 (Total)</td>
      <td style="text-align:right;">{total_c}</td>
    </tr>
  </table>

  <div class="divider"></div>
  <div class="time">
    <div>⏱️ 耗时: {s["duration"]}</div>
    <div>🕐 开始: {s["started_at"] or "-"}</div>
    <div>🕐 结束: {s["finished_at"] or "-"}</div>
  </div>
</div>
</body>
</html>"""


def _generate_md(stats: dict, pipeline_name: str) -> str:
    s = stats
    pass_c = s["pass_count"]
    fail_c = s["fail_count"]
    block_c = s["blocked_count"]
    total_c = s["total_count"]
    pass_pct = f"{(pass_c / max(total_c, 1) * 100):.1f}%"

    md = f"""# {pipeline_name}

**状态**: {s["status_display"]}

## 执行统计

| 指标 | 数量 | 占比 |
|------|------|------|
| ✅ 通过 (Pass) | {pass_c} | {pass_pct} |
"""
    if fail_c > 0:
        md += f"| ❌ 失败 (Fail) | {fail_c} | {(fail_c / max(total_c, 1) * 100):.1f}% |\n"
    if block_c > 0:
        md += f"| ⏸️ 阻塞 (Block) | {block_c} | {(block_c / max(total_c, 1) * 100):.1f}% |\n"

    md += f"""
| **总计** | **{total_c}** | 100% |

## 时间信息

- ⏱️ **耗时**: {s["duration"]}
- 🕐 **开始**: {s["started_at"] or "-"}
- 🕐 **结束**: {s["finished_at"] or "-"}
"""
    return md


def generate_result_page(
    run_id: str,
    pipeline_name: str,
    pipeline_id: str,
    pipeline_version: str,
    status: str,
    started_at: str | None,
    finished_at: str | None,
    tasks: list[dict],
    collector_html: str | None = None,
    collector_md: str | None = None,
    collector_mode: str | None = None,
) -> dict:
    stats = _build_default_stats(tasks, status, started_at, finished_at)
    html = _generate_html(stats, pipeline_name)
    md = _generate_md(stats, pipeline_name)

    if collector_mode == "replace" and (collector_html or collector_md):
        if collector_html:
            html = collector_html
        if collector_md:
            md = collector_md
    elif collector_mode == "append" and (collector_html or collector_md):
        if collector_html:
            html = html + "\n<hr>\n" + collector_html
        if collector_md:
            md = md + "\n---\n" + collector_md

    result_path = get_result_page_path(pipeline_id, pipeline_version, run_id)
    result_path.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "run_id": run_id,
        "pipeline_name": pipeline_name,
        "status": status,
        "stats": stats,
        "html_content": html,
        "md_content": md,
        "collector_mode": collector_mode,
        "has_collector": bool(collector_html or collector_md),
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    with open(result_path, "w") as f:
        json.dump(data, f, ensure_ascii=False, indent=2, default=str)

    logger.info("Result page generated for run %s at %s", run_id, result_path)
    return data


def load_result_page(pipeline_id: str, pipeline_version: str, run_id: str) -> dict | None:
    path = get_result_page_path(pipeline_id, pipeline_version, run_id)
    if not path.exists():
        return None
    with open(path) as f:
        return json.load(f)

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
    is_success = s["status"] == "success"

    status_color = {"success": "#059669", "failed": "#dc2626", "partial": "#d97706", "cancelled": "#9ca3af", "running": "#2563eb", "pending": "#6b7280"}.get(s["status"], "#6b7280")
    status_bg = {"success": "#ecfdf5", "failed": "#fef2f2", "partial": "#fffbeb", "cancelled": "#f9fafb", "running": "#eff6ff", "pending": "#f3f4f6"}.get(s["status"], "#f3f4f6")
    status_icon = {"success": "&#10003;", "failed": "&#10007;", "partial": "&#9888;", "cancelled": "&#8855;", "running": "&#9679;", "pending": "&#9678;"}.get(s["status"], "")

    ring_stroke = "#10b981" if is_success else "#ef4444" if fail_c > 0 else "#f59e0b"
    ring_pct = pass_c / max(total_c, 1)

    failed_row = ""
    if fail_c > 0:
        failed_row = f"""
        <tr>
            <td><span class="dot" style="background:#ef4444"></span> 失败</td>
            <td class="num">{fail_c}</td>
            <td class="pct">{(fail_c / max(total_c, 1) * 100):.0f}%</td>
        </tr>"""
    blocked_row = ""
    if block_c > 0:
        blocked_row = f"""
        <tr>
            <td><span class="dot" style="background:#f59e0b"></span> 阻塞</td>
            <td class="num">{block_c}</td>
            <td class="pct">{(block_c / max(total_c, 1) * 100):.0f}%</td>
        </tr>"""

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Pipeline Result - {pipeline_name}</title>
<style>
  *,*::before,*::after{{box-sizing:border-box;margin:0;padding:0}}
  body{{font-family:"Inter",-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;background:#f5f5f4;color:#292524;line-height:1.5;-webkit-font-smoothing:antialiased}}
  .card{{max-width:560px;margin:24px auto;background:#fff;border-radius:16px;box-shadow:0 1px 2px rgba(0,0,0,.04),0 4px 16px rgba(0,0,0,.04);overflow:hidden}}
  .hero{{padding:28px 28px 20px;border-bottom:1px solid #f0efed}}
  h1{{font-size:16px;font-weight:600;letter-spacing:-.01em;margin-bottom:8px;color:#1c1917}}
  .status-badge{{display:inline-flex;align-items:center;gap:5px;padding:3px 12px;border-radius:20px;font-size:12px;font-weight:600;background:{status_bg};color:{status_color}}}
  .status-badge .icon{{font-size:14px;line-height:1}}
  .metrics{{display:flex;padding:24px 28px;align-items:center;gap:28px}}
  .ring{{position:relative;width:72px;height:72px;flex-shrink:0}}
  .ring svg{{transform:rotate(-90deg)}}
  .ring-value{{position:absolute;inset:0;display:flex;align-items:center;justify-content:center;font-size:20px;font-weight:700;color:{ring_stroke}}}
  .stats-grid{{flex:1;display:grid;grid-template-columns:1fr 1fr;gap:10px}}
  .stat{{text-align:center}}
  .stat .val{{font-size:22px;font-weight:700;line-height:1.2}}
  .stat .lbl{{font-size:11px;color:#78716c;font-weight:500;text-transform:uppercase;letter-spacing:.03em;margin-top:2px}}
  .pass{{color:#059669}}.fail{{color:#dc2626}}.block{{color:#d97706}}.total{{color:#44403c}}
  table{{width:100%;border-collapse:collapse;margin:0 28px 20px;width:calc(100% - 56px)}}
  th{{text-align:left;font-size:11px;font-weight:600;color:#a8a29e;text-transform:uppercase;letter-spacing:.04em;padding-bottom:8px}}
  th:last-child,th:nth-child(2){{text-align:right}}
  td{{padding:7px 0;font-size:13px;border-bottom:1px solid #f5f5f4}}
  td:last-child,td.num{{text-align:right;font-variant-numeric:tabular-nums}}
  td .dot{{display:inline-block;width:8px;height:8px;border-radius:50%;margin-right:6px}}
  tr:last-child td{{border-bottom:none;font-weight:600;font-size:14px;padding-top:10px}}
  .pct{{color:#a8a29e;font-size:12px}}
  .footer{{padding:16px 28px;background:#fafaf9;border-top:1px solid #f0efed;display:flex;gap:20px;font-size:12px}}
  .footer-item{{display:flex;align-items:center;gap:5px;color:#78716c}}
  .footer-item .label{{font-weight:500;color:#a8a29e}}
</style>
</head>
<body>
<div class="card">
  <div class="hero">
    <h1>{pipeline_name}</h1>
    <span class="status-badge"><span class="icon">{status_icon}</span>{s["status_display"]}</span>
  </div>
  <div class="metrics">
    <div class="ring">
      <svg width="72" height="72" viewBox="0 0 72 72">
        <circle cx="36" cy="36" r="30" fill="none" stroke="#f0efed" stroke-width="6"/>
        <circle cx="36" cy="36" r="30" fill="none" stroke="{ring_stroke}" stroke-width="6"
          stroke-dasharray="{ring_pct * 188.5:.1f} 188.5" stroke-linecap="round"/>
      </svg>
      <div class="ring-value">{pass_pct}</div>
    </div>
    <div class="stats-grid">
      <div class="stat"><div class="val pass">{pass_c}</div><div class="lbl">Pass</div></div>
      <div class="stat"><div class="val fail">{fail_c}</div><div class="lbl">Fail</div></div>
      <div class="stat"><div class="val block">{block_c}</div><div class="lbl">Block</div></div>
      <div class="stat"><div class="val total">{total_c}</div><div class="lbl">Total</div></div>
    </div>
  </div>
  <table>
    <tr><th>指标</th><th>数量</th><th>占比</th></tr>
    <tr>
      <td><span class="dot" style="background:#10b981"></span> 通过</td>
      <td class="num">{pass_c}</td>
      <td class="pct">{pass_pct}</td>
    </tr>{failed_row}{blocked_row}
    <tr>
      <td>总计</td>
      <td class="num">{total_c}</td>
      <td class="pct">100%</td>
    </tr>
  </table>
  <div class="footer">
    <div class="footer-item"><span class="label">耗时</span>{s["duration"]}</div>
    <div class="footer-item"><span class="label">开始</span>{s["started_at"] or "-"}</div>
    <div class="footer-item"><span class="label">结束</span>{s["finished_at"] or "-"}</div>
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
    collector_data: list[dict] | None = None,
) -> dict:
    stats = _build_default_stats(tasks, status, started_at, finished_at)
    html = _generate_html(stats, pipeline_name)
    md = _generate_md(stats, pipeline_name)
    fmt = DEFAULT_RESULT_FORMAT

    if collector_mode == "replace" and (collector_html or collector_md):
        if collector_html:
            html = collector_html
            fmt = "html"
        if collector_md:
            md = collector_md
            fmt = "md" if not collector_html else fmt
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
        "format": fmt,
        "stats": stats,
        "html_content": html,
        "md_content": md,
        "collector_mode": collector_mode,
        "has_collector": bool(collector_html or collector_md or collector_data),
        "collector_data": collector_data,
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
    try:
        with open(path) as f:
            return json.load(f)
    except (json.JSONDecodeError, ValueError):
        logger.warning("Failed to load result page at %s: corrupted or empty JSON", path)
        return None

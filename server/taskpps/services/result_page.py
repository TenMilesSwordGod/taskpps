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


def _format_display_time(iso_str: str | None) -> str:
    """把 ISO 时间转成本地可读格式（yyyy-mm-dd HH:MM:SS）。

    为什么：结果页原先直接展示 ISO 原文（含微秒 + 时区，如
    2026-09-12T13:48:45.284357+00:00），长度过长会把页脚撑到换行/截断；
    这里转成人类可读时间，原始值仍保留在 stats.started_at/finished_at 中。
    """
    if not iso_str:
        return ""
    try:
        dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return iso_str
    if dt.tzinfo is not None:
        dt = dt.astimezone()
    return dt.strftime("%Y-%m-%d %H:%M:%S")


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
            total_ms = int(delta.total_seconds() * 1000)
            if total_ms <= 0:
                # 为什么：开始/结束相同（或时钟回拨）时统一显示 0s，避免负值
                duration_str = "0s"
            elif total_ms < 1000:
                # 为什么：亚秒级运行的整数秒会被截断成 0s，改用毫秒更准确
                duration_str = f"{total_ms}ms"
            else:
                total_seconds = total_ms // 1000
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
        # v2 (2026-09): 供结果页展示的可读时间，原始 ISO 字段保持不变兼容旧数据
        "started_display": _format_display_time(started_at),
        "finished_display": _format_display_time(finished_at),
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

    # v2 (2026-09): 页脚改为可读时间 + 原始时间 tooltip；ISO 原文过长会把页脚撑到换行
    duration_display = s.get("duration") or "-"
    started_raw = s.get("started_at") or ""
    finished_raw = s.get("finished_at") or ""
    started_display = s.get("started_display") or started_raw or "-"
    finished_display = s.get("finished_display") or finished_raw or "-"
    started_title = f' title="{started_raw}"' if started_raw and s.get("started_display") else ""
    finished_title = f' title="{finished_raw}"' if finished_raw and s.get("finished_display") else ""

    # v2 (2026-09): 移除与统计卡片完全重复的「指标/数量/占比」表格，避免信息冗余
    # v2 (2026-09): 所有 CSS 选择器限定在 .taskpps-result 下，防止内嵌 web 页面时
    # 全局选择器（body/*）污染应用样式
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Pipeline Result - {pipeline_name}</title>
<style>
  .taskpps-result,.taskpps-result *,.taskpps-result *::before,.taskpps-result *::after{{box-sizing:border-box;margin:0;padding:0}}
  .taskpps-result{{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,"PingFang SC","Microsoft YaHei",sans-serif;background:#fff;color:#292524;line-height:1.5;-webkit-font-smoothing:antialiased;max-width:640px;margin:24px auto;border:1px solid #f0efed;border-radius:14px;box-shadow:0 1px 2px rgba(0,0,0,.04),0 4px 16px rgba(0,0,0,.05);overflow:hidden}}
  .tr-hero{{display:flex;align-items:flex-start;justify-content:space-between;gap:12px;padding:20px 24px 16px;border-bottom:1px solid #f5f5f4}}
  .tr-title{{font-size:15px;font-weight:600;letter-spacing:-.01em;color:#1c1917;word-break:break-word}}
  .tr-badge{{display:inline-flex;align-items:center;gap:5px;flex-shrink:0;padding:3px 12px;border-radius:20px;font-size:12px;font-weight:600;background:{status_bg};color:{status_color}}}
  .tr-badge .icon{{font-size:14px;line-height:1}}
  .tr-metrics{{display:flex;align-items:center;gap:24px;padding:20px 24px}}
  .tr-ring{{position:relative;width:72px;height:72px;flex-shrink:0}}
  .tr-ring svg{{transform:rotate(-90deg)}}
  .tr-ring-value{{position:absolute;inset:0;display:flex;align-items:center;justify-content:center;font-size:14px;font-weight:700;color:{ring_stroke}}}
  .tr-grid{{flex:1;display:grid;grid-template-columns:repeat(4,1fr);gap:8px}}
  .tr-stat{{background:#fafaf9;border-radius:10px;padding:10px 4px;text-align:center}}
  .tr-stat .val{{font-size:20px;font-weight:700;line-height:1.2;font-variant-numeric:tabular-nums}}
  .tr-stat .lbl{{font-size:11px;color:#78716c;font-weight:500;margin-top:2px;white-space:nowrap}}
  .pass{{color:#059669}}.fail{{color:#dc2626}}.block{{color:#d97706}}.total{{color:#44403c}}
  .tr-footer{{display:flex;flex-wrap:wrap;gap:6px 20px;padding:12px 24px;background:#fafaf9;border-top:1px solid #f0efed;font-size:12px;color:#78716c}}
  .tr-footer .label{{font-weight:500;color:#a8a29e;margin-right:4px}}
  @media (max-width:480px){{
    .tr-metrics{{flex-direction:column;align-items:stretch;gap:16px}}
    .tr-ring{{align-self:center}}
    .tr-grid{{grid-template-columns:repeat(2,1fr)}}
  }}
</style>
</head>
<body>
<div class="taskpps-result">
  <div class="tr-hero">
    <div class="tr-title">{pipeline_name}</div>
    <span class="tr-badge"><span class="icon">{status_icon}</span>{s["status_display"]}</span>
  </div>
  <div class="tr-metrics">
    <div class="tr-ring">
      <svg width="72" height="72" viewBox="0 0 72 72" aria-hidden="true">
        <circle cx="36" cy="36" r="30" fill="none" stroke="#f0efed" stroke-width="6"/>
        <circle cx="36" cy="36" r="30" fill="none" stroke="{ring_stroke}" stroke-width="6"
          stroke-dasharray="{ring_pct * 188.5:.1f} 188.5" stroke-linecap="round"/>
      </svg>
      <div class="tr-ring-value">{pass_pct}</div>
    </div>
    <div class="tr-grid">
      <div class="tr-stat"><div class="val pass">{pass_c}</div><div class="lbl">通过 Pass</div></div>
      <div class="tr-stat"><div class="val fail">{fail_c}</div><div class="lbl">失败 Fail</div></div>
      <div class="tr-stat"><div class="val block">{block_c}</div><div class="lbl">阻塞 Block</div></div>
      <div class="tr-stat"><div class="val total">{total_c}</div><div class="lbl">总计 Total</div></div>
    </div>
  </div>
  <div class="tr-footer">
    <span><span class="label">耗时</span>{duration_display}</span>
    <span{started_title}><span class="label">开始</span>{started_display}</span>
    <span{finished_title}><span class="label">结束</span>{finished_display}</span>
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
- 🕐 **开始**: {s.get("started_display") or s.get("started_at") or "-"}
- 🕐 **结束**: {s.get("finished_display") or s.get("finished_at") or "-"}
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
        # v2 (2026-09): 分开保存插件原始产物，供前端原生结果页单独渲染插件内容；
        # 同时保留 html_content/md_content 合并结果兼容文件导出与老数据
        "collector_html": collector_html,
        "collector_md": collector_md,
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

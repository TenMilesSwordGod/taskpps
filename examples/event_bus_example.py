"""EventBus 使用示例 — 监听 pipeline 事件并自定义处理。

这个示例展示如何直接使用 EventBus 监听 taskpps 内部事件，
适用于需要在不写插件的情况下快速响应事件的场景。

运行方式：
    python3 examples/event_bus_example.py
"""

from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

# 将 server 目录加入 path，以便 import taskpps 模块
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "server"))

from taskpps.events.bus import (  # noqa: E402
    EventBus,
    SIGNAL_PIPELINE_STARTED,
    SIGNAL_TASK_FINISHED,
    SIGNAL_RUN_COMPLETED,
    SIGNAL_RUN_CANCELLED,
    SIGNAL_RETRY_STARTED,
    SIGNAL_RETRY_FINISHED,
    get_event_bus,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)


def on_pipeline_started(sender, **kwargs):
    """pipeline 启动时触发。"""
    logger.info(f"Pipeline started: {kwargs}")


def on_task_finished(sender, **kwargs):
    """任务完成时触发。"""
    task_name = kwargs.get("task_name", "unknown")
    status = kwargs.get("status", "unknown")
    logger.info(f"Task finished: {task_name} -> {status}")

    # 示例：根据状态执行不同逻辑
    if status == "failed":
        logger.warning(f"Task {task_name} failed! Triggering alert...")
        # send_alert(task_name)


def on_run_completed(sender, **kwargs):
    """运行完成时触发。"""
    run_id = kwargs.get("run_id", "unknown")
    success = kwargs.get("success", False)
    logger.info(f"Run completed: {run_id} success={success}")

    # 示例：写入外部系统
    write_to_log_file(run_id, success)


def on_run_cancelled(sender, **kwargs):
    """运行取消时触发。"""
    run_id = kwargs.get("run_id", "unknown")
    logger.info(f"Run cancelled: {run_id}")


def on_retry_started(sender, **kwargs):
    """重试开始时触发。"""
    task_name = kwargs.get("task_name", "unknown")
    attempt = kwargs.get("attempt", 0)
    logger.info(f"Retry started: {task_name} attempt={attempt}")


def write_to_log_file(run_id: str, success: bool) -> None:
    """将运行结果写入日志文件。"""
    log_path = Path("run_history.log")
    timestamp = datetime.now(timezone.utc).isoformat()
    status = "SUCCESS" if success else "FAILED"
    with open(log_path, "a") as f:
        f.write(f"{timestamp} | {run_id} | {status}\n")


def main():
    """注册事件监听器。"""
    bus = get_event_bus()

    # 注册事件处理器
    bus.on(SIGNAL_PIPELINE_STARTED, on_pipeline_started)
    bus.on(SIGNAL_TASK_FINISHED, on_task_finished)
    bus.on(SIGNAL_RUN_COMPLETED, on_run_completed)
    bus.on(SIGNAL_RUN_CANCELLED, on_run_cancelled)
    bus.on(SIGNAL_RETRY_STARTED, on_retry_started)

    logger.info("EventBus listeners registered. Waiting for events...")
    logger.info("Available signals:")
    logger.info(f"  - {SIGNAL_PIPELINE_STARTED}")
    logger.info(f"  - {SIGNAL_TASK_FINISHED}")
    logger.info(f"  - {SIGNAL_RUN_COMPLETED}")
    logger.info(f"  - {SIGNAL_RUN_CANCELLED}")
    logger.info(f"  - {SIGNAL_RETRY_STARTED}")
    logger.info(f"  - {SIGNAL_RETRY_FINISHED}")

    # 模拟发送事件（仅用于演示）
    logger.info("")
    logger.info("=== Simulating events ===")
    bus.emit(SIGNAL_PIPELINE_STARTED, pipeline_file="deploy.yaml", run_id="test-001")
    bus.emit(SIGNAL_TASK_FINISHED, task_name="build", status="success", duration=12.5)
    bus.emit(SIGNAL_RUN_COMPLETED, run_id="test-001", success=True)

    logger.info("")
    logger.info("=== Check run_history.log for output ===")


if __name__ == "__main__":
    main()

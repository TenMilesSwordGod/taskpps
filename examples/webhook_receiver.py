"""Webhook 接收端示例 — 一个简单的 FastAPI 服务，用来接收 webhook 通知。

启动方式：
    cd examples
    uvicorn webhook_receiver:app --host 0.0.0.0 --port 9000

然后在 taskpps.yaml 中配置：
    notifiers:
      - name: local-receiver
        type: webhook
        config:
          url: http://localhost:9000/webhook
          events:
            - pipeline_started
            - task_finished
            - run_completed
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from fastapi import FastAPI, Request

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="TaskPPS Webhook Receiver")


@app.post("/webhook")
async def receive_webhook(request: Request) -> dict[str, Any]:
    """接收来自 taskpps 的 webhook 通知。

    Payload 格式:
        {
            "event": "pipeline_started",
            "data": {
                "pipeline_file": "deploy.yaml",
                "run_id": "abc123",
                ...
            }
        }
    """
    body = await request.json()
    event = body.get("event", "unknown")
    data = body.get("data", {})

    # 在这里处理不同事件
    if event == "pipeline_started":
        handle_pipeline_started(data)
    elif event == "task_finished":
        handle_task_finished(data)
    elif event == "run_completed":
        handle_run_completed(data)
    elif event == "run_cancelled":
        handle_run_cancelled(data)
    else:
        handle_generic(event, data)

    return {"status": "ok", "event": event}


def handle_pipeline_started(data: dict) -> None:
    """处理 pipeline 启动事件。"""
    pipeline = data.get("pipeline_file", "unknown")
    run_id = data.get("run_id", "unknown")
    logger.info(f"[Pipeline Started] pipeline={pipeline} run_id={run_id}")
    # 示例：发送到 Slack、钉钉、飞书等
    # send_to_slack(f"🚀 Pipeline {pipeline} started (run: {run_id})")


def handle_task_finished(data: dict) -> None:
    """处理任务完成事件。"""
    task_name = data.get("task_name", "unknown")
    status = data.get("status", "unknown")
    duration = data.get("duration", 0)
    logger.info(
        f"[Task Finished] task={task_name} status={status} duration={duration}s"
    )
    # 示例：更新外部看板状态
    # update_jira_status(task_name, status)


def handle_run_completed(data: dict) -> None:
    """处理运行完成事件。"""
    run_id = data.get("run_id", "unknown")
    pipeline = data.get("pipeline_file", "unknown")
    success = data.get("success", False)
    logger.info(
        f"[Run Completed] run_id={run_id} pipeline={pipeline} success={success}"
    )
    # 示例：发送完成通知
    # send_email(
    #     to="team@example.com",
    #     subject=f"Pipeline {pipeline} {'succeeded' if success else 'failed'}",
    #     body=f"Run {run_id} completed.",
    # )


def handle_run_cancelled(data: dict) -> None:
    """处理运行取消事件。"""
    run_id = data.get("run_id", "unknown")
    reason = data.get("reason", "unknown")
    logger.info(f"[Run Cancelled] run_id={run_id} reason={reason}")


def handle_generic(event: str, data: dict) -> None:
    """处理其他事件。"""
    logger.info(f"[Event] {event}: {data}")


@app.get("/health")
async def health() -> dict:
    """健康检查。"""
    return {"status": "healthy", "timestamp": datetime.now(timezone.utc).isoformat()}

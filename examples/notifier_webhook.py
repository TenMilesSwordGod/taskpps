"""Webhook Notifier 插件示例 — 实现 NotifierPlugin 接口，将事件推送到外部 URL。

使用方式：
    1. 将此文件放到 plugins/ 目录下
    2. 在 taskpps.yaml 中配置 notifiers
    3. 启动 taskpps，插件会自动注册

插件会被 PluginManager 自动发现和注册。
"""

from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
from typing import Any

from taskpps.plugins.base import NotifierPlugin

logger = logging.getLogger(__name__)


class WebhookNotifier(NotifierPlugin):
    """将 pipeline 事件通过 HTTP POST 推送到指定 URL。

    配置示例 (taskpps.yaml):
        notifiers:
          - name: my-webhook
            type: webhook
            config:
              url: https://example.com/webhook
              events:
                - pipeline_started
                - task_finished
                - run_completed
                - run_cancelled
              headers:
                X-Custom-Header: my-value
              timeout: 10
              retry: 3
    """

    def __init__(
        self,
        url: str = "",
        events: list[str] | None = None,
        headers: dict[str, str] | None = None,
        timeout: int = 10,
        retry: int = 3,
        **kwargs: Any,
    ):
        self._url = url
        # 默认监听所有事件
        self._events = events or [
            "pipeline_started",
            "task_started",
            "task_finished",
            "run_completed",
            "run_cancelled",
            "retry_started",
            "retry_finished",
        ]
        self._headers = headers or {}
        self._timeout = timeout
        self._retry = retry
        self._running = False

    @property
    def name(self) -> str:
        return f"webhook:{self._url}"

    def start(self) -> None:
        self._running = True
        logger.info(f"WebhookNotifier started: {self._url}")

    def stop(self) -> None:
        self._running = False
        logger.info(f"WebhookNotifier stopped: {self._url}")

    def notify(self, event: str, data: dict[str, Any]) -> None:
        """收到事件时调用，POST JSON 到配置的 URL。"""
        if event not in self._events:
            return

        payload = {
            "event": event,
            "data": data,
        }

        body = json.dumps(payload, default=str).encode("utf-8")
        headers = {
            "Content-Type": "application/json",
            "User-Agent": "taskpps-webhook-notifier/1.0",
            **self._headers,
        }

        for attempt in range(1, self._retry + 1):
            try:
                req = urllib.request.Request(
                    self._url,
                    data=body,
                    headers=headers,
                    method="POST",
                )
                with urllib.request.urlopen(req, timeout=self._timeout) as resp:
                    status = resp.status
                    logger.info(
                        f"Webhook delivered: event={event} status={status} "
                        f"attempt={attempt}/{self._retry}"
                    )
                    return
            except urllib.error.HTTPError as e:
                logger.warning(
                    f"Webhook HTTP error: event={event} status={e.code} "
                    f"attempt={attempt}/{self._retry}"
                )
                if attempt == self._retry:
                    logger.error(
                        f"Webhook failed after {self._retry} attempts: {event}"
                    )
            except Exception as e:
                logger.warning(
                    f"Webhook error: event={event} error={e} "
                    f"attempt={attempt}/{self._retry}"
                )
                if attempt == self._retry:
                    logger.error(
                        f"Webhook failed after {self._retry} attempts: {event}"
                    )

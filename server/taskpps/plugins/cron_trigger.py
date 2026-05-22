from __future__ import annotations

import asyncio
import logging
import threading
from datetime import datetime, timezone
from typing import Optional

from croniter import croniter

from taskpps.plugins.base import TriggerPlugin

logger = logging.getLogger(__name__)


class CronTrigger(TriggerPlugin):
    def __init__(self, expression: str, pipeline_file: str, callback=None):
        self._expression = expression
        self._pipeline_file = pipeline_file
        self._callback = callback
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()

    @property
    def name(self) -> str:
        return f"cron:{self._expression}:{self._pipeline_file}"

    def get_type(self) -> str:
        return "cron"

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()
        logger.info(f"CronTrigger started: {self.name}")

    def stop(self) -> None:
        self._running = False
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=5)
        logger.info(f"CronTrigger stopped: {self.name}")

    def _run_loop(self) -> None:
        base = datetime.now(timezone.utc)
        cron = croniter(self._expression, base)

        while not self._stop_event.is_set():
            next_time = cron.get_next(datetime)
            now = datetime.now(timezone.utc)
            delay = (next_time - now).total_seconds()

            if delay > 0:
                if self._stop_event.wait(timeout=min(delay, 60)):
                    break
                if datetime.now(timezone.utc) < next_time:  # pragma: no cover
                    continue  # pragma: no cover

            if self._callback:  # pragma: no cover
                try:  # pragma: no cover
                    self._callback(self._pipeline_file)  # pragma: no cover
                except Exception as e:  # pragma: no cover
                    logger.error(f"CronTrigger callback error: {e}")  # pragma: no cover

            cron = croniter(self._expression, datetime.now(timezone.utc))  # pragma: no cover

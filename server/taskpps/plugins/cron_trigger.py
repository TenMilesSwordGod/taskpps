from __future__ import annotations

import asyncio
import logging
import threading
from datetime import datetime
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
        base = datetime.utcnow()
        cron = croniter(self._expression, base)

        while not self._stop_event.is_set():
            next_time = cron.get_next(datetime)
            now = datetime.utcnow()
            delay = (next_time - now).total_seconds()

            if delay > 0:
                if self._stop_event.wait(timeout=min(delay, 60)):
                    break
                if datetime.utcnow() < next_time:
                    continue

            if self._callback:
                try:
                    self._callback(self._pipeline_file)
                except Exception as e:
                    logger.error(f"CronTrigger callback error: {e}")

            cron = croniter(self._expression, datetime.utcnow())

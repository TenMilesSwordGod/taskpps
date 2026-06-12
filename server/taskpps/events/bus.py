from collections.abc import Callable
from typing import Any, Optional

from blinker import Signal


class EventBus:
    _instance: Optional["EventBus"] = None

    def __init__(self):
        self._signals: dict[str, Signal] = {}

    @classmethod
    def get_instance(cls) -> "EventBus":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def _get_signal(self, event_name: str) -> Signal:
        if event_name not in self._signals:
            self._signals[event_name] = Signal(event_name)
        return self._signals[event_name]

    def on(self, event_name: str, handler: Callable) -> None:
        signal = self._get_signal(event_name)
        signal.connect(handler)

    def emit(self, event_name: str, sender: Any = None, **kwargs) -> None:
        signal = self._get_signal(event_name)
        signal.send(sender, **kwargs)

    def off(self, event_name: str, handler: Callable) -> None:
        if event_name in self._signals:
            self._signals[event_name].disconnect(handler)


SIGNAL_PIPELINE_STARTED = "pipeline_started"
SIGNAL_TASK_STARTED = "task_started"
SIGNAL_TASK_FINISHED = "task_finished"
SIGNAL_RUN_COMPLETED = "run_completed"
SIGNAL_RUN_CANCELLED = "run_cancelled"

SIGNAL_RETRY_STARTED = "retry_started"
SIGNAL_RETRY_FINISHED = "retry_finished"


def get_event_bus() -> EventBus:
    return EventBus.get_instance()

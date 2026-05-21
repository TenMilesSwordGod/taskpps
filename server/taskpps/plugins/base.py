from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, Optional


class BasePlugin(ABC):
    @property
    @abstractmethod
    def name(self) -> str:
        pass

    @abstractmethod
    def start(self) -> None:
        pass

    @abstractmethod
    def stop(self) -> None:
        pass


class TriggerPlugin(BasePlugin):
    @abstractmethod
    def start(self) -> None:
        pass

    @abstractmethod
    def stop(self) -> None:
        pass

    @abstractmethod
    def get_type(self) -> str:
        pass


class NotifierPlugin(BasePlugin):
    @abstractmethod
    def notify(self, event: str, data: Dict[str, Any]) -> None:
        pass


class ExecutorPlugin(BasePlugin):
    @abstractmethod
    def can_handle(self, task_type: str) -> bool:
        pass

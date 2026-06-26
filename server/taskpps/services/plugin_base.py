from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class BasePlugin(ABC):
    @property
    @abstractmethod
    def name(self) -> str:  # pragma: no cover
        ...

    @property
    @abstractmethod
    def help_msg(self) -> str:  # pragma: no cover
        ...

    @property
    @abstractmethod
    def version(self) -> str:  # pragma: no cover
        ...

    @abstractmethod
    def start(self) -> None:  # pragma: no cover
        ...

    @abstractmethod
    def stop(self) -> None:  # pragma: no cover
        ...


class TriggerPlugin(BasePlugin):
    @abstractmethod
    def start(self) -> None:  # pragma: no cover
        ...

    @abstractmethod
    def stop(self) -> None:  # pragma: no cover
        ...

    @abstractmethod
    def get_type(self) -> str:  # pragma: no cover
        ...


class NotifierPlugin(BasePlugin):
    @abstractmethod
    def notify(self, event: str, data: dict[str, Any]) -> None:  # pragma: no cover
        ...


class ExecutorPlugin(BasePlugin):
    @abstractmethod
    def can_handle(self, task_type: str) -> bool:  # pragma: no cover
        ...

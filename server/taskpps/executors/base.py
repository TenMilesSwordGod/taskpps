from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path


class ExecutorResult:
    def __init__(self, exit_code: int, stdout: str = "", stderr: str = ""):
        self.exit_code = exit_code
        self.stdout = stdout
        self.stderr = stderr

    @property
    def success(self) -> bool:
        return self.exit_code == 0


class BaseExecutor(ABC):
    @abstractmethod
    async def execute(
        self,
        command: str,
        env: dict[str, str],
        log_path: Path,
        timeout: int | None = None,
        cwd: str | None = None,
    ) -> ExecutorResult:  # pragma: no cover
        ...

    @abstractmethod
    async def cancel(self) -> None: ...

    def _ensure_log_dir(self, log_path: Path) -> None:
        log_path.parent.mkdir(parents=True, exist_ok=True)

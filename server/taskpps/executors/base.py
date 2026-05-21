from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Dict, Optional, Tuple


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
        env: Dict[str, str],
        log_path: Path,
        timeout: Optional[int] = None,
        cwd: Optional[str] = None,
    ) -> ExecutorResult:
        pass

    async def cancel(self) -> None:
        pass

    def _ensure_log_dir(self, log_path: Path) -> None:
        log_path.parent.mkdir(parents=True, exist_ok=True)

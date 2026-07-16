from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path


class ExecutorResult:
    def __init__(self, exit_code: int, stdout: str = "", stderr: str = "", is_infrastructure_failure: bool = False):
        self.exit_code = exit_code
        self.stdout = stdout
        self.stderr = stderr
        # v2 (2026-07): 区分"基础设施故障"（如 connection lost）和"任务逻辑失败"。
        # 基础设施故障即使 on_failure=continue 也必须 block 后续 task，
        # 因为后续 task 同样会因为连接断开而无法执行（Issue #202）。
        self.is_infrastructure_failure = is_infrastructure_failure

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

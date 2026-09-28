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
    # v2 (2026-09): 由 create_executor 从 agent yaml 注入的执行环境。
    # 未配置时为空；实例属性由工厂覆盖，这里只作为缺省值防止 AttributeError。
    agent_env: dict[str, str] = {}
    agent_shell: str = ""

    def apply_agent_env(self, env: dict[str, str]) -> dict[str, str]:
        """把 agent 配置 env 作为默认值，本次执行 env（流水线/任务/运行参数）覆盖之。"""
        if not self.agent_env:
            return dict(env)
        return {**self.agent_env, **env}

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

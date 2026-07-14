from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from taskpps.executors.base import ExecutorResult
from taskpps.i18n import t

# on_log 回调签名: (level: str, msg: str) -> None
# PipelineRunner 传入 self._write_pipeline_log; RetryRunner 不传
OnLog = Callable[[str, str], None] | None


async def run_commands(
    executor: Any,
    commands: list[str],
    env: dict[str, str],
    log_path: Path,
    timeout: int | None,
    effective_cwd: str | None = None,
    on_log: OnLog = None,
) -> ExecutorResult:
    """逐条执行 commands 列表，合并输出。
    从 PipelineRunner._execute_commands 提取为公共 helper，供 RetryRunner 复用。
    """
    if not commands:
        return ExecutorResult(exit_code=0)

    combined_output = ""
    cmd_timeout = None
    if timeout:
        cmd_timeout = timeout // max(len(commands), 1)
        if cmd_timeout < 1:
            cmd_timeout = 1

    for i, cmd in enumerate(commands):
        if on_log:
            on_log("CMD", f"  [{i + 1}/{len(commands)}] {cmd}")
        with open(log_path, "a") as f:
            f.write(t("Command {n}/{total}: {cmd}\n", n=i + 1, total=len(commands), cmd=cmd[:80]))

        result = await executor.execute(
            command=cmd,
            env=env,
            log_path=log_path,
            timeout=cmd_timeout,
            cwd=effective_cwd,
        )

        combined_output += result.stdout or ""

        if not result.success:
            combined_output += result.stderr or ""
            return ExecutorResult(
                exit_code=result.exit_code,
                stdout=combined_output,
                stderr=t("Command {n} failed: {error}", n=i + 1, error=result.stderr),
            )

    return ExecutorResult(exit_code=0, stdout=combined_output)


async def run_steps(
    executor: Any,
    steps: list[Any],  # ResolvedStep，属性: run/cd/env
    env: dict[str, str],
    log_path: Path,
    timeout: int | None,
    effective_cwd: str | None = None,
    on_log: OnLog = None,
) -> ExecutorResult:
    """逐条执行 steps，支持每步的 cd/env/分段超时，合并输出。
    从 PipelineRunner._execute_steps 提取为公共 helper，供 RetryRunner 复用。
    """
    combined_output = ""
    step_timeout = None
    step_count = len(steps)
    if timeout and step_count:
        step_timeout = timeout // max(step_count, 1)
        if step_timeout < 1:
            step_timeout = 1

    for i, step in enumerate(steps):
        step_env = {**env, **step.env}
        step_cwd = step.cd or effective_cwd

        step_desc = f"  [{i + 1}/{step_count}]"
        if step.cd:
            step_desc += f" cd {step.cd} &&"
        step_desc += f" {step.run}"
        if on_log:
            on_log("CMD", step_desc)

        with open(log_path, "a") as f:
            f.write(t("Step {n}/{total}: {cmd}", n=i + 1, total=step_count, cmd=step.run[:80]))

        result = await executor.execute(
            command=step.run,
            env=step_env,
            log_path=log_path,
            timeout=step_timeout,
            cwd=step_cwd,
        )

        combined_output += result.stdout or ""

        if not result.success:
            combined_output += result.stderr or ""
            return ExecutorResult(
                exit_code=result.exit_code,
                stdout=combined_output,
                stderr=t("Step {n} failed: {error}", n=i + 1, error=result.stderr),
            )

    return ExecutorResult(exit_code=0, stdout=combined_output)

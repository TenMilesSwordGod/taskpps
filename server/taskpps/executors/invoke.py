from __future__ import annotations

import asyncio
import importlib
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from taskpps.executors.base import BaseExecutor, ExecutorResult
from taskpps.config import get_tasks_dir
from taskpps.i18n import t


class InvokeExecutor(BaseExecutor):
    def __init__(self):
        self._cancelled = False

    async def execute(
        self,
        command: str,
        env: Dict[str, str],
        log_path: Path,
        timeout: Optional[int] = None,
        cwd: Optional[str] = None,
        invoke_task: Optional[str] = None,
        invoke_args: Optional[List[Any]] = None,
        invoke_kwargs: Optional[Dict[str, Any]] = None,
    ) -> ExecutorResult:
        self._ensure_log_dir(log_path)
        self._cancelled = False

        if not invoke_task:
            return ExecutorResult(exit_code=1, stderr=t("No invoke task specified"))

        parts = invoke_task.rsplit(".", 1)
        if len(parts) != 2:
            return ExecutorResult(exit_code=1, stderr=t("Invalid invoke task format: {task}", task=invoke_task))

        module_name, func_name = parts
        args = invoke_args or []
        kwargs = invoke_kwargs or {}

        def _run_invoke():
            tasks_dir = str(get_tasks_dir())
            if tasks_dir not in sys.path:
                sys.path.insert(0, tasks_dir)

            try:
                module = importlib.import_module(module_name)
                func = getattr(module, func_name)
            except (ImportError, AttributeError) as e:
                return ExecutorResult(exit_code=1, stderr=str(e))

            try:
                from invoke import task as invoke_task_decorator

                merged_env = {**os.environ, **env}

                try:
                    if getattr(func, "_task", None) is not None:
                        from invoke import Context
                        ctx = Context(env=merged_env)
                        result = func(ctx, *args, **kwargs)
                    else:
                        old_env = {}
                        for k, v in merged_env.items():
                            old_env[k] = os.environ.get(k)
                            os.environ[k] = v
                        try:
                            result = func(*args, **kwargs)
                        finally:
                            for k in merged_env:
                                if old_env[k] is None:
                                    os.environ.pop(k, None)
                                else:
                                    os.environ[k] = old_env[k]

                output = str(result) if result is not None else ""
                with open(log_path, "w") as f:
                    f.write(output)
                return ExecutorResult(exit_code=0, stdout=output)
            except Exception as e:
                error_msg = str(e)
                with open(log_path, "w") as f:
                    f.write(error_msg)
                return ExecutorResult(exit_code=1, stderr=error_msg)

        try:
            loop = asyncio.get_event_loop()
            coro = loop.run_in_executor(None, _run_invoke)
            if timeout is not None:
                result = await asyncio.wait_for(coro, timeout=timeout)
            else:
                result = await coro
            return result
        except asyncio.TimeoutError:
            msg = t("Invoke task exceeded timeout of {timeout}s", timeout=timeout)
            with open(log_path, "a") as f:
                f.write(msg)
            return ExecutorResult(exit_code=-1, stderr=msg)
        except asyncio.CancelledError:
            msg = t("Invoke task was cancelled")
            with open(log_path, "a") as f:
                f.write(msg)
            return ExecutorResult(exit_code=-1, stderr=msg)

    async def cancel(self) -> None:
        self._cancelled = True

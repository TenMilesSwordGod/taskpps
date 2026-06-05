from __future__ import annotations

import asyncio
import importlib
import logging
import os
import sys
from pathlib import Path
from typing import Any

from taskpps.config import get_tasks_dir
from taskpps.executors.base import BaseExecutor, ExecutorResult
from taskpps.i18n import t

logger = logging.getLogger(__name__)


class InvokeExecutor(BaseExecutor):
    def __init__(self):
        self._cancelled = False

    async def execute(
        self,
        command: str,
        env: dict[str, str],
        log_path: Path,
        timeout: int | None = None,
        cwd: str | None = None,
        invoke_task: str | None = None,
        invoke_args: list[Any] | None = None,
        invoke_kwargs: dict[str, Any] | None = None,
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
        logger.info("InvokeExecutor: module=%s func=%s args=%s kwargs=%s", module_name, func_name, args, kwargs)

        def _run_invoke():
            tasks_dir = str(get_tasks_dir())
            if tasks_dir not in sys.path:
                sys.path.insert(0, tasks_dir)

            try:
                module = importlib.import_module(module_name)
                func = getattr(module, func_name)
            except (ImportError, AttributeError) as e:
                logger.error("InvokeExecutor: failed to import %s.%s: %s", module_name, func_name, e)
                return ExecutorResult(exit_code=1, stderr=str(e))

            try:
                merged_env = {**os.environ, **env}

                if getattr(func, "_task", None) is not None:
                    logger.info("InvokeExecutor: running invoke task %s.%s", module_name, func_name)
                    from invoke import Context

                    ctx = Context(env=merged_env)
                    result = func(ctx, *args, **kwargs)
                else:
                    logger.info("InvokeExecutor: running plain function %s.%s", module_name, func_name)
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
                logger.error("InvokeExecutor: function %s.%s raised: %s", module_name, func_name, error_msg)
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
            logger.warning("InvokeExecutor: timeout after %ds for %s.%s", timeout, module_name, func_name)
            with open(log_path, "a") as f:
                f.write(msg)
            return ExecutorResult(exit_code=-1, stderr=msg)
        except asyncio.CancelledError:
            msg = t("Invoke task was cancelled")
            logger.info("InvokeExecutor: cancelled %s.%s", module_name, func_name)
            with open(log_path, "a") as f:
                f.write(msg)
            return ExecutorResult(exit_code=-1, stderr=msg)

    async def cancel(self) -> None:
        logger.info("InvokeExecutor.cancel: cancelled=True")
        self._cancelled = True

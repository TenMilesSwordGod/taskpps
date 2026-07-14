from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from taskpps.db.engine import get_session_factory
from taskpps.db.repository import RetryRecordRepository
from taskpps.domain.context import ExecutionContext
from taskpps.domain.dag import DAG
from taskpps.domain.pipeline import ResolvedPipeline, ResolvedTask
from taskpps.engine.step_executor import run_commands, run_steps
from taskpps.events.bus import SIGNAL_RETRY_FINISHED, SIGNAL_RETRY_STARTED, get_event_bus
from taskpps.executors import create_executor
from taskpps.executors.agent_executor import AgentExecutor
from taskpps.executors.base import ExecutorResult
from taskpps.executors.invoke import InvokeExecutor
from taskpps.executors.plugin import PluginExecutor
from taskpps.models.run import TaskStatus

logger = logging.getLogger(__name__)


class RetryRunner:
    def __init__(
        self,
        run_id: str,
        pipeline: ResolvedPipeline,
        context: ExecutionContext,
        max_parallel: int | None = None,
        execution_strategy: str = "parallel",
    ):
        self.run_id = run_id
        self.pipeline = pipeline
        self.context = context
        self.max_parallel = max_parallel
        self.execution_strategy = execution_strategy
        self._cancelled = False
        self._running_executors: dict[str, Any] = {}

    async def retry_tasks(self, task_plan: list[dict]) -> dict[str, ExecutorResult]:
        _active_retries[self.run_id] = self
        try:
            return await self._retry_tasks(task_plan)
        finally:
            _active_retries.pop(self.run_id, None)

    async def _retry_tasks(self, task_plan: list[dict]) -> dict[str, ExecutorResult]:
        task_names = [tp["name"] for tp in task_plan]
        levels = self._build_qualified_levels(task_names)
        semaphore = asyncio.Semaphore(self.max_parallel or 10)

        async def _run_one(tp: dict) -> tuple[str, ExecutorResult]:
            async with semaphore:
                result = await self._execute_retry_task(tp)
                return tp["name"], result

        results: dict[str, ExecutorResult] = {}
        planned: set[str] = set()
        for level in levels:
            if self.execution_strategy == "sequential":
                for task_name in level:
                    tp = next(t for t in task_plan if t["name"] == task_name)
                    name, result = await _run_one(tp)
                    results[name] = result
                    planned.add(name)
            else:
                coros = []
                for task_name in level:
                    tp = next(t for t in task_plan if t["name"] == task_name)
                    coros.append(_run_one(tp))
                    planned.add(task_name)
                for name, result in await asyncio.gather(*coros):
                    results[name] = result

        for tp in task_plan:
            if tp["name"] not in planned:
                if self.execution_strategy == "sequential":
                    name, result = await _run_one(tp)
                    results[name] = result
                else:
                    result = await self._execute_retry_task(tp)
                    results[tp["name"]] = result

        return results

    def _build_qualified_levels(self, task_names: list[str]) -> list[list[str]]:
        qualified_tasks = self._build_qualified_tasks_with_subpipeline_deps()
        dag = DAG(qualified_tasks, implicit_sequential=False)
        all_levels = dag.get_execution_levels()
        return [[n for n in level if n in task_names] for level in all_levels if any(n in task_names for n in level)]

    def _build_qualified_tasks_with_subpipeline_deps(self) -> list[ResolvedTask]:
        qualified_tasks: list[ResolvedTask] = []
        sub_task_map: dict[str, list[str]] = {}
        for sub in self.pipeline.subpipelines:
            sub_task_names = []
            for t in sub.tasks:
                qname = f"{sub.name}.{t.name}"
                sub_task_names.append(qname)
                qt = ResolvedTask(
                    name=qname,
                    task_type=t.task_type,
                    command=t.command,
                    commands=t.commands,
                    depends_on=[f"{sub.name}.{d}" for d in (t.depends_on or [])],
                )
                qualified_tasks.append(qt)
            sub_task_map[sub.name] = sub_task_names

        for sub in self.pipeline.subpipelines:
            if sub.depends_on:
                for dep_sub_name in sub.depends_on:
                    dep_tasks = sub_task_map.get(dep_sub_name, [])
                    for qt in qualified_tasks:
                        if qt.name.startswith(f"{sub.name}."):
                            qt.depends_on = list(qt.depends_on) + dep_tasks

        return qualified_tasks

    async def _execute_retry_task(self, tp: dict) -> ExecutorResult:
        task_name = tp["name"]
        command = tp.get("command", "")
        record_id = tp["retry_record_id"]
        log_path = Path(tp["log_path"])

        task = self._find_task(task_name)
        if task is None:
            await self._update_record(record_id, TaskStatus.FAILED, exit_code=1, error=f"Task '{task_name}' not found in resolved pipeline", finished_at=datetime.now(timezone.utc))
            return ExecutorResult(exit_code=1, stderr=f"Task '{task_name}' not found in resolved pipeline")

        if self._cancelled:
            await self._update_record(record_id, TaskStatus.CANCELLED)
            return ExecutorResult(exit_code=-1, stdout="Retry cancelled")

        env = self.context.get_task_env(task)
        log_path.parent.mkdir(parents=True, exist_ok=True)

        event_bus = get_event_bus()
        event_bus.emit(SIGNAL_RETRY_STARTED, sender=self, run_id=self.run_id, task=task_name, retry_record_id=record_id)

        await self._update_record(record_id, TaskStatus.RUNNING, started_at=datetime.now(timezone.utc))

        timeout = task.timeout or 3600
        effective_cwd = task.cwd or self.context.get_workspace()

        try:
            executor = create_executor(task, self.context.project_workdir)
            self._running_executors[task_name] = executor
            if isinstance(executor, AgentExecutor):
                executor.run_id = self.run_id
                executor.task_name = task_name
            last_result = await self._dispatch_execution(executor, task, command, env, log_path, timeout, effective_cwd)
        except Exception as e:
            logger.exception("Retry task '%s' unexpected error", task_name)
            try:
                with open(log_path, "a") as f:
                    f.write(f"\n[ERROR] {e}\n")
            except Exception:
                pass
            last_result = ExecutorResult(exit_code=1, stderr=str(e))
        finally:
            executor = self._running_executors.pop(task_name, None)
            if isinstance(executor, AgentExecutor):
                executor.cleanup()

        retry_status = TaskStatus.SUCCESS if last_result.success else TaskStatus.FAILED
        if self._cancelled:
            retry_status = TaskStatus.CANCELLED

        await self._update_record(
            record_id,
            retry_status,
            exit_code=last_result.exit_code,
            error=last_result.stderr[:500] if last_result.stderr else None,
            finished_at=datetime.now(timezone.utc),
        )

        event_bus.emit(
            SIGNAL_RETRY_FINISHED,
            sender=self,
            run_id=self.run_id,
            task=task_name,
            retry_record_id=record_id,
            status=retry_status,
        )

        return last_result

    async def _dispatch_execution(
        self,
        executor: Any,
        task: ResolvedTask,
        command: str,
        env: dict[str, str],
        log_path: Path,
        timeout: int,
        effective_cwd: str | None,
    ) -> ExecutorResult:
        if isinstance(executor, InvokeExecutor):
            return await executor.execute(
                command="",
                env=env,
                log_path=log_path,
                timeout=timeout,
                invoke_task=task.invoke_task,
                invoke_args=task.invoke_args,
                invoke_kwargs=task.invoke_kwargs,
            )
        elif isinstance(executor, PluginExecutor):
            return await executor.execute(command="", env=env, log_path=log_path, timeout=timeout)
        elif task.task_type == "steps" and task.steps:
            # v2 (2026-07): 修复 steps 任务重试时 command="" 导致空跑的问题（原 dispatcher 只处理单 command 任务）
            # 改为逐条送 step.run 到 executor，与 PipelineRunner._execute_steps 行为一致
            return await run_steps(executor, task.steps, env, log_path, timeout, effective_cwd)
        elif task.commands:
            # v2 (2026-07): 改为逐条执行，与 PipelineRunner._execute_commands 行为一致
            # 原实现 "\n".join 对 AgentExecutor 仅送一条多行命令，缺少分段超时和错误定位
            return await run_commands(executor, task.commands, env, log_path, timeout, effective_cwd)
        else:
            cmd = command or task.command or ""
            return await executor.execute(
                command=cmd,
                env=env,
                log_path=log_path,
                timeout=timeout,
                cwd=effective_cwd,
            )

    def _find_task(self, task_name: str) -> ResolvedTask | None:
        for sub in self.pipeline.subpipelines:
            for t in sub.tasks:
                full_name = f"{sub.name}.{t.name}"
                if full_name == task_name:
                    return t
        return None

    async def _update_record(
        self,
        record_id: str,
        status: TaskStatus,
        exit_code: int | None = None,
        error: str | None = None,
        started_at: datetime | None = None,
        finished_at: datetime | None = None,
    ) -> None:
        async with get_session_factory()() as session:
            repo = RetryRecordRepository(session)
            await repo.update_retry_status(
                record_id, status, exit_code=exit_code, error=error,
                started_at=started_at, finished_at=finished_at,
            )

    async def cancel(self) -> None:
        self._cancelled = True
        for _name, executor in self._running_executors.items():
            await executor.cancel()


_active_retries: dict[str, RetryRunner] = {}


def get_active_retry_runner(run_id: str) -> RetryRunner | None:
    return _active_retries.get(run_id)

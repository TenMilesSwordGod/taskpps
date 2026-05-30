from __future__ import annotations

import asyncio
import json
import logging
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from taskpps.config import get_logs_dir, get_settings, build_log_path, get_workspaces_dir
from taskpps.db.engine import get_session_factory
from taskpps.db.repository import RunRepository, TaskRunRepository
from taskpps.i18n import t
from taskpps.domain.context import ExecutionContext
from taskpps.domain.dag import DAG, DAGCycleError
from taskpps.domain.pipeline import ResolvedPipeline, ResolvedTask, ResolvedSubPipeline
from taskpps.events.bus import get_event_bus, SIGNAL_PIPELINE_STARTED, SIGNAL_TASK_STARTED, SIGNAL_TASK_FINISHED, SIGNAL_RUN_COMPLETED, SIGNAL_RUN_CANCELLED
from taskpps.executors import create_executor
from taskpps.executors.base import BaseExecutor, ExecutorResult
from taskpps.executors.invoke import InvokeExecutor
from taskpps.executors.git import GitExecutor
from taskpps.executors.nexus import NexusExecutor
from taskpps.models.run import RunStatus, TaskStatus


logger = logging.getLogger(__name__)
_active_runs: Dict[str, "PipelineRunner"] = {}

_WHEN_PATTERN = re.compile(r'\$\{env\.([^}]+)\}\s*(==|!=)\s*"([^"]*)"')


def _evaluate_when(when_expr: Optional[str], env: Dict[str, str]) -> bool:
    if when_expr is None:
        return True
    match = _WHEN_PATTERN.match(when_expr.strip())
    if not match:
        logger.warning(t("Invalid when expression: {expr}", expr=when_expr))
        return True
    var_name = match.group(1)
    operator = match.group(2)
    expected = match.group(3)
    actual = env.get(var_name, os.environ.get(var_name, ""))
    if operator == "==":
        return actual == expected
    elif operator == "!=":
        return actual != expected
    return True


class PipelineRunner:
    def __init__(self, run_id: str, pipeline: ResolvedPipeline, context: ExecutionContext):
        self.run_id = run_id
        self.pipeline = pipeline
        self.context = context
        self.dag: Optional[DAG] = None
        self._cancelled = False
        self._unexpected_error = False
        self._running_executors: Dict[str, Any] = {}
        self._task_run_ids: Dict[str, str] = {}
        self._pipeline_id: str = ""
        self._pipeline_version: str = ""

    async def run(self) -> None:
        if not self.pipeline.subpipelines:
            return

        _active_runs[self.run_id] = self

        try:
            event_bus = get_event_bus()
            event_bus.emit(SIGNAL_PIPELINE_STARTED, sender=self, run_id=self.run_id, pipeline=self.pipeline.name)

            async with get_session_factory()() as session:
                run_repo = RunRepository(session)
                await run_repo.update_run_status(self.run_id, RunStatus.RUNNING, started_at=datetime.now(timezone.utc))

            sub_levels = self._build_subpipeline_levels()

            failed_subpipelines: Set[str] = set()
            completed_subpipelines: Set[str] = set()

            try:
                for level in sub_levels:
                    if self._cancelled:
                        break

                    subs_to_run = []
                    for sub_name in level:
                        if sub_name in failed_subpipelines:
                            continue
                        subs_to_run.append(sub_name)

                    if not subs_to_run:
                        continue

                    results = await asyncio.gather(
                        *[self._execute_subpipeline(sub_name) for sub_name in subs_to_run],
                        return_exceptions=True,
                    )

                    for sub_name, result in zip(subs_to_run, results):
                        sub = self.pipeline.get_subpipeline_by_name(sub_name)
                        if sub is None:
                            failed_subpipelines.add(sub_name)
                            continue

                        if isinstance(result, BaseException):
                            logger.exception(f"SubPipeline '{sub_name}' raised unexpected exception: {result}")
                            self._unexpected_error = True
                            failed_subpipelines.add(sub_name)
                            for dep_sub in self._get_subpipeline_dependents(sub_name):
                                failed_subpipelines.add(dep_sub)
                        elif isinstance(result, dict) and not result.get("success"):
                            failed_subpipelines.add(sub_name)
                            on_failure = sub.config.on_failure
                            if on_failure != "continue":
                                for dep_sub in self._get_subpipeline_dependents(sub_name):
                                    failed_subpipelines.add(dep_sub)
                        else:
                            completed_subpipelines.add(sub_name)

            except Exception as e:
                logger.exception(f"Pipeline runner {self.run_id} encountered an unexpected error")
                self._unexpected_error = True

            async with get_session_factory()() as session:
                run_repo = RunRepository(session)

                if self._cancelled:
                    final_status = RunStatus.CANCELLED
                elif self._unexpected_error:
                    final_status = RunStatus.FAILED
                elif failed_subpipelines:
                    if completed_subpipelines:
                        final_status = RunStatus.PARTIAL
                    else:
                        final_status = RunStatus.FAILED
                else:
                    final_status = RunStatus.SUCCESS

                await run_repo.update_run_status(self.run_id, final_status, finished_at=datetime.now(timezone.utc))

            event_bus.emit(SIGNAL_RUN_COMPLETED, sender=self, run_id=self.run_id, status=final_status)
        finally:
            _active_runs.pop(self.run_id, None)

    def _build_subpipeline_levels(self) -> List[List[str]]:
        in_degree: Dict[str, int] = {}
        adjacency: Dict[str, List[str]] = {}

        for sub in self.pipeline.subpipelines:
            if sub.name not in in_degree:
                in_degree[sub.name] = 0
                adjacency[sub.name] = []

        for sub in self.pipeline.subpipelines:
            for dep in sub.depends_on:
                if dep not in in_degree:
                    raise ValueError(t("SubPipeline '{name}' depends on unknown subpipeline '{dep}'", name=sub.name, dep=dep))
                adjacency[dep].append(sub.name)
                in_degree[sub.name] += 1

        levels = []
        remaining = set(in_degree.keys())

        while remaining:
            level = [name for name in remaining if in_degree[name] == 0]
            if not level:
                raise DAGCycleError(t("Cycle detected among subpipelines: {names}", names=remaining))
            levels.append(level)
            for name in level:
                remaining.remove(name)
                for neighbor in adjacency[name]:
                    in_degree[neighbor] -= 1

        return levels

    def _get_subpipeline_dependents(self, sub_name: str) -> Set[str]:
        result = set()
        for sub in self.pipeline.subpipelines:
            if sub_name in sub.depends_on:
                result.add(sub.name)
                result.update(self._get_subpipeline_dependents(sub.name))
        return result

    async def _execute_subpipeline(self, sub_name: str) -> dict:
        sub = self.pipeline.get_subpipeline_by_name(sub_name)
        if sub is None:
            return {"success": False, "error": f"SubPipeline '{sub_name}' not found"}

        sub_env = self.context.get_subpipeline_env(sub)

        try:
            dag = DAG(sub.tasks)
            levels = dag.get_execution_levels()
        except (DAGCycleError, ValueError) as e:
            logger.error(t("SubPipeline '{name}' DAG error: {error}", name=sub_name, error=str(e)))
            return {"success": False, "error": str(e)}

        failed_tasks: Set[str] = set()
        completed_tasks: Set[str] = set()
        strategy = sub.config.execution_strategy

        for level in levels:
            if self._cancelled:
                break

            tasks_to_run = []
            for task_name in level:
                task = sub.get_task_by_name(task_name)
                if task is None:
                    continue

                qualified_name = f"{sub.name}.{task_name}"

                on_failure = task.on_failure or sub.config.on_failure or "fail"

                should_skip = False
                for dep in task.depends_on:
                    if dep in failed_tasks:
                        should_skip = (on_failure != "continue")
                        break

                if should_skip:
                    async with get_session_factory()() as session:
                        task_repo = TaskRunRepository(session)
                        task_run_id = self._task_run_ids.get(qualified_name)
                        if task_run_id:
                            await task_repo.update_task_status(task_run_id, TaskStatus.SKIPPED)
                    failed_tasks.add(qualified_name)
                    continue

                tasks_to_run.append(task)

            if tasks_to_run:
                if strategy == "parallel":
                    results = await asyncio.gather(
                        *[self._execute_task(task) for task in tasks_to_run],
                        return_exceptions=True,
                    )
                else:
                    results = []
                    for task in tasks_to_run:
                        if self._cancelled:
                            break
                        result = await self._execute_task(task)
                        results.append(result)

                for task, result in zip(tasks_to_run, results):
                    qualified_name = f"{sub.name}.{task.name}"
                    if isinstance(result, Exception):
                        failed_tasks.add(qualified_name)
                    elif isinstance(result, ExecutorResult) and not result.success:
                        failed_tasks.add(qualified_name)
                    else:
                        completed_tasks.add(qualified_name)

        if failed_tasks:
            return {"success": False, "failed_tasks": list(failed_tasks)}
        return {"success": True}

    async def _execute_task(self, task: ResolvedTask) -> ExecutorResult:
        event_bus = get_event_bus()

        qualified_name = task.name
        task_run_id = self._task_run_ids.get(qualified_name, "")

        if self._pipeline_id and self._pipeline_version:
            log_path = build_log_path(self._pipeline_id, self._pipeline_version, self.run_id, qualified_name)
        else:
            log_path = Path(self._task_run_ids.get(qualified_name, "output.log"))

        env = self.context.get_task_env(task)

        when_env = {**self.pipeline.top_config.env, **task.env, **self.context.env}
        if not _evaluate_when(task.when, when_env):
            async with get_session_factory()() as session:
                task_repo = TaskRunRepository(session)
                if task_run_id:
                    await task_repo.update_task_status(task_run_id, TaskStatus.SKIPPED)
            return ExecutorResult(exit_code=0, stdout="Task skipped (when condition not met)")

        async with get_session_factory()() as session:
            task_repo = TaskRunRepository(session)
            await task_repo.update_task_status(task_run_id, TaskStatus.RUNNING, started_at=datetime.now(timezone.utc))

        event_bus.emit(SIGNAL_TASK_STARTED, sender=self, run_id=self.run_id, task=task.name)

        timeout = task.timeout or get_settings().executor.default_timeout
        max_retries = task.retry

        last_result = ExecutorResult(exit_code=0)
        for attempt in range(max_retries + 1):
            if attempt > 0:
                logger.info(t("Task '{task}' retry {n}/{max}", task=task.name, n=attempt, max=max_retries))
                await asyncio.sleep(5)
                with open(log_path, "a") as f:
                    f.write(t("\n[RETRY {n}/{max}] waiting 5s...\n", n=attempt, max=max_retries))

            executor = create_executor(task)
            self._running_executors[task.name] = executor

            try:
                if isinstance(executor, InvokeExecutor):
                    result = await executor.execute(
                        command="",
                        env=env,
                        log_path=log_path,
                        timeout=timeout,
                        invoke_task=task.invoke_task,
                        invoke_args=task.invoke_args,
                        invoke_kwargs=task.invoke_kwargs,
                    )
                elif isinstance(executor, (GitExecutor, NexusExecutor)):
                    if isinstance(executor, GitExecutor):
                        if not executor.dest or executor.dest == "/workspace/repo":
                            workspace_dir = get_workspaces_dir() / self.run_id / "repo"
                            workspace_dir.mkdir(parents=True, exist_ok=True)
                            executor.dest = str(workspace_dir)
                    result = await executor.execute(
                        command="",
                        env=env,
                        log_path=log_path,
                        timeout=timeout,
                    )
                elif task.task_type == "steps" and task.steps:
                    result = await self._execute_steps(executor, task, env, log_path, timeout)
                elif task.commands:
                    result = await self._execute_commands(executor, task, env, log_path, timeout)
                else:
                    result = await executor.execute(
                        command=task.command or "",
                        env=env,
                        log_path=log_path,
                        timeout=timeout,
                        cwd=task.cwd,
                    )
            except Exception as e:
                result = ExecutorResult(exit_code=1, stderr=str(e))

            self._running_executors.pop(task.name, None)
            last_result = result

            if result.success:
                break

        task_status = TaskStatus.SUCCESS if last_result.success else TaskStatus.FAILED

        async with get_session_factory()() as session:
            task_repo = TaskRunRepository(session)
            await task_repo.update_task_status(
                task_run_id,
                task_status,
                exit_code=last_result.exit_code,
                finished_at=datetime.now(timezone.utc),
            )

        event_bus.emit(SIGNAL_TASK_FINISHED, sender=self, run_id=self.run_id, task=task.name, status=task_status)

        return last_result

    async def _execute_commands(
        self,
        executor: Any,
        task: ResolvedTask,
        env: Dict[str, str],
        log_path: Path,
        timeout: Optional[int],
    ) -> ExecutorResult:
        if not task.commands:
            return ExecutorResult(exit_code=0)

        combined_output = ""
        cmd_timeout = None
        if timeout:
            cmd_timeout = timeout // max(len(task.commands), 1)
            if cmd_timeout < 1:
                cmd_timeout = 1

        for i, cmd in enumerate(task.commands):
            with open(log_path, "a") as f:
                f.write(t("Step {n}/{total}: {cmd}\n", n=i + 1, total=len(task.commands), cmd=cmd[:80]))

            result = await executor.execute(
                command=cmd,
                env=env,
                log_path=log_path,
                timeout=cmd_timeout,
                cwd=task.cwd,
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

    async def _execute_steps(
        self,
        executor: BaseExecutor,
        task: ResolvedTask,
        env: Dict[str, str],
        log_path: Path,
        timeout: Optional[int],
    ) -> ExecutorResult:
        combined_output = ""
        step_timeout = None
        if timeout and task.steps:
            step_timeout = timeout // max(len(task.steps), 1)
            if step_timeout < 1:
                step_timeout = 1

        for i, step in enumerate(task.steps):
            step_env = {**env, **step.env}
            step_cwd = step.cd or task.cwd

            with open(log_path, "a") as f:
                f.write(t("Step {n}/{total}: {cmd}", n=i + 1, total=len(task.steps), cmd=step.run[:80]))

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

    async def cancel(self) -> None:
        self._cancelled = True
        event_bus = get_event_bus()
        event_bus.emit(SIGNAL_RUN_CANCELLED, sender=self, run_id=self.run_id)

        async with get_session_factory()() as session:
            task_repo = TaskRunRepository(session)
            await task_repo.cancel_pending_tasks(self.run_id)

        for name, executor in self._running_executors.items():
            await executor.cancel()


def get_active_runner(run_id: str) -> Optional[PipelineRunner]:
    return _active_runs.get(run_id)
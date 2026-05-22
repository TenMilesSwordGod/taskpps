from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from taskpps.config import get_logs_dir, get_settings
from taskpps.db.engine import get_session_factory
from taskpps.db.repository import RunRepository, TaskRunRepository
from taskpps.i18n import t
from taskpps.domain.context import ExecutionContext
from taskpps.domain.dag import DAG, DAGCycleError
from taskpps.domain.pipeline import ResolvedPipeline, ResolvedTask
from taskpps.events.bus import get_event_bus, SIGNAL_PIPELINE_STARTED, SIGNAL_TASK_STARTED, SIGNAL_TASK_FINISHED, SIGNAL_RUN_COMPLETED, SIGNAL_RUN_CANCELLED
from taskpps.executors import create_executor
from taskpps.executors.base import ExecutorResult
from taskpps.executors.invoke import InvokeExecutor
from taskpps.models.run import RunStatus, TaskStatus


_active_runs: Dict[str, "PipelineRunner"] = {}


class PipelineRunner:
    def __init__(self, run_id: str, pipeline: ResolvedPipeline, context: ExecutionContext):
        self.run_id = run_id
        self.pipeline = pipeline
        self.context = context
        self.dag: Optional[DAG] = None
        self._cancelled = False
        self._running_executors: Dict[str, Any] = {}
        self._task_run_ids: Dict[str, str] = {}

    async def run(self) -> None:
        try:
            self.dag = DAG(self.pipeline.tasks)
        except (DAGCycleError, ValueError) as e:
            async with get_session_factory()() as session:
                run_repo = RunRepository(session)
                await run_repo.update_run_status(self.run_id, RunStatus.FAILED, finished_at=datetime.now(timezone.utc))
            return

        _active_runs[self.run_id] = self

        try:
            event_bus = get_event_bus()
            event_bus.emit(SIGNAL_PIPELINE_STARTED, sender=self, run_id=self.run_id, pipeline=self.pipeline.name)

            async with get_session_factory()() as session:
                run_repo = RunRepository(session)
                task_repo = TaskRunRepository(session)
                await run_repo.update_run_status(self.run_id, RunStatus.RUNNING, started_at=datetime.now(timezone.utc))

            failed_tasks: Set[str] = set()
            completed_tasks: Set[str] = set()

            try:
                levels = self.dag.get_execution_levels()

                for level in levels:
                    if self._cancelled:
                        break

                    tasks_to_run = []
                    for task_name in level:
                        task = self.pipeline.get_task_by_name(task_name)
                        if task is None:
                            continue

                        on_failure = task.on_failure or self.pipeline.options.on_failure or "fail"

                        should_skip = False
                        for dep in task.depends_on:
                            if dep in failed_tasks:
                                should_skip = (on_failure != "continue")
                                break

                        if should_skip:
                            async with get_session_factory()() as session:
                                task_repo = TaskRunRepository(session)
                                task_run_id = self._task_run_ids.get(task_name)
                                if task_run_id:
                                    await task_repo.update_task_status(task_run_id, TaskStatus.SKIPPED)
                            failed_tasks.add(task_name)
                            continue

                        tasks_to_run.append(task)

                    if tasks_to_run:
                        results = await asyncio.gather(
                            *[self._execute_task(task) for task in tasks_to_run],
                            return_exceptions=True,
                        )

                        for task, result in zip(tasks_to_run, results):
                            if isinstance(result, Exception):
                                failed_tasks.add(task.name)
                            elif isinstance(result, ExecutorResult) and not result.success:
                                failed_tasks.add(task.name)
                            else:
                                completed_tasks.add(task.name)

                        # Update run status after each level for real-time monitoring
                        async with get_session_factory()() as session:
                            run_repo = RunRepository(session)
                            if failed_tasks and not completed_tasks:
                                await run_repo.update_run_status(self.run_id, RunStatus.FAILED)
                            elif failed_tasks and completed_tasks:
                                await run_repo.update_run_status(self.run_id, RunStatus.PARTIAL)
                            else:
                                await run_repo.update_run_status(self.run_id, RunStatus.RUNNING)

            except Exception:
                pass

            async with get_session_factory()() as session:
                run_repo = RunRepository(session)

                if self._cancelled:
                    final_status = RunStatus.CANCELLED
                elif failed_tasks:
                    if completed_tasks:
                        final_status = RunStatus.PARTIAL
                    else:
                        final_status = RunStatus.FAILED
                else:
                    final_status = RunStatus.SUCCESS

                await run_repo.update_run_status(self.run_id, final_status, finished_at=datetime.now(timezone.utc))

            event_bus.emit(SIGNAL_RUN_COMPLETED, sender=self, run_id=self.run_id, status=final_status)
        finally:
            _active_runs.pop(self.run_id, None)

    async def _execute_task(self, task: ResolvedTask) -> ExecutorResult:
        event_bus = get_event_bus()
        logs_dir = get_logs_dir()
        log_path = logs_dir / self.pipeline.name / task.name / f"{self.run_id}.log"

        task_run_id = self._task_run_ids.get(task.name, "")

        async with get_session_factory()() as session:
            task_repo = TaskRunRepository(session)
            await task_repo.update_task_status(task_run_id, TaskStatus.RUNNING, started_at=datetime.now(timezone.utc))

        event_bus.emit(SIGNAL_TASK_STARTED, sender=self, run_id=self.run_id, task=task.name)

        env = self.context.get_task_env(task)
        timeout = task.timeout or get_settings().executor.default_timeout

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
            elif task.task_type == "steps" and task.steps:
                result = await self._execute_steps(executor, task, env, log_path, timeout)
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

        task_status = TaskStatus.SUCCESS if result.success else TaskStatus.FAILED

        async with get_session_factory()() as session:
            task_repo = TaskRunRepository(session)
            await task_repo.update_task_status(
                task_run_id,
                task_status,
                exit_code=result.exit_code,
                finished_at=datetime.now(timezone.utc),
            )

        event_bus.emit(SIGNAL_TASK_FINISHED, sender=self, run_id=self.run_id, task=task.name, status=task_status)

        return result

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

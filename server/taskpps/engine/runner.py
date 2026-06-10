from __future__ import annotations

import asyncio
import contextlib
import logging
import os
import re
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from taskpps.config import (  # noqa: F401
    build_log_path,
    build_pipeline_log_path,
    get_logs_dir,
    get_settings,
    get_workspaces_dir,
)
from taskpps.db.engine import get_session_factory
from taskpps.db.repository import RunRepository, TaskRunRepository
from taskpps.domain.context import ExecutionContext
from taskpps.domain.dag import DAG, DAGCycleError
from taskpps.domain.pipeline import ResolvedPipeline, ResolvedTask
from taskpps.events.bus import (
    SIGNAL_PIPELINE_STARTED,
    SIGNAL_RUN_CANCELLED,
    SIGNAL_RUN_COMPLETED,
    SIGNAL_TASK_FINISHED,
    SIGNAL_TASK_STARTED,
    get_event_bus,
)
from taskpps.executors import create_executor
from taskpps.executors.base import BaseExecutor, ExecutorResult
from taskpps.executors.git import GitExecutor
from taskpps.executors.invoke import InvokeExecutor
from taskpps.executors.local import LocalExecutor
from taskpps.executors.nexus import NexusExecutor
from taskpps.i18n import t
from taskpps.models.run import RunStatus, TaskStatus

logger = logging.getLogger(__name__)
_active_runs: dict[str, PipelineRunner] = {}

_WHEN_PATTERN = re.compile(r'\$\{env\.([^}]+)\}\s*(==|!=)\s*"([^"]*)"')


def _evaluate_when(when_expr: str | None, env: dict[str, str]) -> bool:
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
        self.dag: DAG | None = None
        self._cancelled = False
        self._unexpected_error = False
        self._running_executors: dict[str, Any] = {}
        self._task_run_ids: dict[str, str] = {}
        self._pipeline_id: str = ""
        self._pipeline_version: str = ""
        self._pipeline_log_path: Path | None = None
        self._start_time: datetime | None = None

    def _init_pipeline_log(self) -> None:
        """Initialize pipeline-level console.log for runtime logging."""
        if self._pipeline_id and self._pipeline_version:
            self._pipeline_log_path = build_pipeline_log_path(self._pipeline_id, self._pipeline_version, self.run_id)

            with open(self._pipeline_log_path, "w") as f:
                f.write(f"{'=' * 80}\n")
                f.write("Pipeline Execution Log\n")
                f.write(f"{'=' * 80}\n\n")
                f.write(f"[SYSTEM] Run ID: {self.run_id}\n")
                f.write(f"[SYSTEM] Pipeline ID: {self._pipeline_id}\n")
                f.write(f"[SYSTEM] Pipeline Version: {self._pipeline_version}\n")
                f.write(f"[SYSTEM] Pipeline Name: {self.pipeline.name}\n")
                f.write(f"[SYSTEM] Start Time: {datetime.now(timezone.utc).isoformat()}\n")
                f.write(f"[SYSTEM] Working Directory: {os.getcwd()}\n")
                f.write(f"[SYSTEM] Python Version: {os.sys.version}\n\n")

                settings = get_settings()
                f.write(f"[CONFIG] Default Timeout: {settings.executor.default_timeout}s\n")
                f.write(f"[CONFIG] Max Workers: {settings.executor.max_workers}\n")
                f.write(f"[CONFIG] Shell: {settings.executor.shell}\n\n")

                if self.pipeline.subpipelines:
                    f.write(f"[PIPELINE] SubPipelines: {len(self.pipeline.subpipelines)}\n")
                    for sub in self.pipeline.subpipelines:
                        f.write(
                            f"[PIPELINE]   - {sub.name}: {len(sub.tasks)} tasks (strategy: {sub.config.execution_strategy})\n"
                        )
                    f.write("\n")
                # Flush Python buffers and push the header to the OS page
                # cache so that a concurrent reader sees it immediately
                # and not just on file-close. See issue #15.
                f.flush()
                with contextlib.suppress(OSError):
                    os.fsync(f.fileno())

    def _write_separator(self, char: str, label: str = "") -> None:
        """Write a full-width separator line with an optional label."""
        if self._pipeline_log_path:
            W = 80
            try:
                with open(self._pipeline_log_path, "a") as f:
                    f.write(char * W + "\n")
                    if label:
                        padding = (W - len(label)) // 2
                        f.write(
                            char + " " * max(padding - 1, 0) + label + " " * max(W - padding - len(label) - 1, 0) + "\n"
                        )
                        f.write(char * W + "\n")
                    f.flush()
            except Exception as e:
                logger.error(f"Failed to write separator to pipeline log: {e}")

    def _write_pipeline_log(self, level: str, message: str) -> None:
        """Write a message to the pipeline-level console.log."""
        if self._pipeline_log_path:
            try:
                timestamp = datetime.now(timezone.utc).isoformat()
                with open(self._pipeline_log_path, "a") as f:
                    f.write(f"[{level}] [{timestamp}] {message}\n")
                    # Flush after every entry so a reader tailing the log
                    # (or the user inspecting console.log right after a
                    # single task completes) sees every line, not just
                    # the last one. Without this, the first few lines
                    # can be lost when the server is still running and
                    # the OS has not yet drained its write buffer.
                    # See issue #15.
                    f.flush()
            except Exception as e:
                logger.error(f"Failed to write to pipeline log: {e}")

    async def run(self) -> None:
        if not self.pipeline.subpipelines:
            logger.info("PipelineRunner: no subpipelines, returning immediately")
            return

        _active_runs[self.run_id] = self
        self._start_time = datetime.now(timezone.utc)
        self._init_pipeline_log()

        logger.info("PipelineRunner: starting pipeline '%s' run_id=%s", self.pipeline.name, self.run_id)

        try:
            event_bus = get_event_bus()
            event_bus.emit(SIGNAL_PIPELINE_STARTED, sender=self, run_id=self.run_id, pipeline=self.pipeline.name)

            self._write_pipeline_log("INFO", f"Pipeline '{self.pipeline.name}' started")
            self._write_pipeline_log("INFO", f"Total subpipelines: {len(self.pipeline.subpipelines)}")

            async with get_session_factory()() as session:
                run_repo = RunRepository(session)
                await run_repo.update_run_status(self.run_id, RunStatus.RUNNING, started_at=self._start_time)

            try:
                sub_levels = self._build_subpipeline_levels()
                logger.info("PipelineRunner: built %d execution levels", len(sub_levels))
            except Exception as e:
                error_msg = f"Failed to build subpipeline execution levels: {e}"
                logger.exception(error_msg)
                self._write_pipeline_log("ERROR", error_msg)
                self._write_pipeline_log("ERROR", f"Traceback:\n{traceback.format_exc()}")
                self._unexpected_error = True
                sub_levels = []

            if sub_levels:
                self._write_pipeline_log("INFO", f"Execution levels: {len(sub_levels)}")

            failed_subpipelines: set[str] = set()
            completed_subpipelines: set[str] = set()

            try:
                for level_idx, level in enumerate(sub_levels):
                    if self._cancelled:
                        self._write_pipeline_log("WARN", "Pipeline execution cancelled by user")
                        break

                    self._write_pipeline_log("INFO", f"Executing level {level_idx + 1}/{len(sub_levels)}: {level}")

                    subs_to_run = []
                    for sub_name in level:
                        if sub_name in failed_subpipelines:
                            self._write_pipeline_log("SKIP", f"SubPipeline '{sub_name}' skipped (dependency failed)")
                            continue
                        subs_to_run.append(sub_name)

                    if not subs_to_run:
                        continue

                    # Within a level, subpipelines have no remaining
                    # inter-dependencies. We still run them one at a time
                    # in YAML order rather than with asyncio.gather so that
                    # console.log is written in a single coherent stream
                    # per subpipeline, instead of being interleaved across
                    # them. See issue #13.
                    for sub_name in subs_to_run:
                        if self._cancelled:
                            break
                        try:
                            result = await self._execute_subpipeline(sub_name)
                        except BaseException as exc:
                            result = exc

                        sub = self.pipeline.get_subpipeline_by_name(sub_name)
                        if sub is None:
                            failed_subpipelines.add(sub_name)
                            self._write_pipeline_log("ERROR", f"SubPipeline '{sub_name}' not found")
                            continue

                        if isinstance(result, BaseException):
                            error_msg = f"SubPipeline '{sub_name}' raised unexpected exception: {result}"
                            logger.exception(error_msg)
                            self._write_pipeline_log("ERROR", error_msg)
                            self._write_pipeline_log("ERROR", f"Traceback:\n{traceback.format_exc()}")
                            self._unexpected_error = True
                            failed_subpipelines.add(sub_name)
                            for dep_sub in self._get_subpipeline_dependents(sub_name):
                                failed_subpipelines.add(dep_sub)
                        elif isinstance(result, dict) and not result.get("success"):
                            failed_tasks = result.get("failed_tasks", [])
                            self._write_pipeline_log(
                                "FAILED", f"SubPipeline '{sub_name}' failed. Failed tasks: {failed_tasks}"
                            )
                            failed_subpipelines.add(sub_name)
                            on_failure = sub.config.on_failure
                            if on_failure != "continue":
                                for dep_sub in self._get_subpipeline_dependents(sub_name):
                                    failed_subpipelines.add(dep_sub)
                                    self._write_pipeline_log(
                                        "SKIP", f"Marking dependent subpipeline '{dep_sub}' as failed"
                                    )
                        else:
                            completed_subpipelines.add(sub_name)
                            self._write_pipeline_log("SUCCESS", f"SubPipeline '{sub_name}' completed successfully")

            except Exception as e:
                error_msg = f"Pipeline runner {self.run_id} encountered an unexpected error"
                logger.exception(error_msg)
                self._write_pipeline_log("ERROR", f"{error_msg}: {e}")
                self._write_pipeline_log("ERROR", f"Traceback:\n{traceback.format_exc()}")
                self._unexpected_error = True

            end_time = datetime.now(timezone.utc)
            duration = end_time - self._start_time

            async with get_session_factory()() as session:
                run_repo = RunRepository(session)

                if self._cancelled:
                    final_status = RunStatus.CANCELLED
                    self._write_pipeline_log("CANCELLED", f"Pipeline cancelled after {duration}")
                elif self._unexpected_error:
                    final_status = RunStatus.FAILED
                    self._write_pipeline_log("FAILED", f"Pipeline failed after {duration} (unexpected error)")
                elif failed_subpipelines:
                    final_status = RunStatus.PARTIAL if completed_subpipelines else RunStatus.FAILED
                    self._write_pipeline_log(
                        "PARTIAL" if final_status == RunStatus.PARTIAL else "FAILED",
                        f"Pipeline finished with status: {final_status.value}. "
                        f"Failed: {len(failed_subpipelines)}, Completed: {len(completed_subpipelines)}. Duration: {duration}",
                    )
                else:
                    final_status = RunStatus.SUCCESS
                    self._write_pipeline_log("SUCCESS", f"Pipeline completed successfully after {duration}")
                logger.info(
                    "PipelineRunner: finished run_id=%s status=%s duration=%s",
                    self.run_id,
                    final_status.value,
                    duration,
                )

                await run_repo.update_run_status(self.run_id, final_status, finished_at=end_time)

            self._write_pipeline_log("SYSTEM", f"End Time: {end_time.isoformat()}")
            self._write_pipeline_log("SYSTEM", f"Duration: {duration}")
            self._write_pipeline_log("SYSTEM", "=" * 80)

            event_bus.emit(SIGNAL_RUN_COMPLETED, sender=self, run_id=self.run_id, status=final_status)
        finally:
            _active_runs.pop(self.run_id, None)

    def _build_subpipeline_levels(self) -> list[list[str]]:
        in_degree: dict[str, int] = {}
        adjacency: dict[str, list[str]] = {}
        # Track the original YAML position of each subpipeline so the
        # level ordering is deterministic and matches what the user wrote
        # in the YAML file (set iteration order is not guaranteed and
        # would otherwise produce a confusing console.log). See issue #13.
        yaml_index: dict[str, int] = {}

        for idx, sub in enumerate(self.pipeline.subpipelines):
            if sub.name not in in_degree:
                in_degree[sub.name] = 0
                adjacency[sub.name] = []
                yaml_index[sub.name] = idx

        for sub in self.pipeline.subpipelines:
            for dep in sub.depends_on:
                if dep not in in_degree:
                    raise ValueError(
                        t("SubPipeline '{name}' depends on unknown subpipeline '{dep}'", name=sub.name, dep=dep)
                    )
                adjacency[dep].append(sub.name)
                in_degree[sub.name] += 1

        levels = []
        remaining = set(in_degree.keys())

        while remaining:
            ready = [name for name in remaining if in_degree[name] == 0]
            if not ready:
                raise DAGCycleError(t("Cycle detected among subpipelines: {names}", names=remaining))
            ready.sort(key=lambda n: yaml_index[n])
            levels.append(ready)
            for name in ready:
                remaining.remove(name)
                for neighbor in adjacency[name]:
                    in_degree[neighbor] -= 1

        return levels

    def _get_subpipeline_dependents(self, sub_name: str) -> set[str]:
        result = set()
        for sub in self.pipeline.subpipelines:
            if sub_name in sub.depends_on:
                result.add(sub.name)
                result.update(self._get_subpipeline_dependents(sub.name))
        return result

    async def _execute_subpipeline(self, sub_name: str) -> dict:
        sub = self.pipeline.get_subpipeline_by_name(sub_name)
        if sub is None:
            logger.error("PipelineRunner: subpipeline '%s' not found", sub_name)
            return {"success": False, "error": f"SubPipeline '{sub_name}' not found"}

        logger.info(
            "PipelineRunner: executing subpipeline '%s' strategy=%s tasks=%d",
            sub_name,
            sub.config.execution_strategy,
            len(sub.tasks),
        )
        self.context.get_subpipeline_env(sub)
        self._write_separator("=", f"[subpipeline] {sub_name} start")
        self._write_pipeline_log("INFO", f"Starting SubPipeline '{sub_name}' with {len(sub.tasks)} tasks")

        try:
            dag = DAG(sub.tasks)
            levels = dag.get_execution_levels()
        except (DAGCycleError, ValueError) as e:
            error_msg = f"SubPipeline '{sub_name}' DAG error: {e}"
            logger.error(t(error_msg))
            self._write_pipeline_log("ERROR", error_msg)
            self._write_separator("=", f"[subpipeline] {sub_name} end")
            return {"success": False, "error": str(e)}

        self._write_pipeline_log("INFO", f"SubPipeline '{sub_name}' has {len(levels)} execution levels")

        failed_tasks: set[str] = set()
        completed_tasks: set[str] = set()
        strategy = sub.config.execution_strategy
        self._write_pipeline_log("INFO", f"Execution strategy: {strategy}")

        for level_idx, level in enumerate(levels):
            if self._cancelled:
                self._write_pipeline_log("WARN", f"SubPipeline '{sub_name}' cancelled at level {level_idx + 1}")
                break

            self._write_pipeline_log("DEBUG", f"SubPipeline '{sub_name}' level {level_idx + 1}: {level}")

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
                        should_skip = on_failure != "continue"
                        break

                if should_skip:
                    async with get_session_factory()() as session:
                        task_repo = TaskRunRepository(session)
                        task_run_id = self._task_run_ids.get(qualified_name)
                        if task_run_id:
                            await task_repo.update_task_status(task_run_id, TaskStatus.SKIPPED)
                    failed_tasks.add(qualified_name)
                    self._write_pipeline_log("SKIP", f"Task '{qualified_name}' skipped (dependency failed)")
                    continue

                tasks_to_run.append(task)

            if tasks_to_run:
                if strategy == "parallel":
                    self._write_pipeline_log("DEBUG", f"Executing {len(tasks_to_run)} tasks in parallel")
                    results = await asyncio.gather(
                        *[self._execute_task(task, sub_name) for task in tasks_to_run],
                        return_exceptions=True,
                    )
                else:
                    self._write_pipeline_log("DEBUG", f"Executing {len(tasks_to_run)} tasks sequentially")
                    results = []
                    for task in tasks_to_run:
                        if self._cancelled:
                            break
                        result = await self._execute_task(task, sub_name)
                        results.append(result)

                for task, result in zip(tasks_to_run, results, strict=False):
                    qualified_name = f"{sub.name}.{task.name}"
                    if isinstance(result, Exception) or (isinstance(result, ExecutorResult) and not result.success):
                        failed_tasks.add(qualified_name)
                        if isinstance(result, ExecutorResult):
                            exit_code = result.exit_code
                            if exit_code < 0:
                                self._write_pipeline_log(
                                    "FAILED",
                                    f"Task '{qualified_name}' failed with exit code: {exit_code} (process was killed by signal or did not start properly)",
                                )
                            else:
                                self._write_pipeline_log(
                                    "FAILED", f"Task '{qualified_name}' failed with exit code: {exit_code}"
                                )
                        else:
                            exit_code = -1
                            self._write_pipeline_log(
                                "FAILED", f"Task '{qualified_name}' failed with unexpected exception: {result}"
                            )
                    else:
                        completed_tasks.add(qualified_name)
                        exit_code = result.exit_code if isinstance(result, ExecutorResult) else 0
                        self._write_pipeline_log(
                            "SUCCESS", f"Task '{qualified_name}' completed with exit code: {exit_code}"
                        )

        if failed_tasks:
            self._write_pipeline_log(
                "FAILED", f"SubPipeline '{sub_name}' finished with {len(failed_tasks)} failed tasks"
            )
            self._write_separator("=", f"[subpipeline] {sub_name} end")
            return {"success": False, "failed_tasks": list(failed_tasks)}

        self._write_pipeline_log(
            "SUCCESS",
            f"SubPipeline '{sub_name}' completed successfully ({len(completed_tasks)}/{len(sub.tasks)} tasks)",
        )
        self._write_separator("=", f"[subpipeline] {sub_name} end")
        return {"success": True}

    async def _execute_task(self, task: ResolvedTask, sub_name: str = "") -> ExecutorResult:
        event_bus = get_event_bus()

        qualified_name = f"{sub_name}.{task.name}" if sub_name else task.name
        task_run_id = self._task_run_ids.get(qualified_name, "")

        if self._pipeline_id and self._pipeline_version:
            log_path = build_log_path(self._pipeline_id, self._pipeline_version, self.run_id, qualified_name)
        else:
            log_path = Path(self._task_run_ids.get(qualified_name, "task.log"))

        env = self.context.get_task_env(task)
        env["TASKPPS_RUN_ID"] = self.run_id
        env["TASKPPS_TASK_ID"] = task_run_id or qualified_name

        logger.debug(
            f"[DEBUG-EXEC] _execute_task '{qualified_name}': task_type={task.task_type}, command={task.command!r:.200}, commands={task.commands}, steps={task.steps}, cwd={task.cwd}"
        )
        logger.debug(
            f"[DEBUG-EXEC] _execute_task '{qualified_name}': timeout={task.timeout}, retry={task.retry}, log_path={log_path}"
        )

        when_env = {**self.pipeline.top_config.env, **task.env, **self.context.env}
        if not _evaluate_when(task.when, when_env):
            logger.info("PipelineRunner: task '%s' skipped due to when condition", qualified_name)
            async with get_session_factory()() as session:
                task_repo = TaskRunRepository(session)
                if task_run_id:
                    await task_repo.update_task_status(task_run_id, TaskStatus.SKIPPED)
            self._write_pipeline_log("SKIP", f"Task '{qualified_name}' skipped (when condition not met)")
            return ExecutorResult(exit_code=0, stdout="Task skipped (when condition not met)")

        if self._cancelled:
            logger.info("PipelineRunner: task '%s' cancelled before execution", qualified_name)
            async with get_session_factory()() as session:
                task_repo = TaskRunRepository(session)
                if task_run_id:
                    await task_repo.update_task_status(task_run_id, TaskStatus.CANCELLED)
            self._write_pipeline_log("CANCELLED", f"Task '{qualified_name}' cancelled before execution")
            return ExecutorResult(exit_code=-1, stdout="Task cancelled")

        self._write_separator("-", f"[task] {qualified_name} start")
        self._write_pipeline_log(
            "INFO", f"Executing task '{qualified_name}' (type: {task.task_type}, timeout: {task.timeout or 'default'})"
        )
        if task.cwd:
            self._write_pipeline_log("INFO", f"  cwd: {task.cwd}")

        if task.task_type == "invoke":
            self._write_pipeline_log("CMD", f"  invoke: {task.invoke_task}")
        elif task.task_type == "git" and task.git:
            self._write_pipeline_log("CMD", f"  git: {task.git.get('action', 'clone')} {task.git.get('repo', '')}")
        elif task.task_type == "nexus" and task.nexus:
            self._write_pipeline_log("CMD", f"  nexus: {task.nexus.get('action', '')} {task.nexus.get('url', '')}")
        elif task.task_type == "steps" and task.steps:
            self._write_pipeline_log("CMD", f"  steps: {len(task.steps)} step(s)")
        elif task.commands:
            self._write_pipeline_log("CMD", f"  commands: {len(task.commands)} command(s)")
        else:
            cmd = task.command or ""
            self._write_pipeline_log("CMD", f"  command: {cmd}")

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
                self._write_pipeline_log("RETRY", f"Task '{qualified_name}' retry {attempt}/{max_retries} (waiting 5s)")
                await asyncio.sleep(5)
                with open(log_path, "a") as f:
                    f.write(t("\n[RETRY {n}/{max}] waiting 5s...\n", n=attempt, max=max_retries))

            effective_cwd = task.cwd or self.context.get_workspace()

            try:
                executor = create_executor(task, self.context.project_workdir)
                self._running_executors[task.name] = executor

                logger.debug(
                    f"[DEBUG-EXEC] _execute_task '{qualified_name}': attempt={attempt}, executor={type(executor).__name__}, effective_cwd={effective_cwd}"
                )

                if effective_cwd and isinstance(executor, LocalExecutor) and not os.path.isdir(effective_cwd):
                    self._write_pipeline_log(
                        "WARN", f"Task '{qualified_name}' cwd does not exist: {effective_cwd}, using current dir"
                    )
                    effective_cwd = os.getcwd()

                if isinstance(executor, InvokeExecutor):
                    logger.debug(f"[DEBUG-EXEC] '{qualified_name}': InvokeExecutor path")
                    logger.info("PipelineRunner: task '%s' dispatching to InvokeExecutor", qualified_name)
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
                    logger.debug(f"[DEBUG-EXEC] '{qualified_name}': {type(executor).__name__} path")
                    logger.info("PipelineRunner: task '%s' dispatching to %s", qualified_name, type(executor).__name__)
                    if isinstance(executor, GitExecutor) and (not executor.dest or executor.dest == "/workspace/repo"):
                        workspace_dir = get_workspaces_dir() / self.run_id / "repo"
                        workspace_dir.mkdir(parents=True, exist_ok=True)
                        executor.dest = str(workspace_dir)
                    result = await executor.execute(
                        command="",
                        env=env,
                        log_path=log_path,
                        timeout=timeout,
                    )
                    if isinstance(executor, GitExecutor) and result.success:
                        self.context.set_workspace(task.name, executor.dest)
                elif task.task_type == "steps" and task.steps:
                    logger.debug(f"[DEBUG-EXEC] '{qualified_name}': steps path, {len(task.steps)} steps")
                    logger.info(
                        "PipelineRunner: task '%s' dispatching to steps executor (%d steps)",
                        qualified_name,
                        len(task.steps),
                    )
                    result = await self._execute_steps(executor, task, env, log_path, timeout, effective_cwd)
                elif task.commands:
                    logger.debug(f"[DEBUG-EXEC] '{qualified_name}': commands path, {len(task.commands)} commands")
                    logger.info(
                        "PipelineRunner: task '%s' dispatching to commands executor (%d commands)",
                        qualified_name,
                        len(task.commands),
                    )
                    result = await self._execute_commands(executor, task, env, log_path, timeout, effective_cwd)
                else:
                    cmd = task.command or ""
                    if not cmd.strip():
                        self._write_pipeline_log("WARN", f"Task '{qualified_name}' has an empty command")
                    logger.debug(f"[DEBUG-EXEC] '{qualified_name}': single command path, cmd={cmd!r:.200}")
                    logger.info("PipelineRunner: task '%s' dispatching to single command executor", qualified_name)
                    result = await executor.execute(
                        command=cmd,
                        env=env,
                        log_path=log_path,
                        timeout=timeout,
                        cwd=effective_cwd,
                    )
            except Exception as e:
                error_msg = f"Unexpected error executing task '{qualified_name}': {e}"
                logger.exception(error_msg)
                self._write_pipeline_log("ERROR", error_msg)
                self._write_pipeline_log("ERROR", f"Traceback:\n{traceback.format_exc()}")
                # 将错误信息写入 task.log，确保 UI 上可查看
                try:
                    with open(log_path, "a") as f:
                        f.write(f"\n[ERROR] {error_msg}\n")
                        f.write(f"[ERROR] Traceback:\n{traceback.format_exc()}")
                except Exception:
                    pass
                result = ExecutorResult(exit_code=1, stderr=str(e))

            self._running_executors.pop(task.name, None)
            last_result = result

            logger.debug(
                f"[DEBUG-EXEC] '{qualified_name}': result exit_code={result.exit_code}, success={result.success}, stderr={result.stderr!r:.200}"
            )
            self._write_pipeline_log(
                "DEBUG", f"Task '{qualified_name}' result: exit_code={result.exit_code}, success={result.success}"
            )

            if result.success:
                break

        if self._cancelled:
            task_status = TaskStatus.CANCELLED
        else:
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

        if not last_result.success:
            self._write_pipeline_log("ERROR", f"Task '{qualified_name}' failed with exit code {last_result.exit_code}")
            if last_result.stderr:
                self._write_pipeline_log("ERROR", f"Error output: {last_result.stderr[:500]}")

        self._write_separator("-", f"[task] {qualified_name} end")
        return last_result

    async def _execute_commands(
        self,
        executor: Any,
        task: ResolvedTask,
        env: dict[str, str],
        log_path: Path,
        timeout: int | None,
        effective_cwd: str | None = None,
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
            self._write_pipeline_log("CMD", f"  [{i + 1}/{len(task.commands)}] {cmd}")
            with open(log_path, "a") as f:
                f.write(t("Command {n}/{total}: {cmd}\n", n=i + 1, total=len(task.commands), cmd=cmd[:80]))

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

    async def _execute_steps(
        self,
        executor: BaseExecutor,
        task: ResolvedTask,
        env: dict[str, str],
        log_path: Path,
        timeout: int | None,
        effective_cwd: str | None = None,
    ) -> ExecutorResult:
        combined_output = ""
        step_timeout = None
        if timeout and task.steps:
            step_timeout = timeout // max(len(task.steps), 1)
            if step_timeout < 1:
                step_timeout = 1

        for i, step in enumerate(task.steps):
            step_env = {**env, **step.env}
            step_cwd = step.cd or effective_cwd

            step_desc = f"  [{i + 1}/{len(task.steps)}]"
            if step.cd:
                step_desc += f" cd {step.cd} &&"
            step_desc += f" {step.run}"
            self._write_pipeline_log("CMD", step_desc)

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
        logger.info("PipelineRunner.cancel: run_id=%s", self.run_id)
        self._write_pipeline_log("WARN", "Pipeline cancellation requested")
        event_bus = get_event_bus()
        event_bus.emit(SIGNAL_RUN_CANCELLED, sender=self, run_id=self.run_id)

        async with get_session_factory()() as session:
            run_repo = RunRepository(session)
            task_repo = TaskRunRepository(session)
            # Persist the cancelled status up front so the run does not appear
            # as "running" while waiting for the in-flight task to drain.
            # finished_at is left unset and will be filled in by run()'s final
            # status update with the real end time.
            await run_repo.update_run_status(self.run_id, RunStatus.CANCELLED)
            await task_repo.cancel_pending_tasks(self.run_id)

        for _name, executor in self._running_executors.items():
            self._write_pipeline_log("INFO", f"Cancelling running executor for task: {_name}")
            await executor.cancel()

        self._write_pipeline_log("WARN", "Pipeline cancellation completed")


def get_active_runner(run_id: str) -> PipelineRunner | None:
    return _active_runs.get(run_id)

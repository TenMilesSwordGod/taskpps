from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from taskpps.config import (
    build_log_path,
    build_pipeline_log_path,
    build_retry_log_path,
    compute_pipeline_id,
    compute_pipeline_version,
    get_logs_dir,
    get_pipelines_dir,
)
from taskpps.db.engine import get_session_factory
from taskpps.db.repository import RetryRecordRepository, RunRepository, TaskRunRepository
from taskpps.domain.context import ExecutionContext, apply_overrides
from taskpps.domain.dag import DAG, DAGCycleError
from taskpps.domain.pipeline import ResolvedPipeline, ResolvedTask
from taskpps.engine.retry_runner import RetryRunner
from taskpps.engine.runner import PipelineRunner
from taskpps.i18n import t
from taskpps.loaders.pipeline_loader import PipelineLoader

logger = logging.getLogger("taskpps.services.pipeline_service")
from taskpps.models.run import RunStatus, TaskStatus
from taskpps.schemas.pipeline import PipelineYAML
from taskpps.schemas.run import DependencyNode


def _ensure_utc(dt: datetime | None) -> datetime | None:
    if dt is not None and dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


class PipelineService:
    # Per-pipeline asyncio.Lock to make the max_parallel check and run
    # creation atomic within a single event loop. The dict is class-level
    # so it is shared across PipelineService instances within one process.
    # NOTE: with gunicorn's multi-worker setup, this only protects against
    # concurrent calls handled by the same worker. Cross-worker safety
    # relies on a single-writer-per-pipeline pattern at the DB layer; that
    # constraint is enforced by SQLite's BEGIN IMMEDIATE behavior in the
    # underlying session when status is updated to 'running' on the runner.
    _pipeline_locks: dict[str, asyncio.Lock] = {}

    def __init__(self):
        self.loader = PipelineLoader()

    @classmethod
    def _get_pipeline_lock(cls, pipeline_id: str) -> asyncio.Lock:
        lock = cls._pipeline_locks.get(pipeline_id)
        if lock is None:
            lock = asyncio.Lock()
            cls._pipeline_locks[pipeline_id] = lock
        return lock

    async def create_run(
        self, pipeline_file: str, params: dict[str, Any] | None = None, project_id: str | None = None
    ) -> dict:
        try:
            # 构建完整的 env 字典, 包含从 settings 和 params 提取的环境变量
            from taskpps.config import get_settings

            settings = get_settings()
            loader_env = settings.env.copy()

            # 如果有 params, 提取其中的 config.env
            if params:
                config_env = params.get("config", {}).get("env", {})
                if isinstance(config_env, dict):
                    loader_env.update(config_env)

            project_workdir = None
            if project_id:
                from taskpps.config import get_project_workdir_by_id

                project_workdir = get_project_workdir_by_id(project_id)
                if project_workdir:
                    from taskpps.config import get_pipelines_dir

                    loader = PipelineLoader(base_dir=get_pipelines_dir(project_workdir))
                else:
                    raise ValueError(f"Project not found: {project_id}")
                spec = loader.load(pipeline_file, loader_env)
            else:
                # 未指定 project_id 时，遍历所有已注册项目查找 pipeline
                from taskpps.db.repository import ProjectRepository

                async with get_session_factory()() as session:
                    repo = ProjectRepository(session)
                    projects = await repo.list_projects()

                spec = None
                for proj in projects:
                    loader = PipelineLoader(base_dir=get_pipelines_dir(proj.workdir))
                    try:
                        spec = loader.load(pipeline_file, loader_env)
                        project_id = proj.id
                        project_workdir = Path(proj.workdir)
                        break
                    except FileNotFoundError:
                        continue

                if spec is None:
                    # 回退到默认 loader
                    spec = self.loader.load(pipeline_file, loader_env)
        except FileNotFoundError as e:
            raise ValueError(str(e)) from e
        except Exception as e:
            raise ValueError(t("Failed to load pipeline: {error}", error=str(e))) from e

        if params:
            pipeline_data = spec.model_dump()
            try:
                overridden = apply_overrides(pipeline_data, params)
                spec = PipelineYAML(**overridden)
            except Exception as e:
                raise ValueError(t("Failed to apply overrides: {error}", error=str(e))) from e

        resolved = ResolvedPipeline.from_yaml(spec, pipeline_file=pipeline_file)

        for sub in resolved.subpipelines:
            try:
                dag = DAG(sub.tasks)
                dag.topological_sort()
            except (DAGCycleError, ValueError) as e:
                raise ValueError(t("SubPipeline '{name}': {error}", name=sub.name, error=str(e))) from e

        pipeline_id = compute_pipeline_id(pipeline_file)
        pipeline_version = compute_pipeline_version(
            pipeline_file,
            pipelines_dir=get_pipelines_dir(project_workdir) if project_workdir else None,
        )

        async with self._get_pipeline_lock(pipeline_id):
            return await self._create_run_locked(
                resolved=resolved,
                pipeline_file=pipeline_file,
                params=params,
                pipeline_id=pipeline_id,
                pipeline_version=pipeline_version,
                project_id=project_id,
                project_workdir=str(project_workdir) if project_workdir else None,
            )

    async def _create_run_locked(
        self,
        *,
        resolved: ResolvedPipeline,
        pipeline_file: str,
        params: dict[str, Any] | None,
        pipeline_id: str,
        pipeline_version: str,
        project_id: str | None = None,
        project_workdir: str | None = None,
    ) -> dict:
        # The caller is expected to hold PipelineService._get_pipeline_lock(pipeline_id).
        async with get_session_factory()() as session:
            run_repo = RunRepository(session)
            task_repo = TaskRunRepository(session)

            # Enforce max_parallel (atomic with run creation under the per-pipeline lock)
            max_parallel = resolved.top_config.max_parallel
            if max_parallel is not None and max_parallel > 0:
                active_count = await run_repo.count_runs(pipeline_id=pipeline_id, status="running")
                active_count += await run_repo.count_runs(pipeline_id=pipeline_id, status="pending")
                if active_count >= max_parallel:
                    raise ValueError(
                        t(
                            "Cannot start pipeline: max_parallel={max} reached ({active} active runs)",
                            max=max_parallel,
                            active=active_count,
                        )
                    )

            last_run = await run_repo.get_last_run_by_pipeline(pipeline_id)
            version_changed = (
                last_run is not None
                and last_run.pipeline_version != ""
                and last_run.pipeline_version != pipeline_version
            )

            run = await run_repo.create_run(
                pipeline_name=resolved.name,
                pipeline_file=pipeline_file,
                pipeline_id=pipeline_id,
                pipeline_version=pipeline_version,
                params=params,
                project_id=project_id,
            )

            task_run_ids = {}

            for sub in resolved.subpipelines:
                for task in sub.tasks:
                    qualified_name = f"{sub.name}.{task.name}"
                    log_path = build_log_path(pipeline_id, pipeline_version, run.id, qualified_name)
                    task_run = await task_repo.create_task_run(
                        run_id=run.id,
                        task_name=qualified_name,
                        task_type=task.task_type,
                        subpipeline_name=sub.name,
                        log_path=str(log_path),
                    )
                    task_run_ids[qualified_name] = task_run.id

        self._save_pipeline_snapshot(pipeline_file, pipeline_id, pipeline_version, run.id)

        context = ExecutionContext(pipeline=resolved, run_id=run.id, env=params, project_workdir=project_workdir)

        runner = PipelineRunner(run_id=run.id, pipeline=resolved, context=context)
        runner._task_run_ids = task_run_ids
        runner._pipeline_id = pipeline_id
        runner._pipeline_version = pipeline_version

        from taskpps.engine.runner import _active_runs

        _active_runs[run.id] = runner

        asyncio_task = asyncio.create_task(runner.run())
        asyncio_task.add_done_callback(self._handle_run_error)

        return {
            "id": run.id,
            "pipeline_name": run.pipeline_name,
            "pipeline_id": pipeline_id,
            "pipeline_version": pipeline_version,
            "version_changed": version_changed,
            "status": run.status,
        }

    @staticmethod
    def _save_pipeline_snapshot(pipeline_file: str, pipeline_id: str, pipeline_version: str, run_id: str) -> None:
        pipelines_dir = get_pipelines_dir()
        p = Path(pipeline_file)
        if len(p.parts) > 0 and p.parts[0] == pipelines_dir.name:
            p = Path(*p.parts[1:])
        src = pipelines_dir / p
        if not src.exists():
            return
        snapshot_dir = get_logs_dir() / pipeline_id / f"v_{pipeline_version}" / "builds" / run_id
        snapshot_dir.mkdir(parents=True, exist_ok=True)
        dst = snapshot_dir / "pipeline-snapshot.yaml"
        shutil.copy2(src, dst)

    @staticmethod
    def _handle_run_error(task: asyncio.Task):
        try:
            task.result()
        except asyncio.CancelledError:
            import logging

            logging.getLogger("taskpps").info(t("Pipeline run was cancelled"))
        except Exception as e:
            import logging

            logging.getLogger("taskpps").error(t("Pipeline run failed unexpectedly: {error}", error=str(e)))

    async def get_run(self, run_id: str) -> dict | None:
        async with get_session_factory()() as session:
            run_repo = RunRepository(session)
            task_repo = TaskRunRepository(session)

            run = await run_repo.get_run(run_id)
            if run is None:
                return None

            tasks = await task_repo.list_task_runs(run_id)

            params = {}
            if isinstance(run.params, str):
                with contextlib.suppress(json.JSONDecodeError, TypeError):
                    params = json.loads(run.params)
            elif isinstance(run.params, dict):
                params = run.params

            console_log_path = ""
            if run.pipeline_id and run.pipeline_version:
                console_log_path = str(build_pipeline_log_path(run.pipeline_id, run.pipeline_version, run.id))

            return {
                "id": run.id,
                "pipeline_name": run.pipeline_name,
                "pipeline_file": run.pipeline_file,
                "pipeline_id": run.pipeline_id,
                "pipeline_version": run.pipeline_version,
                "project_id": getattr(run, "project_id", None),
                "status": run.status,
                "error": getattr(run, "error", None),
                "params": params,
                "console_log_path": console_log_path,
                "started_at": _ensure_utc(run.started_at),
                "finished_at": _ensure_utc(run.finished_at),
                "created_at": _ensure_utc(run.created_at),
                "tasks": [
                    {
                        "id": t.id,
                        "run_id": t.run_id,
                        "task_name": t.task_name,
                        "subpipeline_name": t.subpipeline_name,
                        "task_type": t.task_type,
                        "status": t.status,
                        "exit_code": t.exit_code,
                        "error": getattr(t, "error", None),
                        "log_path": t.log_path,
                        "started_at": _ensure_utc(t.started_at),
                        "finished_at": _ensure_utc(t.finished_at),
                        "created_at": _ensure_utc(t.created_at),
                    }
                    for t in tasks
                ],
            }

    async def list_runs(
        self, pipeline: str | None = None, status: str | None = None, project_id: str | None = None, limit: int = 50
    ) -> dict:
        async with get_session_factory()() as session:
            run_repo = RunRepository(session)
            runs = await run_repo.list_runs(pipeline=pipeline, status=status, project_id=project_id, limit=limit)
            items = []
            for run in runs:
                params = {}
                if isinstance(run.params, str):
                    with contextlib.suppress(json.JSONDecodeError, TypeError):
                        params = json.loads(run.params)
                elif isinstance(run.params, dict):
                    params = run.params

                console_log_path = ""
                if run.pipeline_id and run.pipeline_version:
                    console_log_path = str(build_pipeline_log_path(run.pipeline_id, run.pipeline_version, run.id))

                items.append(
                    {
                        "id": run.id,
                        "pipeline_name": run.pipeline_name,
                        "pipeline_file": run.pipeline_file,
                        "pipeline_id": run.pipeline_id,
                        "pipeline_version": run.pipeline_version,
                        "project_id": getattr(run, "project_id", None),
                        "status": run.status,
                        "error": getattr(run, "error", None),
                        "params": params,
                        "console_log_path": console_log_path,
                        "started_at": _ensure_utc(run.started_at),
                        "finished_at": _ensure_utc(run.finished_at),
                        "created_at": _ensure_utc(run.created_at),
                        "tasks": [],
                    }
                )
            total = await run_repo.count_runs(pipeline=pipeline, status=status, project_id=project_id)
            return {"items": items, "total": total}

    async def cancel_run(self, run_id: str) -> bool:
        from taskpps.engine.runner import get_active_runner

        runner = get_active_runner(run_id)
        if runner:
            await runner.cancel()
            return True

        async with get_session_factory()() as session:
            run_repo = RunRepository(session)
            task_repo = TaskRunRepository(session)

            run = await run_repo.get_run(run_id)
            if run is None:
                return False

            if run.status in ("pending", "running"):
                await run_repo.update_run_status(run_id, "cancelled", finished_at=datetime.now(timezone.utc))
                await task_repo.cancel_pending_tasks(run_id)
                return True

            return False

    async def clean_runs(self, older_than: int | None = None, keep: int | None = None, force: bool = False) -> dict:
        async with get_session_factory()() as session:
            run_repo = RunRepository(session)
            task_repo = TaskRunRepository(session)

            deleted_logs = 0

            if force:
                runs = await run_repo.list_runs(limit=10000)
                for run in runs:
                    deleted_logs += self._delete_run_logs(run)
                    await task_repo.delete_tasks_for_run(run.id)
                deleted_runs = await run_repo.delete_all_runs()
            elif older_than:
                cutoff = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=older_than)
                runs = await run_repo.list_runs(limit=10000)
                for run in runs:
                    if run.created_at and run.created_at < cutoff:
                        deleted_logs += self._delete_run_logs(run)
                        await task_repo.delete_tasks_for_run(run.id)
                deleted_runs = await run_repo.delete_runs_older_than(older_than)
            elif keep:
                runs = await run_repo.list_runs(limit=10000)
                for run in runs[keep:]:
                    deleted_logs += self._delete_run_logs(run)
                    await task_repo.delete_tasks_for_run(run.id)
                deleted_runs = await run_repo.delete_runs_keep(keep)
            else:
                return {"deleted_runs": 0, "deleted_logs": 0}

            return {"deleted_runs": deleted_runs, "deleted_logs": deleted_logs}

    def _delete_run_logs(self, run) -> int:
        logs_dir = get_logs_dir()
        count = 0

        if run.pipeline_version:
            run_dir = logs_dir / run.pipeline_id / f"v_{run.pipeline_version}" / "builds" / run.id
        else:
            log_rel_dir = Path(run.pipeline_file).with_suffix("") if run.pipeline_file else Path("unknown")
            run_dir = logs_dir / log_rel_dir / run.id

        if run_dir.exists():
            for item in run_dir.iterdir():
                if item.is_dir():
                    log_file = item / "task.log"
                    if log_file.exists():
                        count += 1
            shutil.rmtree(run_dir, ignore_errors=True)
        return count

    async def retry_run(
        self,
        run_id: str,
        tasks: list[str] | None = None,
        subpipeline: str | None = None,
        include_upstream: bool = False,
        command_overrides: dict[str, str] | None = None,
    ) -> dict:
        async with get_session_factory()() as session:
            run_repo = RunRepository(session)
            task_repo = TaskRunRepository(session)
            retry_repo = RetryRecordRepository(session)

            run = await run_repo.get_run(run_id)
            if run is None:
                raise ValueError("Run not found")
            if run.status == RunStatus.RUNNING:
                raise ValueError(t("Run is still running, cannot retry"))
            if run.status == RunStatus.CANCELLED:
                raise ValueError(t("Run is cancelled, cannot retry"))

            if tasks and subpipeline:
                raise ValueError("Cannot specify both tasks and subpipeline")

            resolved = self._load_resolved_pipeline(run)
            if resolved is None:
                raise ValueError("Cannot load pipeline definition for retry")

            task_targets: list[str] = []
            if tasks:
                task_targets = tasks
            elif subpipeline:
                sub_obj = resolved.get_subpipeline_by_name(subpipeline)
                if sub_obj is None:
                    raise ValueError(f"SubPipeline '{subpipeline}' not found")
                task_targets = [f"{subpipeline}.{t.name}" for t in sub_obj.tasks]
            else:
                raise ValueError("Must specify either tasks or subpipeline")

            if include_upstream:
                qualified_tasks = self._build_qualified_tasks_with_subpipeline_deps(resolved)
                dag = DAG(qualified_tasks, implicit_sequential=False)
                upstream_set: set[str] = set()
                for t_name in task_targets:
                    upstream_set |= dag.get_dependencies(t_name)
                for t_name in task_targets:
                    upstream_set.discard(t_name)
                task_targets = list(upstream_set) + task_targets
                task_levels = dag.get_execution_levels()
                task_targets.sort(key=lambda n: next((i for i, lev in enumerate(task_levels) if n in lev), 999))

            all_task_runs = await task_repo.list_task_runs(run_id)
            task_run_map = {tr.task_name: tr for tr in all_task_runs}

            for t_name in task_targets:
                if t_name not in task_run_map:
                    raise ValueError(f"Task '{t_name}' not found in run")
                tr = task_run_map[t_name]
                if tr.status == TaskStatus.SKIPPED:
                    raise ValueError(t("Task was skipped, cannot retry"))

                existing = await retry_repo.list_retries_by_task(run_id, t_name)
                pending = [r for r in existing if r.status == TaskStatus.PENDING or r.status == TaskStatus.RUNNING]
                if pending:
                    raise ValueError(t("Task has a retry already in progress"))

            context = ExecutionContext(
                pipeline=resolved,
                run_id=run_id,
                env=json.loads(run.params) if isinstance(run.params, str) else (run.params or {}),
                project_workdir=getattr(run, "project_workdir", None),
            )

            retry_records = []
            for t_name in task_targets:
                tr = task_run_map[t_name]
                task_obj = resolved.get_task_by_name(t_name.split(".", 1)[1])

                original_raw = getattr(task_obj, "command", "") or ""
                env_dict = context.get_task_env(task_obj) if task_obj else {}
                resolved_cmd = self._resolve_template(original_raw, env_dict)
                if command_overrides and t_name in command_overrides:
                    resolved_cmd = command_overrides[t_name]

                retry_version = await retry_repo.get_next_retry_version(run_id, t_name)
                log_path = build_retry_log_path(
                    run.pipeline_id, run.pipeline_version, run_id, t_name, retry_version,
                )

                record = await retry_repo.create_retry_record(
                    run_id=run_id,
                    task_run_id=tr.id,
                    task_name=t_name,
                    subpipeline_name=tr.subpipeline_name,
                    retry_version=retry_version,
                    command=resolved_cmd,
                    original_command=resolved_cmd,
                    log_path=str(log_path),
                )
                retry_records.append(record)

        max_parallel = resolved.top_config.max_parallel
        runner = RetryRunner(run_id=run_id, pipeline=resolved, context=context, max_parallel=max_parallel)

        task_plan = [
            {
                "name": r.task_name,
                "command": r.command,
                "retry_record_id": r.id,
                "log_path": r.log_path,
            }
            for r in retry_records
        ]

        await runner.retry_tasks(task_plan)

        refreshed: dict[str, Any] = {}
        async with get_session_factory()() as session:
            retry_repo = RetryRecordRepository(session)
            for r in retry_records:
                record = await retry_repo.get_retry_record(r.id)
                if record:
                    refreshed[r.id] = record
                    if record.status == TaskStatus.SUCCESS:
                        await self._auto_select_latest_retry(session, run_id, r.task_name)

        return {
            "run_id": run_id,
            "retry_records": [
                {
                    "id": r.id,
                    "task_name": r.task_name,
                    "retry_version": r.retry_version,
                    "status": (refreshed[r.id].status.value
                               if r.id in refreshed
                               else r.status.value if hasattr(r.status, "value") else r.status),
                    "command": r.command,
                    "log_path": r.log_path,
                }
                for r in retry_records
            ],
        }

    async def _auto_select_latest_retry(self, session, run_id: str, task_name: str) -> None:
        from taskpps.db.repository import RetryRecordRepository, TaskRunRepository

        retry_repo = RetryRecordRepository(session)
        task_repo = TaskRunRepository(session)

        records = await retry_repo.list_retries_by_task(run_id, task_name)
        if not records:
            return

        latest = max(records, key=lambda r: r.retry_version)
        if latest.status != TaskStatus.SUCCESS:
            return
        await self._select_retry_report_internal(session, run_id, task_name, latest.id)

    async def _select_retry_report_internal(
        self, session, run_id: str, task_name: str, selected_retry_id: str,
    ) -> dict:
        from taskpps.db.repository import RetryRecordRepository, RunRepository, TaskRunRepository

        retry_repo = RetryRecordRepository(session)
        run_repo = RunRepository(session)
        task_repo = TaskRunRepository(session)

        selected = await retry_repo.get_retry_record(selected_retry_id)
        if selected is None:
            raise ValueError(t("Retry record not found"))
        if selected.task_name != task_name or selected.run_id != run_id:
            raise ValueError("Retry record does not match task/run")

        task_runs = await task_repo.list_task_runs(run_id)
        tr = next((t for t in task_runs if t.task_name == task_name), None)
        if tr is None:
            raise ValueError(f"Task run '{task_name}' not found")

        tr.selected_retry_id = selected_retry_id
        if selected.status == TaskStatus.SUCCESS and tr.status != TaskStatus.SUCCESS:
            tr.status = TaskStatus.SUCCESS
        session.add(tr)
        await session.commit()

        all_tr = await task_repo.list_task_runs(run_id)
        all_failed_or_cancelled = all(
            t.status in (TaskStatus.SUCCESS, TaskStatus.SKIPPED) for t in all_tr
        )
        if all_failed_or_cancelled:
            run = await run_repo.get_run(run_id)
            if run:
                await run_repo.update_run_status(run_id, RunStatus.SUCCESS)

        logger.info(t("Selected retry report for '{task}': version {ver}",
                       task=task_name, ver=selected.retry_version))
        return {"task_name": task_name, "selected_retry_id": selected_retry_id}

    async def select_retry_report(self, run_id: str, task_name: str, selected_retry_id: str) -> dict:
        async with get_session_factory()() as session:
            return await self._select_retry_report_internal(session, run_id, task_name, selected_retry_id)

    async def batch_select_retry_report(self, run_id: str, selections: dict[str, str]) -> dict:
        async with get_session_factory()() as session:
            for task_name, retry_id in selections.items():
                await self._select_retry_report_internal(session, run_id, task_name, retry_id)
            return {"selected": selections}

    async def get_retry_versions(self, run_id: str) -> dict:
        async with get_session_factory()() as session:
            retry_repo = RetryRecordRepository(session)
            task_repo = TaskRunRepository(session)

            records = await retry_repo.list_retries_by_run(run_id)
            task_runs = await task_repo.list_task_runs(run_id)

            grouped: dict[str, list[dict]] = {}
            for r in records:
                task_name = r.task_name
                if task_name not in grouped:
                    grouped[task_name] = []
                grouped[task_name].append({
                    "id": r.id,
                    "run_id": r.run_id,
                    "task_run_id": r.task_run_id,
                    "task_name": r.task_name,
                    "subpipeline_name": r.subpipeline_name,
                    "retry_version": r.retry_version,
                    "status": r.status.value if hasattr(r.status, "value") else r.status,
                    "command": r.command,
                    "original_command": r.original_command,
                    "log_path": r.log_path,
                    "exit_code": r.exit_code,
                    "error": r.error,
                    "started_at": _ensure_utc(r.started_at),
                    "finished_at": _ensure_utc(r.finished_at),
                    "created_at": _ensure_utc(r.created_at),
                })

            selected: dict[str, str | None] = {}
            for tr in task_runs:
                selected[tr.task_name] = tr.selected_retry_id

            return {"task_retries": grouped, "selected": selected}

    async def get_retry_record(self, retry_id: str) -> dict | None:
        async with get_session_factory()() as session:
            retry_repo = RetryRecordRepository(session)
            r = await retry_repo.get_retry_record(retry_id)
            if r is None:
                return None
            return {
                "id": r.id,
                "run_id": r.run_id,
                "task_run_id": r.task_run_id,
                "task_name": r.task_name,
                "subpipeline_name": r.subpipeline_name,
                "retry_version": r.retry_version,
                "status": r.status.value if hasattr(r.status, "value") else r.status,
                "command": r.command,
                "original_command": r.original_command,
                "log_path": r.log_path,
                "exit_code": r.exit_code,
                "error": r.error,
                "started_at": _ensure_utc(r.started_at),
                "finished_at": _ensure_utc(r.finished_at),
                "created_at": _ensure_utc(r.created_at),
            }

    async def get_retry_command(self, retry_id: str) -> dict | None:
        async with get_session_factory()() as session:
            retry_repo = RetryRecordRepository(session)
            r = await retry_repo.get_retry_record(retry_id)
            if r is None:
                return None

            resolved_cmd = r.command or r.original_command
            return {
                "retry_id": r.id,
                "task_name": r.task_name,
                "original_command": r.original_command,
                "resolved_command": resolved_cmd,
                "variables": {},
                "editable": r.status == TaskStatus.PENDING,
                "status": r.status.value if hasattr(r.status, "value") else r.status,
            }

    async def update_retry_command(self, retry_id: str, command: str) -> dict:
        async with get_session_factory()() as session:
            retry_repo = RetryRecordRepository(session)
            r = await retry_repo.get_retry_record(retry_id)
            if r is None:
                raise ValueError(t("Retry record not found"))
            if r.status != TaskStatus.PENDING:
                raise ValueError(t("Retry command can only be edited when pending"))
            await retry_repo.update_retry_command(retry_id, command)
            return {"retry_id": retry_id, "command": command}

    async def get_dependency_tree(self, run_id: str, task_name: str) -> dict:
        async with get_session_factory()() as session:
            run_repo = RunRepository(session)
            run = await run_repo.get_run(run_id)
            if run is None:
                raise ValueError("Run not found")

        resolved = self._load_resolved_pipeline(run)
        if resolved is None:
            raise ValueError("Cannot load pipeline definition")

        parts = task_name.split(".", 1)
        sub_name = parts[0] if len(parts) > 1 else ""
        task_short = parts[1] if len(parts) > 1 else parts[0]

        qualified_tasks = self._build_qualified_tasks_with_subpipeline_deps(resolved)
        dag = DAG(qualified_tasks, implicit_sequential=False)
        deps = dag.get_dependencies(task_name)
        levels = dag.get_execution_levels()

        tree = []
        for level_idx, level in enumerate(levels):
            for t_name in level:
                if t_name == task_name or t_name in deps:
                    task_obj = resolved.get_task_by_name(t_name.split(".", 1)[1])
                    is_upstream = t_name in deps
                    tree.append(DependencyNode(
                        name=t_name,
                        depends_on=list(dag.reverse_adjacency.get(t_name, [])),
                        level=level_idx,
                        upstream_of_target=is_upstream,
                        mandatory_if_upstream=is_upstream,
                    ))

        return {
            "target": task_name,
            "subpipeline": sub_name,
            "tree": [n.model_dump() for n in tree],
        }

    def _load_resolved_pipeline(self, run) -> ResolvedPipeline | None:
        try:
            from taskpps.config import get_pipelines_dir
            base_dir = get_pipelines_dir()
            spec = self.loader.load(run.pipeline_file)
            return ResolvedPipeline.from_yaml(spec, pipeline_file=run.pipeline_file)
        except Exception:
            import traceback
            logger.warning("Failed to reload pipeline for retry: %s", traceback.format_exc())
            return None

    @staticmethod
    def _build_qualified_tasks_with_subpipeline_deps(resolved: ResolvedPipeline) -> list[ResolvedTask]:
        qualified_tasks: list[ResolvedTask] = []
        sub_task_map: dict[str, list[str]] = {}
        for sub in resolved.subpipelines:
            sub_task_names = []
            for _task in sub.tasks:
                qname = f"{sub.name}.{_task.name}"
                sub_task_names.append(qname)
                qt = ResolvedTask(
                    name=qname,
                    task_type=_task.task_type,
                    command=_task.command,
                    commands=_task.commands,
                    depends_on=[f"{sub.name}.{d}" for d in (_task.depends_on or [])],
                )
                qualified_tasks.append(qt)
            sub_task_map[sub.name] = sub_task_names

        for sub in resolved.subpipelines:
            if sub.depends_on:
                for dep_sub_name in sub.depends_on:
                    dep_tasks = sub_task_map.get(dep_sub_name, [])
                    for qt in qualified_tasks:
                        if qt.name.startswith(f"{sub.name}."):
                            qt.depends_on = list(qt.depends_on) + dep_tasks

        return qualified_tasks

    @staticmethod
    def _resolve_template(command: str, env: dict[str, str]) -> str:
        import re
        def _replace(match):
            var_name = match.group(1)
            return env.get(var_name, match.group(0))
        return re.sub(r'\$\{env\.([^}]+)\}', _replace, command)

    def list_pipelines(self) -> list[str]:
        all_pipelines = self.loader.load_all()
        return list(all_pipelines.keys())

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
from taskpps.db.repository import ProjectRepository, RetryRecordRepository, RunRepository, TaskRunRepository
from taskpps.domain.context import ExecutionContext, apply_overrides
from taskpps.domain.dag import DAG, DAGCycleError
from taskpps.domain.pipeline import ResolvedPipeline, ResolvedTask
from taskpps.engine.retry_runner import RetryRunner
from taskpps.engine.runner import PipelineRunner
from taskpps.i18n import t
from taskpps.loaders.pipeline_loader import PipelineLoader
from taskpps.naming import generate_display_name

logger = logging.getLogger("taskpps.services.pipeline_service")
from taskpps.models.run import RunStatus, TaskStatus
from taskpps.schemas.pipeline import PipelineYAML
from taskpps.schemas.run import DependencyNode


def _ensure_utc(dt: datetime | None) -> datetime | None:
    if dt is not None and dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


async def _resolve_project_name(project_id: str | None) -> str | None:
    """根据 project_id 查找项目名称，名称为空时用 workdir 最后一段路径作为回退。"""
    if project_id is None:
        return None
    async with get_session_factory()() as session:
        project = await ProjectRepository(session).get_project(project_id)
    if project is None:
        return None
    if project.name:
        return project.name
    # 名称为空时用 workdir 最后一段路径
    return Path(project.workdir).name or None


def _extract_env_overrides(params: dict[str, Any]) -> dict[str, str]:
    """从 override params 中提取所有环境变量（支持 nested 和 dot-path 两种格式）"""
    result: dict[str, str] = {}
    # 1) nested: params["config"]["env"]
    nested_config = params.get("config")
    if isinstance(nested_config, dict):
        env = nested_config.get("env")
        if isinstance(env, dict):
            result.update(env)
    # 2) dot-path: params["config.env"]
    dotpath_env = params.get("config.env")
    if isinstance(dotpath_env, dict):
        result.update(dotpath_env)
    # 3) task-level env: params['tasks["name"].env']
    for key, val in params.items():
        if isinstance(val, dict) and key.startswith('tasks["') and key.endswith('"].env'):
            result.update(val)
    return result


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
                config_env = _extract_env_overrides(params)
                if config_env:
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

            display_name = generate_display_name()

            run = await run_repo.create_run(
                pipeline_name=resolved.name,
                pipeline_file=pipeline_file,
                pipeline_id=pipeline_id,
                pipeline_version=pipeline_version,
                params=params,
                project_id=project_id,
                display_name=display_name,
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

        self._save_pipeline_snapshot(pipeline_file, pipeline_id, pipeline_version, run.id, project_workdir)

        context = ExecutionContext(pipeline=resolved, run_id=run.id, env=_extract_env_overrides(params) if params else {}, project_workdir=project_workdir)

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
            "display_name": display_name,
        }

    @staticmethod
    def _save_pipeline_snapshot(pipeline_file: str, pipeline_id: str, pipeline_version: str, run_id: str, project_workdir: str | None = None) -> None:
        pipelines_dir = get_pipelines_dir(Path(project_workdir) if project_workdir else None)
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
    def _write_cancel_signal(pipeline_id: str, pipeline_version: str, run_id: str) -> None:
        logs_dir = get_logs_dir()
        v = pipeline_version or "unknown"
        signal_dir = logs_dir / pipeline_id / f"v_{v}" / "builds" / run_id
        signal_dir.mkdir(parents=True, exist_ok=True)
        (signal_dir / ".cancel-requested").touch()

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

            project_name = await _resolve_project_name(getattr(run, "project_id", None))

            return {
                "id": run.id,
                "pipeline_name": run.pipeline_name,
                "pipeline_file": run.pipeline_file,
                "pipeline_id": run.pipeline_id,
                "pipeline_version": run.pipeline_version,
                "project_id": getattr(run, "project_id", None),
                "project_name": project_name,
                "display_name": getattr(run, "display_name", ""),
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

                project_name = await _resolve_project_name(getattr(run, "project_id", None))

                items.append(
                    {
                        "id": run.id,
                        "pipeline_name": run.pipeline_name,
                        "pipeline_file": run.pipeline_file,
                        "pipeline_id": run.pipeline_id,
                        "pipeline_version": run.pipeline_version,
                        "project_id": getattr(run, "project_id", None),
                        "project_name": project_name,
                        "display_name": getattr(run, "display_name", ""),
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
                # 写入跨 Worker 取消信号文件，让其他 Worker 上的 runner 能检测到
                self._write_cancel_signal(run.pipeline_id, run.pipeline_version, run_id)

                # 不设置 finished_at — 让 runner 在实际终止时设置真实结束时间
                await run_repo.update_run_status(run_id, "cancelled")
                await task_repo.cancel_pending_tasks(run_id)
                return True

            return False

    async def delete_run(self, run_id: str) -> bool:
        async with get_session_factory()() as session:
            run_repo = RunRepository(session)
            task_repo = TaskRunRepository(session)

            runs = await run_repo.list_runs(limit=10000)
            target = None
            for run in runs:
                if run.id == run_id:
                    target = run
                    break

            if not target:
                return False

            self._delete_run_logs(target)
            await task_repo.delete_tasks_for_run(run_id)
            deleted = await run_repo.delete_run_by_id(run_id)
            return deleted > 0

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
                if not run.pipeline_id:
                    raise ValueError(t("Run has no pipeline snapshot, retry is not available"))
                raise ValueError(t("Pipeline snapshot not found, retry is not available. The snapshot may have been cleaned up."))

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

                existing = await retry_repo.list_retries_by_task(run_id, t_name)
                pending = [r for r in existing if r.status == TaskStatus.PENDING or r.status == TaskStatus.RUNNING]
                if pending:
                    raise ValueError(t("Task has a retry already in progress"))

            run_params = json.loads(run.params) if isinstance(run.params, str) else (run.params or {})
            context = ExecutionContext(
                pipeline=resolved,
                run_id=run_id,
                env=_extract_env_overrides(run_params),
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

            # 构建原始 TaskRun 的 v0 条目
            task_run_map: dict[str, TaskRun] = {tr.task_name: tr for tr in task_runs}

            grouped: dict[str, list[dict]] = {}
            for task_name, tr in task_run_map.items():
                if task_name not in grouped:
                    grouped[task_name] = []
                # 原始执行作为 v0
                grouped[task_name].append({
                    "id": tr.id,
                    "run_id": tr.run_id,
                    "task_run_id": tr.id,
                    "task_name": tr.task_name,
                    "subpipeline_name": tr.subpipeline_name,
                    "retry_version": 0,
                    "status": tr.status.value if hasattr(tr.status, "value") else tr.status,
                    "command": "",
                    "original_command": "",
                    "log_path": tr.log_path,
                    "exit_code": tr.exit_code,
                    "error": tr.error,
                    "started_at": _ensure_utc(tr.started_at),
                    "finished_at": _ensure_utc(tr.finished_at),
                    "created_at": _ensure_utc(tr.created_at),
                })

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
            if not run.pipeline_id:
                raise ValueError(t("Run has no pipeline snapshot, retry is not available"))
            raise ValueError(t("Pipeline snapshot not found, retry is not available. The snapshot may have been cleaned up."))

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
        """加载 pipeline 定义用于重试。仅使用执行时保存的快照，禁止回退到当前磁盘文件。"""
        import yaml

        if not run.pipeline_id:
            logger.error("Run %s has no pipeline_id, cannot locate snapshot", run.id)
            return None

        v = run.pipeline_version or ""
        snapshot_path = get_logs_dir() / run.pipeline_id / f"v_{v}" / "builds" / run.id / "pipeline-snapshot.yaml"

        if not snapshot_path.exists():
            logger.error("Pipeline snapshot not found for run %s: %s", run.id, snapshot_path)
            return None

        try:
            with open(snapshot_path) as f:
                data = yaml.safe_load(f)
            if data is None:
                logger.error("Pipeline snapshot is empty for run %s", run.id)
                return None
            spec = PipelineYAML(**data)
            return ResolvedPipeline.from_yaml(spec, pipeline_file=run.pipeline_file)
        except Exception:
            import traceback
            logger.error("Failed to parse pipeline snapshot for run %s: %s", run.id, traceback.format_exc())
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

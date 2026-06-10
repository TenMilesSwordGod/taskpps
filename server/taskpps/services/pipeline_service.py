from __future__ import annotations

import asyncio
import contextlib
import json
import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from taskpps.config import (
    build_log_path,
    compute_pipeline_id,
    compute_pipeline_version,
    get_logs_dir,
    get_pipelines_dir,
)
from taskpps.db.engine import get_session_factory
from taskpps.db.repository import RunRepository, TaskRunRepository
from taskpps.domain.context import ExecutionContext, apply_overrides
from taskpps.domain.dag import DAG, DAGCycleError
from taskpps.domain.pipeline import ResolvedPipeline
from taskpps.engine.runner import PipelineRunner
from taskpps.i18n import t
from taskpps.loaders.pipeline_loader import PipelineLoader
from taskpps.schemas.pipeline import PipelineYAML


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
        pipeline_version = compute_pipeline_version(pipeline_file)

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

            return {
                "id": run.id,
                "pipeline_name": run.pipeline_name,
                "pipeline_file": run.pipeline_file,
                "pipeline_id": run.pipeline_id,
                "pipeline_version": run.pipeline_version,
                "project_id": getattr(run, "project_id", None),
                "status": run.status,
                "params": params,
                "started_at": run.started_at,
                "finished_at": run.finished_at,
                "created_at": run.created_at,
                "tasks": [
                    {
                        "id": t.id,
                        "run_id": t.run_id,
                        "task_name": t.task_name,
                        "subpipeline_name": t.subpipeline_name,
                        "task_type": t.task_type,
                        "status": t.status,
                        "exit_code": t.exit_code,
                        "log_path": t.log_path,
                        "started_at": t.started_at,
                        "finished_at": t.finished_at,
                        "created_at": t.created_at,
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

                items.append(
                    {
                        "id": run.id,
                        "pipeline_name": run.pipeline_name,
                        "pipeline_file": run.pipeline_file,
                        "pipeline_id": run.pipeline_id,
                        "pipeline_version": run.pipeline_version,
                        "project_id": getattr(run, "project_id", None),
                        "status": run.status,
                        "params": params,
                        "started_at": run.started_at,
                        "finished_at": run.finished_at,
                        "created_at": run.created_at,
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

    def list_pipelines(self) -> list[str]:
        all_pipelines = self.loader.load_all()
        return list(all_pipelines.keys())

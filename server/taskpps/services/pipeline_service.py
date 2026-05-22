from __future__ import annotations

import asyncio
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from taskpps.config import get_logs_dir, get_settings
from taskpps.db.engine import get_session_factory
from taskpps.db.repository import RunRepository, TaskRunRepository
from taskpps.domain.context import ExecutionContext, apply_overrides
from taskpps.domain.dag import DAG, DAGCycleError
from taskpps.domain.pipeline import ResolvedPipeline, ResolvedTask
from taskpps.engine.runner import PipelineRunner
from taskpps.loaders.pipeline_loader import PipelineLoader
from taskpps.schemas.pipeline import PipelineYAML


class PipelineService:
    def __init__(self):
        self.loader = PipelineLoader()

    async def create_run(self, pipeline_file: str, params: Optional[Dict[str, Any]] = None) -> dict:
        try:
            spec = self.loader.load(pipeline_file)
        except FileNotFoundError as e:
            raise ValueError(str(e))
        except Exception as e:
            raise ValueError(f"Failed to load pipeline: {e}")

        if params:
            pipeline_data = spec.model_dump()
            try:
                overridden = apply_overrides(pipeline_data, params)
                spec = PipelineYAML(**overridden)
            except Exception as e:
                raise ValueError(f"Failed to apply overrides: {e}")

        resolved = ResolvedPipeline.from_yaml(spec, pipeline_file=pipeline_file)

        try:
            dag = DAG(resolved.tasks)
            dag.topological_sort()
        except (DAGCycleError, ValueError) as e:
            raise ValueError(str(e))

        async with get_session_factory()() as session:
            run_repo = RunRepository(session)
            task_repo = TaskRunRepository(session)

            run = await run_repo.create_run(
                pipeline_name=resolved.name,
                pipeline_file=pipeline_file,
                params=params,
            )

            logs_dir = get_logs_dir()
            task_run_ids = {}
            for task in resolved.tasks:
                log_path = str(logs_dir / resolved.name / task.name / f"{run.id}.log")
                task_run = await task_repo.create_task_run(
                    run_id=run.id,
                    task_name=task.name,
                    task_type=task.task_type,
                    log_path=log_path,
                )
                task_run_ids[task.name] = task_run.id

        context = ExecutionContext(pipeline=resolved, run_id=run.id, env=params)

        runner = PipelineRunner(run_id=run.id, pipeline=resolved, context=context)
        runner._task_run_ids = task_run_ids

        asyncio.create_task(runner.run())

        return {"id": run.id, "pipeline_name": run.pipeline_name, "status": run.status}

    async def get_run(self, run_id: str) -> Optional[dict]:
        async with get_session_factory()() as session:
            run_repo = RunRepository(session)
            task_repo = TaskRunRepository(session)

            run = await run_repo.get_run(run_id)
            if run is None:
                return None

            tasks = await task_repo.list_task_runs(run_id)

            return {
                "id": run.id,
                "pipeline_name": run.pipeline_name,
                "pipeline_file": run.pipeline_file,
                "status": run.status,
                "params": run.params,
                "started_at": run.started_at,
                "finished_at": run.finished_at,
                "created_at": run.created_at,
                "tasks": [
                    {
                        "id": t.id,
                        "run_id": t.run_id,
                        "task_name": t.task_name,
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

    async def list_runs(self, pipeline: Optional[str] = None, status: Optional[str] = None, limit: int = 50) -> dict:
        async with get_session_factory()() as session:
            run_repo = RunRepository(session)
            runs = await run_repo.list_runs(pipeline=pipeline, status=status, limit=limit)
            items = []
            for run in runs:
                items.append({
                    "id": run.id,
                    "pipeline_name": run.pipeline_name,
                    "pipeline_file": run.pipeline_file,
                    "status": run.status,
                    "params": run.params,
                    "started_at": run.started_at,
                    "finished_at": run.finished_at,
                    "created_at": run.created_at,
                })
            # Also get total count (without limit)
            total = len(await run_repo.list_runs(pipeline=pipeline, status=status, limit=10000))
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
                await run_repo.update_run_status(run_id, "cancelled", finished_at=datetime.utcnow())
                await task_repo.cancel_pending_tasks(run_id)
                return True

            return False

    async def clean_runs(self, older_than: Optional[int] = None, keep: Optional[int] = None, force: bool = False) -> dict:
        async with get_session_factory()() as session:
            run_repo = RunRepository(session)
            task_repo = TaskRunRepository(session)

            deleted_logs = 0

            if force:
                runs = await run_repo.list_runs(limit=10000)
                for run in runs:
                    deleted_logs += self._delete_run_logs(run.pipeline_name, run.id)
                deleted_runs = await run_repo.delete_all_runs()
            elif older_than:
                runs = await run_repo.list_runs(limit=10000)
                from datetime import datetime, timedelta
                cutoff = datetime.utcnow() - timedelta(days=older_than)
                for run in runs:
                    if run.created_at and run.created_at < cutoff:
                        deleted_logs += self._delete_run_logs(run.pipeline_name, run.id)
                deleted_runs = await run_repo.delete_runs_older_than(older_than)
            elif keep:
                runs = await run_repo.list_runs(limit=10000)
                runs_to_keep = set()
                for run in runs[:keep]:
                    runs_to_keep.add(run.id)
                for run in runs[keep:]:
                    deleted_logs += self._delete_run_logs(run.pipeline_name, run.id)
                deleted_runs = await run_repo.delete_runs_keep(keep)
            else:
                return {"deleted_runs": 0, "deleted_logs": 0}

            return {"deleted_runs": deleted_runs, "deleted_logs": deleted_logs}

    def _delete_run_logs(self, pipeline_name: str, run_id: str) -> int:
        logs_dir = get_logs_dir()
        pipeline_logs = logs_dir / pipeline_name
        count = 0
        if pipeline_logs.exists():
            for task_dir in pipeline_logs.iterdir():
                if task_dir.is_dir():
                    log_file = task_dir / f"{run_id}.log"
                    if log_file.exists():
                        log_file.unlink()
                        count += 1
        return count

    def list_pipelines(self) -> List[str]:
        all_pipelines = self.loader.load_all()
        return list(all_pipelines.keys())

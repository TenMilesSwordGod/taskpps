from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from taskpps.config import get_logs_dir, get_settings
from taskpps.db.engine import get_session_factory
from taskpps.db.repository import RunRepository, TaskRunRepository
from taskpps.i18n import t
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
            raise ValueError(t("Failed to load pipeline: {error}", error=str(e)))

        if params:
            pipeline_data = spec.model_dump()
            try:
                overridden = apply_overrides(pipeline_data, params)
                spec = PipelineYAML(**overridden)
            except Exception as e:
                raise ValueError(t("Failed to apply overrides: {error}", error=str(e)))

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
                log_rel_dir = Path(pipeline_file).with_suffix('') if pipeline_file else Path(resolved.name)
                # Create task_run first without log_path (we'll update it after getting the id)
                task_run = await task_repo.create_task_run(
                    run_id=run.id,
                    task_name=task.name,
                    task_type=task.task_type,
                )
                # Now update log_path with the task_run.id
                log_path = str(logs_dir / log_rel_dir / run.id / task_run.id / "output.log")
                task_run.log_path = log_path
                await self.session.commit()
                await self.session.refresh(task_run)
                task_run_ids[task.name] = task_run.id

        context = ExecutionContext(pipeline=resolved, run_id=run.id, env=params)

        runner = PipelineRunner(run_id=run.id, pipeline=resolved, context=context)
        runner._task_run_ids = task_run_ids

        task = asyncio.create_task(runner.run())
        task.add_done_callback(self._handle_run_error)

        return {"id": run.id, "pipeline_name": run.pipeline_name, "status": run.status}

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

    async def get_run(self, run_id: str) -> Optional[dict]:
        async with get_session_factory()() as session:
            run_repo = RunRepository(session)
            task_repo = TaskRunRepository(session)

            run = await run_repo.get_run(run_id)
            if run is None:
                return None

            tasks = await task_repo.list_task_runs(run_id)
            
            # Parse params from JSON string
            params = {}
            if isinstance(run.params, str):
                try:
                    params = json.loads(run.params)
                except (json.JSONDecodeError, TypeError):
                    pass
            elif isinstance(run.params, dict):
                params = run.params

            return {
                "id": run.id,
                "pipeline_name": run.pipeline_name,
                "pipeline_file": run.pipeline_file,
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
                # Parse params from JSON string
                params = {}
                if isinstance(run.params, str):
                    try:
                        params = json.loads(run.params)
                    except (json.JSONDecodeError, TypeError):
                        pass
                elif isinstance(run.params, dict):
                    params = run.params
                
                items.append({
                    "id": run.id,
                    "pipeline_name": run.pipeline_name,
                    "pipeline_file": run.pipeline_file,
                    "status": run.status,
                    "params": params,
                    "started_at": run.started_at,
                    "finished_at": run.finished_at,
                    "created_at": run.created_at,
                    "tasks": []  # Empty tasks for list view
                })
            # Also get total count (without limit)
            total = await run_repo.count_runs(pipeline=pipeline, status=status)
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

    async def clean_runs(self, older_than: Optional[int] = None, keep: Optional[int] = None, force: bool = False) -> dict:
        async with get_session_factory()() as session:
            run_repo = RunRepository(session)

            deleted_logs = 0

            if force:
                runs = await run_repo.list_runs(limit=10000)
                for run in runs:
                    deleted_logs += self._delete_run_logs(run.pipeline_file, run.id)
                deleted_runs = await run_repo.delete_all_runs()
            elif older_than:
                cutoff = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=older_than)
                runs = await run_repo.list_runs(limit=10000)
                for run in runs:
                    if run.created_at and run.created_at < cutoff:
                        deleted_logs += self._delete_run_logs(run.pipeline_file, run.id)
                deleted_runs = await run_repo.delete_runs_older_than(older_than)
            elif keep:
                runs = await run_repo.list_runs(limit=10000)
                for run in runs[keep:]:
                    deleted_logs += self._delete_run_logs(run.pipeline_file, run.id)
                deleted_runs = await run_repo.delete_runs_keep(keep)
            else:
                return {"deleted_runs": 0, "deleted_logs": 0}

            return {"deleted_runs": deleted_runs, "deleted_logs": deleted_logs}

    def _delete_run_logs(self, pipeline_file: str, run_id: str) -> int:
        import shutil
        logs_dir = get_logs_dir()
        log_rel_dir = Path(pipeline_file).with_suffix('') if pipeline_file else Path('unknown')
        run_dir = logs_dir / log_rel_dir / run_id
        count = 0
        if run_dir.exists():
            for task_dir in run_dir.iterdir():
                if task_dir.is_dir():
                    log_file = task_dir / "output.log"
                    if log_file.exists():
                        count += 1
            shutil.rmtree(run_dir)
        return count

    def list_pipelines(self) -> List[str]:
        all_pipelines = self.loader.load_all()
        return list(all_pipelines.keys())

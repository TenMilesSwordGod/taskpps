import json
import logging
from collections.abc import Sequence
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from taskpps.models.project import Project
from taskpps.models.run import PipelineRun, RunStatus, TaskRun, TaskStatus
from taskpps.models.trigger import Trigger

logger = logging.getLogger("taskpps.db.repository")


class RunRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_run(
        self,
        pipeline_name: str,
        pipeline_file: str = "",
        pipeline_id: str = "",
        pipeline_version: str = "",
        *,
        params: dict | None = None,
        project_id: str | None = None,
    ) -> PipelineRun:
        logger.debug("Creating run: pipeline=%s project=%s", pipeline_name, project_id)
        run = PipelineRun(
            pipeline_name=pipeline_name,
            pipeline_file=pipeline_file,
            pipeline_id=pipeline_id,
            pipeline_version=pipeline_version,
            project_id=project_id,
            params=json.dumps(params or {}),
            status=RunStatus.PENDING,
        )
        self.session.add(run)
        await self.session.commit()
        await self.session.refresh(run)
        return run

    async def get_run(self, run_id: str) -> PipelineRun | None:
        result = await self.session.execute(select(PipelineRun).where(PipelineRun.id == run_id))
        return result.scalar_one_or_none()

    async def get_last_run_by_pipeline(self, pipeline_id: str) -> PipelineRun | None:
        result = await self.session.execute(
            select(PipelineRun)
            .where(PipelineRun.pipeline_id == pipeline_id, PipelineRun.pipeline_version != "")
            .order_by(PipelineRun.created_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def list_versions(self, pipeline_id: str) -> list[str]:
        result = await self.session.execute(
            select(PipelineRun.pipeline_version)
            .where(PipelineRun.pipeline_id == pipeline_id, PipelineRun.pipeline_version != "")
            .order_by(PipelineRun.created_at.desc())
        )
        return [row[0] for row in result.fetchall()]

    async def delete_runs_by_version(self, pipeline_id: str, version: str) -> int:
        stmt = delete(PipelineRun).where(
            PipelineRun.pipeline_id == pipeline_id,
            PipelineRun.pipeline_version == version,
        )
        result = await self.session.execute(stmt)
        await self.session.commit()
        return result.rowcount

    async def count_runs(
        self,
        pipeline: str | None = None,
        status: str | None = None,
        pipeline_id: str | None = None,
        project_id: str | None = None,
    ) -> int:
        stmt = select(func.count(PipelineRun.id))
        if pipeline:
            stmt = stmt.where(PipelineRun.pipeline_name == pipeline)
        if pipeline_id:
            stmt = stmt.where(PipelineRun.pipeline_id == pipeline_id)
        if status:
            stmt = stmt.where(PipelineRun.status == status)
        if project_id:
            stmt = stmt.where(PipelineRun.project_id == project_id)
        result = await self.session.execute(stmt)
        return result.scalar() or 0

    async def list_runs(
        self,
        pipeline: str | None = None,
        status: str | None = None,
        project_id: str | None = None,
        limit: int = 50,
    ) -> Sequence[PipelineRun]:
        stmt = select(PipelineRun).order_by(PipelineRun.created_at.desc())
        if pipeline:
            stmt = stmt.where(PipelineRun.pipeline_name == pipeline)
        if status:
            stmt = stmt.where(PipelineRun.status == status)
        if project_id:
            stmt = stmt.where(PipelineRun.project_id == project_id)
        stmt = stmt.limit(limit)
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def update_run_status(
        self,
        run_id: str,
        status: RunStatus,
        started_at: datetime | None = None,
        finished_at: datetime | None = None,
        error: str | None = None,
    ) -> None:
        logger.debug("Updating run status: id=%s status=%s", run_id, status)
        run = await self.get_run(run_id)
        if run is None:
            logger.debug("update_run_status: run not found id=%s", run_id)
            return
        run.status = status
        if started_at is not None:
            run.started_at = started_at
        if finished_at is not None:
            run.finished_at = finished_at
        if error is not None:
            run.error = error
        await self.session.commit()

    async def delete_runs_older_than(self, days: int) -> int:
        cutoff = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=days)
        stmt = delete(PipelineRun).where(PipelineRun.created_at < cutoff)
        result = await self.session.execute(stmt)
        await self.session.commit()
        return result.rowcount

    async def delete_runs_keep(self, keep: int) -> int:
        if keep < 0:
            raise ValueError("keep must be non-negative")
        if keep == 0:
            return await self.delete_all_runs()
        sub = select(PipelineRun.id).order_by(PipelineRun.created_at.desc()).limit(keep)
        stmt = delete(PipelineRun).where(PipelineRun.id.not_in(sub))
        result = await self.session.execute(stmt)
        await self.session.commit()
        return result.rowcount

    async def delete_all_runs(self) -> int:
        stmt = delete(PipelineRun)
        result = await self.session.execute(stmt)
        await self.session.commit()
        return result.rowcount


class TaskRunRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_task_run(
        self, run_id: str, task_name: str, task_type: str = "command", subpipeline_name: str = "", log_path: str = ""
    ) -> TaskRun:
        tr = TaskRun(
            run_id=run_id,
            task_name=task_name,
            subpipeline_name=subpipeline_name,
            task_type=task_type,
            log_path=log_path,
            status=TaskStatus.PENDING,
        )
        self.session.add(tr)
        await self.session.commit()
        await self.session.refresh(tr)
        return tr

    async def get_task_run(self, task_run_id: str) -> TaskRun | None:
        result = await self.session.execute(select(TaskRun).where(TaskRun.id == task_run_id))
        return result.scalar_one_or_none()

    async def list_task_runs(self, run_id: str) -> Sequence[TaskRun]:
        result = await self.session.execute(
            select(TaskRun).where(TaskRun.run_id == run_id).order_by(TaskRun.created_at)
        )
        return result.scalars().all()

    async def update_task_status(
        self,
        task_run_id: str,
        status: TaskStatus,
        exit_code: int | None = None,
        error: str | None = None,
        started_at: datetime | None = None,
        finished_at: datetime | None = None,
    ) -> None:
        tr = await self.get_task_run(task_run_id)
        if tr is None:
            return
        tr.status = status
        if exit_code is not None:
            tr.exit_code = exit_code
        if error is not None:
            tr.error = error
        if started_at is not None:
            tr.started_at = started_at
        if finished_at is not None:
            tr.finished_at = finished_at
        await self.session.commit()

    async def cancel_pending_tasks(self, run_id: str) -> int:
        stmt = select(TaskRun).where(TaskRun.run_id == run_id, TaskRun.status == TaskStatus.PENDING)
        result = await self.session.execute(stmt)
        tasks = result.scalars().all()
        count = 0
        for t in tasks:
            t.status = TaskStatus.CANCELLED
            count += 1
        await self.session.commit()
        return count

    async def get_running_tasks(self, run_id: str) -> Sequence[TaskRun]:
        result = await self.session.execute(
            select(TaskRun).where(TaskRun.run_id == run_id, TaskRun.status == TaskStatus.RUNNING)
        )
        return result.scalars().all()

    async def delete_tasks_for_run(self, run_id: str) -> int:
        stmt = delete(TaskRun).where(TaskRun.run_id == run_id)
        result = await self.session.execute(stmt)
        await self.session.commit()
        return result.rowcount


class TriggerRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_trigger(
        self, type: str, config: dict, pipeline_file: str, enabled: bool = True, project_id: str | None = None
    ) -> Trigger:
        trigger = Trigger(
            type=type,
            config=json.dumps(config),
            pipeline_file=pipeline_file,
            project_id=project_id,
            enabled=enabled,
        )
        self.session.add(trigger)
        await self.session.commit()
        await self.session.refresh(trigger)
        return trigger

    async def get_trigger(self, trigger_id: str) -> Trigger | None:
        result = await self.session.execute(select(Trigger).where(Trigger.id == trigger_id))
        return result.scalar_one_or_none()

    async def list_triggers(self) -> Sequence[Trigger]:
        result = await self.session.execute(select(Trigger).order_by(Trigger.created_at))
        return result.scalars().all()

    async def delete_trigger(self, trigger_id: str) -> bool:
        trigger = await self.get_trigger(trigger_id)
        if trigger is None:
            return False
        await self.session.delete(trigger)
        await self.session.commit()
        return True


class ProjectRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_project(self, workdir: str, name: str = "") -> Project:
        logger.debug("Creating project: workdir=%s name=%s", workdir, name)
        project = Project(
            name=name,
            workdir=workdir,
        )
        self.session.add(project)
        await self.session.commit()
        await self.session.refresh(project)
        logger.debug("Project created: id=%s workdir=%s", project.id, project.workdir)
        return project

    async def get_project(self, project_id: str) -> Project | None:
        logger.debug("Getting project by id=%s", project_id)
        result = await self.session.execute(select(Project).where(Project.id == project_id))
        return result.scalar_one_or_none()

    async def get_project_by_workdir(self, workdir: str) -> Project | None:
        logger.debug("Querying project by workdir=%s", workdir)
        result = await self.session.execute(select(Project).where(Project.workdir == workdir))
        return result.scalar_one_or_none()

    async def list_projects(self, active_only: bool = True) -> Sequence[Project]:
        logger.debug("Listing projects (active_only=%s)", active_only)
        stmt = select(Project).order_by(Project.registered_at)
        if active_only:
            stmt = stmt.where(Project.active == True)  # noqa: E712
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def update_project(self, project_id: str, **kwargs) -> Project | None:
        logger.debug("Updating project id=%s kwargs=%s", project_id, kwargs)
        project = await self.get_project(project_id)
        if project is None:
            logger.debug("update_project: not found id=%s", project_id)
            return None
        for key, value in kwargs.items():
            if hasattr(project, key):
                setattr(project, key, value)
        await self.session.commit()
        await self.session.refresh(project)
        logger.debug("Project updated: id=%s", project_id)
        return project

    async def delete_project(self, project_id: str) -> bool:
        logger.debug("Deleting project id=%s", project_id)
        project = await self.get_project(project_id)
        if project is None:
            logger.debug("delete_project: not found id=%s", project_id)
            return False
        await self.session.delete(project)
        await self.session.commit()
        logger.info("Project deleted: id=%s", project_id)
        return True

    async def count_projects(self) -> int:
        logger.debug("Counting projects")
        result = await self.session.execute(select(func.count(Project.id)))
        return result.scalar() or 0

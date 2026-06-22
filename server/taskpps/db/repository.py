import json
import logging
from collections.abc import Sequence
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from taskpps.models.project import Project
from taskpps.models.run import PipelineRun, RunStatus, TaskRetryRecord, TaskRun, TaskStatus
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
        display_name: str = "",
    ) -> PipelineRun:
        logger.debug("Creating run: pipeline=%s project=%s", pipeline_name, project_id)
        run = PipelineRun(
            pipeline_name=pipeline_name,
            pipeline_file=pipeline_file,
            pipeline_id=pipeline_id,
            pipeline_version=pipeline_version,
            project_id=project_id,
            display_name=display_name,
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
        pipeline_file: str | None = None,
    ) -> int:
        stmt = select(func.count(PipelineRun.id))
        if pipeline:
            stmt = stmt.where(PipelineRun.pipeline_name == pipeline)
        if pipeline_id:
            stmt = stmt.where(PipelineRun.pipeline_id == pipeline_id)
        if pipeline_file:
            stmt = stmt.where(PipelineRun.pipeline_file == pipeline_file)
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
        pipeline_file: str | None = None,
    ) -> Sequence[PipelineRun]:
        stmt = select(PipelineRun).order_by(PipelineRun.created_at.desc())
        if pipeline:
            stmt = stmt.where(PipelineRun.pipeline_name == pipeline)
        if pipeline_file:
            stmt = stmt.where(PipelineRun.pipeline_file == pipeline_file)
        if status:
            stmt = stmt.where(PipelineRun.status == status)
        if project_id:
            stmt = stmt.where(PipelineRun.project_id == project_id)
        stmt = stmt.limit(limit)
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def list_runs_by_statuses(self, statuses: list[RunStatus]) -> Sequence[PipelineRun]:
        """按状态列表查询 runs（用于恢复停滞运行）。"""
        stmt = select(PipelineRun).where(PipelineRun.status.in_(statuses))
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def batch_update_stale_tasks(self, run_id: str, target_status: TaskStatus, source_statuses: list[TaskStatus], finished_at: datetime | None = None, error: str | None = None) -> int:
        """批量将指定 run 中处于 source_statuses 的 task 更新为 target_status。"""
        stmt = select(TaskRun).where(TaskRun.run_id == run_id, TaskRun.status.in_(source_statuses))
        result = await self.session.execute(stmt)
        tasks = result.scalars().all()
        count = 0
        for t in tasks:
            t.status = target_status
            if finished_at is not None:
                t.finished_at = finished_at
            if error is not None:
                t.error = error
            count += 1
        return count

    async def batch_update_stale_retries(self, run_id: str, target_status: TaskStatus, source_statuses: list[TaskStatus], finished_at: datetime | None = None, error: str | None = None) -> int:
        """批量将指定 run 中处于 source_statuses 的 retry_record 更新为 target_status。"""
        stmt = select(TaskRetryRecord).where(TaskRetryRecord.run_id == run_id, TaskRetryRecord.status.in_(source_statuses))
        result = await self.session.execute(stmt)
        records = result.scalars().all()
        count = 0
        for r in records:
            r.status = target_status
            if finished_at is not None:
                r.finished_at = finished_at
            if error is not None:
                r.error = error
            count += 1
        return count

    async def get_task_summaries(self, run_ids: list[str]) -> dict[str, dict[str, int]]:
        """批量获取多个 run 的任务状态计数。

        Returns:
            {run_id: {"pending": N, "running": N, "success": N, ...}}
        """
        if not run_ids:
            return {}
        stmt = (
            select(TaskRun.run_id, TaskRun.status, func.count())
            .where(TaskRun.run_id.in_(run_ids))
            .group_by(TaskRun.run_id, TaskRun.status)
        )
        result = await self.session.execute(stmt)
        summaries: dict[str, dict[str, int]] = {rid: {} for rid in run_ids}
        for run_id, status, count in result.fetchall():
            summaries.setdefault(run_id, {})[status] = count
        return summaries

    async def count_runs_by_status(
        self,
        pipeline: str | None = None,
        pipeline_id: str | None = None,
        project_id: str | None = None,
        pipeline_file: str | None = None,
    ) -> dict[str, int]:
        """按状态分组计数运行数量（一条 SQL 聚合）。"""
        stmt = select(PipelineRun.status, func.count(PipelineRun.id)).group_by(PipelineRun.status)
        if pipeline:
            stmt = stmt.where(PipelineRun.pipeline_name == pipeline)
        if pipeline_id:
            stmt = stmt.where(PipelineRun.pipeline_id == pipeline_id)
        if pipeline_file:
            stmt = stmt.where(PipelineRun.pipeline_file == pipeline_file)
        if project_id:
            stmt = stmt.where(PipelineRun.project_id == project_id)
        result = await self.session.execute(stmt)
        return {status: count for status, count in result.fetchall()}

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

    async def delete_run_by_id(self, run_id: str) -> int:
        stmt = delete(PipelineRun).where(PipelineRun.id == run_id)
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

    async def get_task_statuses_by_ids(self, task_ids: list[str]) -> dict[str, TaskStatus]:
        """批量查询多个 task_run 的状态，返回 {task_run_id: status}。"""
        if not task_ids:
            return {}
        result = await self.session.execute(
            select(TaskRun.id, TaskRun.status).where(TaskRun.id.in_(task_ids))
        )
        return {row[0]: row[1] for row in result.fetchall()}

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

    async def update_stuck_tasks(
        self,
        run_id: str,
        status: TaskStatus,
        finished_at: datetime | None = None,
    ) -> int:
        """将指定 run 中仍处于 RUNNING 或 PENDING 的 task 批量更新为终态。

        用于 PipelineRunner.run() 的 finally 兜底，确保异常中断时
        不会有 task 永远卡在"运行中"状态。
        """
        stmt = select(TaskRun).where(
            TaskRun.run_id == run_id,
            TaskRun.status.in_([TaskStatus.RUNNING, TaskStatus.PENDING]),
        )
        result = await self.session.execute(stmt)
        tasks = result.scalars().all()
        count = 0
        for t in tasks:
            t.status = status
            if finished_at is not None:
                t.finished_at = finished_at
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


class RetryRecordRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_retry_record(
        self,
        run_id: str,
        task_run_id: str,
        task_name: str,
        subpipeline_name: str,
        retry_version: int,
        command: str,
        original_command: str,
        log_path: str,
    ) -> TaskRetryRecord:
        record = TaskRetryRecord(
            run_id=run_id,
            task_run_id=task_run_id,
            task_name=task_name,
            subpipeline_name=subpipeline_name,
            retry_version=retry_version,
            command=command,
            original_command=original_command,
            log_path=log_path,
            status=TaskStatus.PENDING,
        )
        self.session.add(record)
        await self.session.commit()
        await self.session.refresh(record)
        return record

    async def get_retry_record(self, retry_id: str) -> TaskRetryRecord | None:
        result = await self.session.execute(
            select(TaskRetryRecord).where(TaskRetryRecord.id == retry_id)
        )
        return result.scalar_one_or_none()

    async def list_retries_by_task(self, run_id: str, task_name: str) -> Sequence[TaskRetryRecord]:
        result = await self.session.execute(
            select(TaskRetryRecord)
            .where(TaskRetryRecord.run_id == run_id, TaskRetryRecord.task_name == task_name)
            .order_by(TaskRetryRecord.retry_version)
        )
        return result.scalars().all()

    async def list_retries_by_run(self, run_id: str) -> Sequence[TaskRetryRecord]:
        result = await self.session.execute(
            select(TaskRetryRecord)
            .where(TaskRetryRecord.run_id == run_id)
            .order_by(TaskRetryRecord.created_at)
        )
        return result.scalars().all()

    async def update_retry_status(
        self,
        retry_id: str,
        status: TaskStatus,
        exit_code: int | None = None,
        error: str | None = None,
        started_at: datetime | None = None,
        finished_at: datetime | None = None,
    ) -> None:
        record = await self.get_retry_record(retry_id)
        if record is None:
            return
        record.status = status
        if exit_code is not None:
            record.exit_code = exit_code
        if error is not None:
            record.error = error
        if started_at is not None:
            record.started_at = started_at
        if finished_at is not None:
            record.finished_at = finished_at
        await self.session.commit()

    async def update_retry_command(self, retry_id: str, command: str) -> None:
        record = await self.get_retry_record(retry_id)
        if record is None:
            return
        record.command = command
        await self.session.commit()

    async def get_next_retry_version(self, run_id: str, task_name: str) -> int:
        result = await self.session.execute(
            select(func.max(TaskRetryRecord.retry_version))
            .where(TaskRetryRecord.run_id == run_id, TaskRetryRecord.task_name == task_name)
        )
        max_ver = result.scalar()
        return (max_ver or 0) + 1

    async def delete_retries_for_run(self, run_id: str) -> int:
        stmt = delete(TaskRetryRecord).where(TaskRetryRecord.run_id == run_id)
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

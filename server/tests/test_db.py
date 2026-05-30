import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from taskpps.db.engine import get_session_factory, init_db
from taskpps.db.repository import RunRepository, TaskRunRepository, TriggerRepository
from taskpps.models.run import RunStatus, TaskStatus, TaskType


@pytest.mark.asyncio
async def test_create_run(db_engine, clean_db):
    async with get_session_factory()() as session:
        repo = RunRepository(session)
        run = await repo.create_run("test-pipeline", "test.yaml", params={"key": "value"})
        assert run.id is not None
        assert run.pipeline_name == "test-pipeline"
        assert run.status == RunStatus.PENDING
        assert run.pipeline_file == "test.yaml"


@pytest.mark.asyncio
async def test_get_run(db_engine, clean_db):
    async with get_session_factory()() as session:
        repo = RunRepository(session)
        created = await repo.create_run("test-pipeline")
        fetched = await repo.get_run(created.id)
        assert fetched is not None
        assert fetched.id == created.id


@pytest.mark.asyncio
async def test_list_runs(db_engine, clean_db):
    async with get_session_factory()() as session:
        repo = RunRepository(session)
        await repo.create_run("pipeline-1")
        await repo.create_run("pipeline-2")
        runs = await repo.list_runs()
        assert len(runs) == 2


@pytest.mark.asyncio
async def test_list_runs_filter(db_engine, clean_db):
    async with get_session_factory()() as session:
        repo = RunRepository(session)
        await repo.create_run("pipeline-1")
        await repo.create_run("pipeline-2")
        runs = await repo.list_runs(pipeline="pipeline-1")
        assert len(runs) == 1
        assert runs[0].pipeline_name == "pipeline-1"


@pytest.mark.asyncio
async def test_update_run_status(db_engine, clean_db):
    async with get_session_factory()() as session:
        repo = RunRepository(session)
        run = await repo.create_run("test")
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc)
        await repo.update_run_status(run.id, RunStatus.RUNNING, started_at=now)
        updated = await repo.get_run(run.id)
        assert updated.status == RunStatus.RUNNING
        assert updated.started_at is not None


@pytest.mark.asyncio
async def test_delete_all_runs(db_engine, clean_db):
    async with get_session_factory()() as session:
        repo = RunRepository(session)
        await repo.create_run("test1")
        await repo.create_run("test2")
        count = await repo.delete_all_runs()
        assert count >= 2
        runs = await repo.list_runs()
        assert len(runs) == 0


@pytest.mark.asyncio
async def test_create_task_run(db_engine, clean_db):
    async with get_session_factory()() as session:
        run_repo = RunRepository(session)
        task_repo = TaskRunRepository(session)
        run = await run_repo.create_run("test")
        task = await task_repo.create_task_run(run.id, "task-1", "command", "/tmp/test.log")
        assert task.id is not None
        assert task.run_id == run.id
        assert task.task_name == "task-1"
        assert task.task_type == TaskType.COMMAND
        assert task.status == TaskStatus.PENDING


@pytest.mark.asyncio
async def test_update_task_status(db_engine, clean_db):
    async with get_session_factory()() as session:
        run_repo = RunRepository(session)
        task_repo = TaskRunRepository(session)
        run = await run_repo.create_run("test")
        task = await task_repo.create_task_run(run.id, "task-1")
        await task_repo.update_task_status(task.id, TaskStatus.RUNNING)
        updated = await task_repo.get_task_run(task.id)
        assert updated.status == TaskStatus.RUNNING

        await task_repo.update_task_status(task.id, TaskStatus.SUCCESS, exit_code=0)
        updated = await task_repo.get_task_run(task.id)
        assert updated.status == TaskStatus.SUCCESS
        assert updated.exit_code == 0


@pytest.mark.asyncio
async def test_cancel_pending_tasks(db_engine, clean_db):
    async with get_session_factory()() as session:
        run_repo = RunRepository(session)
        task_repo = TaskRunRepository(session)
        run = await run_repo.create_run("test")
        t1 = await task_repo.create_task_run(run.id, "task-1")
        t2 = await task_repo.create_task_run(run.id, "task-2")
        count = await task_repo.cancel_pending_tasks(run.id)
        assert count == 2
        updated1 = await task_repo.get_task_run(t1.id)
        assert updated1.status == TaskStatus.CANCELLED


@pytest.mark.asyncio
async def test_list_task_runs(db_engine, clean_db):
    async with get_session_factory()() as session:
        run_repo = RunRepository(session)
        task_repo = TaskRunRepository(session)
        run = await run_repo.create_run("test")
        await task_repo.create_task_run(run.id, "task-1")
        await task_repo.create_task_run(run.id, "task-2")
        tasks = await task_repo.list_task_runs(run.id)
        assert len(tasks) == 2


@pytest.mark.asyncio
async def test_trigger_crud(db_engine, clean_db):
    async with get_session_factory()() as session:
        repo = TriggerRepository(session)
        trigger = await repo.create_trigger("cron", {"schedule": "0 * * * *"}, "deploy.yaml")
        assert trigger.id is not None
        assert trigger.type == "cron"

        fetched = await repo.get_trigger(trigger.id)
        assert fetched is not None

        triggers = await repo.list_triggers()
        assert len(triggers) >= 1

        deleted = await repo.delete_trigger(trigger.id)
        assert deleted is True

        deleted_again = await repo.delete_trigger(trigger.id)
        assert deleted_again is False

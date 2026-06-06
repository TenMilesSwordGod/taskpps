from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import create_async_engine
from sqlmodel import SQLModel

from taskpps.db import _get_repos
from taskpps.db.engine import (
    close_db,
    get_engine,
    get_session,
    get_session_factory,
    init_db,
    reset_engine,
    set_engine,
)
from taskpps.db.repository import RunRepository, TaskRunRepository, TriggerRepository
from taskpps.models.run import RunStatus, TaskStatus, TaskType


class TestDBEngine:
    def test_reset_engine(self):
        reset_engine()
        from taskpps.db import engine as eng

        assert eng._engine is None
        assert eng._session_factory is None

    @pytest.mark.asyncio
    async def test_set_engine(self, tmp_path):
        db_file = tmp_path / "custom.db"
        engine = create_async_engine(
            f"sqlite+aiosqlite:///{db_file}",
            connect_args={"check_same_thread": False},
        )
        set_engine(engine)
        assert get_engine() is engine
        assert get_session_factory() is not None
        async with engine.begin() as conn:
            await conn.run_sync(SQLModel.metadata.create_all)
        await engine.dispose()
        reset_engine()

    @pytest.mark.asyncio
    async def test_get_engine_reuses(self):
        reset_engine()
        from taskpps.config import _project_root

        old_root = _project_root
        _project_root = Path("/tmp")
        try:
            engine1 = get_engine()
            engine2 = get_engine()
            assert engine1 is engine2
            await engine1.dispose()
        finally:
            _project_root = old_root
            reset_engine()

    @pytest.mark.asyncio
    async def test_get_engine_creates_new(self, tmp_path):
        reset_engine()
        from taskpps.config import _project_root

        old_root = _project_root
        _project_root = tmp_path
        try:
            engine = get_engine()
            assert engine is not None
            await engine.dispose()
        finally:
            _project_root = old_root
            reset_engine()

    @pytest.mark.asyncio
    async def test_init_db(self, tmp_path):
        reset_engine()
        db_file = tmp_path / "test_init.db"
        engine = create_async_engine(
            f"sqlite+aiosqlite:///{db_file}",
            connect_args={"check_same_thread": False},
        )
        set_engine(engine)
        await init_db()
        assert db_file.exists()
        await engine.dispose()
        reset_engine()

    @pytest.mark.asyncio
    async def test_close_db(self, tmp_path):
        reset_engine()
        db_file = tmp_path / "test_close.db"
        engine = create_async_engine(
            f"sqlite+aiosqlite:///{db_file}",
            connect_args={"check_same_thread": False},
        )
        set_engine(engine)
        await close_db()
        from taskpps.db.engine import _engine, _session_factory

        assert _engine is None
        assert _session_factory is None

    @pytest.mark.asyncio
    async def test_close_db_no_engine(self):
        reset_engine()
        await close_db()

    @pytest.mark.asyncio
    async def test_get_session(self, tmp_path):
        reset_engine()
        db_file = tmp_path / "test_session.db"
        engine = create_async_engine(
            f"sqlite+aiosqlite:///{db_file}",
            connect_args={"check_same_thread": False},
        )
        set_engine(engine)
        async with engine.begin() as conn:
            await conn.run_sync(SQLModel.metadata.create_all)

        async for session in get_session():
            assert session is not None
            break

        await engine.dispose()
        reset_engine()

    def test_get_repos(self):
        repos = _get_repos()
        assert repos == (RunRepository, TaskRunRepository, TriggerRepository)


class TestRunRepository:
    @pytest.mark.asyncio
    async def test_create_run(self, db_engine, clean_db):
        async with get_session_factory()() as session:
            repo = RunRepository(session)
            run = await repo.create_run("test-pipeline", "test.yaml", params={"key": "value"})
            assert run.id is not None
            assert run.pipeline_name == "test-pipeline"
            assert run.status == RunStatus.PENDING
            assert run.pipeline_file == "test.yaml"

    @pytest.mark.asyncio
    async def test_get_run(self, db_engine, clean_db):
        async with get_session_factory()() as session:
            repo = RunRepository(session)
            created = await repo.create_run("test-pipeline")
            fetched = await repo.get_run(created.id)
            assert fetched is not None
            assert fetched.id == created.id

    @pytest.mark.asyncio
    async def test_list_runs(self, db_engine, clean_db):
        async with get_session_factory()() as session:
            repo = RunRepository(session)
            await repo.create_run("pipeline-1")
            await repo.create_run("pipeline-2")
            runs = await repo.list_runs()
            assert len(runs) == 2

    @pytest.mark.asyncio
    async def test_list_runs_filter(self, db_engine, clean_db):
        async with get_session_factory()() as session:
            repo = RunRepository(session)
            await repo.create_run("pipeline-1")
            await repo.create_run("pipeline-2")
            runs = await repo.list_runs(pipeline="pipeline-1")
            assert len(runs) == 1
            assert runs[0].pipeline_name == "pipeline-1"

    @pytest.mark.asyncio
    async def test_update_run_status(self, db_engine, clean_db):
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
    async def test_delete_all_runs(self, db_engine, clean_db):
        async with get_session_factory()() as session:
            repo = RunRepository(session)
            await repo.create_run("test1")
            await repo.create_run("test2")
            count = await repo.delete_all_runs()
            assert count >= 2
            runs = await repo.list_runs()
            assert len(runs) == 0


class TestTaskRunRepository:
    @pytest.mark.asyncio
    async def test_create_task_run(self, db_engine, clean_db):
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
    async def test_update_task_status(self, db_engine, clean_db):
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
    async def test_cancel_pending_tasks(self, db_engine, clean_db):
        async with get_session_factory()() as session:
            run_repo = RunRepository(session)
            task_repo = TaskRunRepository(session)
            run = await run_repo.create_run("test")
            t1 = await task_repo.create_task_run(run.id, "task-1")
            await task_repo.create_task_run(run.id, "task-2")
            count = await task_repo.cancel_pending_tasks(run.id)
            assert count == 2
            updated1 = await task_repo.get_task_run(t1.id)
            assert updated1.status == TaskStatus.CANCELLED

    @pytest.mark.asyncio
    async def test_list_task_runs(self, db_engine, clean_db):
        async with get_session_factory()() as session:
            run_repo = RunRepository(session)
            task_repo = TaskRunRepository(session)
            run = await run_repo.create_run("test")
            await task_repo.create_task_run(run.id, "task-1")
            await task_repo.create_task_run(run.id, "task-2")
            tasks = await task_repo.list_task_runs(run.id)
            assert len(tasks) == 2


class TestTriggerRepository:
    @pytest.mark.asyncio
    async def test_trigger_crud(self, db_engine, clean_db):
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

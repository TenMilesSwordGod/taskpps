import asyncio
from pathlib import Path

import pytest
from sqlalchemy import text
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
from taskpps.db.repository import ProjectRepository, RunRepository, TaskRunRepository, TriggerRepository
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
    async def test_init_db_concurrent(self, tmp_path, monkeypatch):
        """回归测试:多 task 并发调 init_db 不能炸出 'table already exists'。

        复现 gunicorn 多 worker 启动时的竞态:SQLAlchemy create_all 是
        check-then-create,跨任务并发跑会撞 TOCTOU。fix 是在 init_db 里加
        fcntl 文件锁,这里验证锁能起到串行化作用。

        注意:同进程内的多个 asyncio task 共享 flock 文件。修复后每次 init_db
        都新开 fd 走 flock,后到的 task 在 flock 上阻塞直到前者释放,不会撞车。
        """
        # 把 data dir 指到 tmp_path(避免污染真实 workdir / 留 lock 文件)
        monkeypatch.setattr("taskpps.config._project_root", tmp_path)
        monkeypatch.setattr("taskpps.config._server_home", tmp_path)
        monkeypatch.setattr("taskpps.config._project_workdir", tmp_path)
        monkeypatch.setattr("taskpps.config._settings", None)

        reset_engine()

        db_file = tmp_path / "concurrent.db"
        engine = create_async_engine(
            f"sqlite+aiosqlite:///{db_file}",
            connect_args={"check_same_thread": False, "timeout": 30},
        )
        set_engine(engine)

        try:
            # 5 个 task 并发 init_db,修复前会报 "table runs already exists"
            await asyncio.gather(*(init_db() for _ in range(5)))
            async with engine.begin() as conn:
                rows = (await conn.execute(text("SELECT name FROM sqlite_master WHERE type='table'"))).fetchall()
                table_names = {r[0] for r in rows}
            assert "runs" in table_names
            assert "task_runs" in table_names
        finally:
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


class TestProjectRepository:
    @pytest.mark.asyncio
    async def test_create_project(self, db_engine, clean_db):
        async with get_session_factory()() as session:
            repo = ProjectRepository(session)
            project = await repo.create_project("/opt/project-a", name="project-a")
            assert project.id is not None
            assert len(project.id) == 12
            assert project.workdir == "/opt/project-a"
            assert project.name == "project-a"
            assert project.active is True

    @pytest.mark.asyncio
    async def test_get_project(self, db_engine, clean_db):
        async with get_session_factory()() as session:
            repo = ProjectRepository(session)
            created = await repo.create_project("/opt/project-b")
            fetched = await repo.get_project(created.id)
            assert fetched is not None
            assert fetched.id == created.id
            assert fetched.workdir == "/opt/project-b"

    @pytest.mark.asyncio
    async def test_get_project_not_found(self, db_engine, clean_db):
        async with get_session_factory()() as session:
            repo = ProjectRepository(session)
            fetched = await repo.get_project("nonexistent")
            assert fetched is None

    @pytest.mark.asyncio
    async def test_get_project_by_workdir(self, db_engine, clean_db):
        async with get_session_factory()() as session:
            repo = ProjectRepository(session)
            await repo.create_project("/opt/project-c", name="project-c")
            found = await repo.get_project_by_workdir("/opt/project-c")
            assert found is not None
            assert found.name == "project-c"

    @pytest.mark.asyncio
    async def test_get_project_by_workdir_not_found(self, db_engine, clean_db):
        async with get_session_factory()() as session:
            repo = ProjectRepository(session)
            found = await repo.get_project_by_workdir("/nonexistent")
            assert found is None

    @pytest.mark.asyncio
    async def test_list_projects(self, db_engine, clean_db):
        async with get_session_factory()() as session:
            repo = ProjectRepository(session)
            await repo.create_project("/opt/p1", name="p1")
            await repo.create_project("/opt/p2", name="p2")
            projects = await repo.list_projects()
            assert len(projects) == 2

    @pytest.mark.asyncio
    async def test_list_projects_active_only(self, db_engine, clean_db):
        async with get_session_factory()() as session:
            repo = ProjectRepository(session)
            await repo.create_project("/opt/p1", name="p1")
            p2 = await repo.create_project("/opt/p2", name="p2")
            await repo.update_project(p2.id, active=False)
            active = await repo.list_projects(active_only=True)
            assert len(active) == 1
            assert active[0].name == "p1"
            all_projects = await repo.list_projects(active_only=False)
            assert len(all_projects) == 2

    @pytest.mark.asyncio
    async def test_update_project(self, db_engine, clean_db):
        async with get_session_factory()() as session:
            repo = ProjectRepository(session)
            created = await repo.create_project("/opt/project-d", name="old-name")
            updated = await repo.update_project(created.id, name="new-name", active=False)
            assert updated is not None
            assert updated.name == "new-name"
            assert updated.active is False

    @pytest.mark.asyncio
    async def test_delete_project(self, db_engine, clean_db):
        async with get_session_factory()() as session:
            repo = ProjectRepository(session)
            created = await repo.create_project("/opt/project-e")
            deleted = await repo.delete_project(created.id)
            assert deleted is True
            fetched = await repo.get_project(created.id)
            assert fetched is None

    @pytest.mark.asyncio
    async def test_delete_project_not_found(self, db_engine, clean_db):
        async with get_session_factory()() as session:
            repo = ProjectRepository(session)
            deleted = await repo.delete_project("nonexistent")
            assert deleted is False

    @pytest.mark.asyncio
    async def test_count_projects(self, db_engine, clean_db):
        async with get_session_factory()() as session:
            repo = ProjectRepository(session)
            assert await repo.count_projects() == 0
            await repo.create_project("/opt/p1")
            await repo.create_project("/opt/p2")
            assert await repo.count_projects() == 2

    @pytest.mark.asyncio
    async def test_create_run_with_project_id(self, db_engine, clean_db):
        async with get_session_factory()() as session:
            proj_repo = ProjectRepository(session)
            run_repo = RunRepository(session)
            project = await proj_repo.create_project("/opt/project-x", name="project-x")
            run = await run_repo.create_run("test-pipeline", project_id=project.id)
            assert run.project_id == project.id

    @pytest.mark.asyncio
    async def test_list_runs_by_project_id(self, db_engine, clean_db):
        async with get_session_factory()() as session:
            proj_repo = ProjectRepository(session)
            run_repo = RunRepository(session)
            p1 = await proj_repo.create_project("/opt/p1")
            p2 = await proj_repo.create_project("/opt/p2")
            await run_repo.create_run("pipe-a", project_id=p1.id)
            await run_repo.create_run("pipe-b", project_id=p1.id)
            await run_repo.create_run("pipe-c", project_id=p2.id)
            p1_runs = await run_repo.list_runs(project_id=p1.id)
            assert len(p1_runs) == 2
            p2_runs = await run_repo.list_runs(project_id=p2.id)
            assert len(p2_runs) == 1


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
    async def test_list_runs_filter_by_file(self, db_engine, clean_db):
        async with get_session_factory()() as session:
            repo = RunRepository(session)
            await repo.create_run("pipe-a", pipeline_file="proj1/deploy.yaml")
            await repo.create_run("pipe-a", pipeline_file="proj2/deploy.yaml")
            runs = await repo.list_runs(pipeline_file="proj1/deploy.yaml")
            assert len(runs) == 1
            assert runs[0].pipeline_file == "proj1/deploy.yaml"

    @pytest.mark.asyncio
    async def test_list_runs_same_name_different_file(self, db_engine, clean_db):
        async with get_session_factory()() as session:
            repo = RunRepository(session)
            await repo.create_run("build", pipeline_file="proj1/build.yaml")
            # Update status to running
            await repo.update_run_status((await repo.list_runs(pipeline_file="proj1/build.yaml"))[0].id, RunStatus.RUNNING)
            await repo.create_run("build", pipeline_file="proj2/build.yaml")
            proj1_runs = await repo.list_runs(pipeline_file="proj1/build.yaml")
            proj2_runs = await repo.list_runs(pipeline_file="proj2/build.yaml")
            assert len(proj1_runs) == 1
            assert proj1_runs[0].status == RunStatus.RUNNING
            assert len(proj2_runs) == 1
            assert proj2_runs[0].status == RunStatus.PENDING

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


class TestRunRepositoryMore:
    @pytest.mark.asyncio
    async def test_get_last_run_by_pipeline(self, db_engine, clean_db):
        async with get_session_factory()() as session:
            repo = RunRepository(session)
            await repo.create_run("pipe", pipeline_id="pid-1", pipeline_version="v1")
            await repo.create_run("pipe", pipeline_id="pid-1", pipeline_version="v2")

            last = await repo.get_last_run_by_pipeline("pid-1")
            assert last is not None
            assert last.pipeline_version == "v2"

    @pytest.mark.asyncio
    async def test_get_last_run_by_pipeline_none(self, db_engine, clean_db):
        async with get_session_factory()() as session:
            repo = RunRepository(session)
            result = await repo.get_last_run_by_pipeline("nonexistent")
            assert result is None

    @pytest.mark.asyncio
    async def test_list_versions(self, db_engine, clean_db):
        async with get_session_factory()() as session:
            repo = RunRepository(session)
            await repo.create_run("pipe", pipeline_id="pid-1", pipeline_version="v2")
            await repo.create_run("pipe", pipeline_id="pid-1", pipeline_version="v1")

            versions = await repo.list_versions("pid-1")
            assert versions == ["v1", "v2"]  # ordered by created_at desc

    @pytest.mark.asyncio
    async def test_list_versions_empty(self, db_engine, clean_db):
        async with get_session_factory()() as session:
            repo = RunRepository(session)
            versions = await repo.list_versions("nonexistent")
            assert versions == []

    @pytest.mark.asyncio
    async def test_delete_runs_by_version(self, db_engine, clean_db):
        async with get_session_factory()() as session:
            repo = RunRepository(session)
            await repo.create_run("pipe", pipeline_id="pid-1", pipeline_version="v1")
            await repo.create_run("pipe", pipeline_id="pid-1", pipeline_version="v2")

            count = await repo.delete_runs_by_version("pid-1", "v1")
            assert count == 1

    @pytest.mark.asyncio
    async def test_count_runs(self, db_engine, clean_db):
        async with get_session_factory()() as session:
            repo = RunRepository(session)
            assert await repo.count_runs() == 0
            await repo.create_run("pipe-a")
            await repo.create_run("pipe-b")
            assert await repo.count_runs() == 2
            assert await repo.count_runs(pipeline="pipe-a") == 1
            assert await repo.count_runs(status="pending") == 2

    @pytest.mark.asyncio
    async def test_count_runs_by_file(self, db_engine, clean_db):
        async with get_session_factory()() as session:
            repo = RunRepository(session)
            await repo.create_run("deploy", pipeline_file="proj1/deploy.yaml")
            await repo.create_run("deploy", pipeline_file="proj2/deploy.yaml")
            assert await repo.count_runs(pipeline_file="proj1/deploy.yaml") == 1
            assert await repo.count_runs(pipeline_file="proj2/deploy.yaml") == 1
            assert await repo.count_runs(pipeline_file="proj1/deploy.yaml", status="pending") == 1

    @pytest.mark.asyncio
    async def test_delete_runs_older_than(self, db_engine, clean_db):
        from datetime import datetime, timedelta, timezone

        async with get_session_factory()() as session:
            repo = RunRepository(session)
            run = await repo.create_run("pipe")
            # Set created_at to 30 days ago
            run.created_at = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=30)
            await session.commit()

            count = await repo.delete_runs_older_than(7)
            assert count == 1

    @pytest.mark.asyncio
    async def test_delete_runs_keep(self, db_engine, clean_db):
        async with get_session_factory()() as session:
            repo = RunRepository(session)
            await repo.create_run("pipe")
            await repo.create_run("pipe")
            await repo.create_run("pipe")

            count = await repo.delete_runs_keep(2)
            assert count == 1  # 3 - 2 = 1 deleted

    @pytest.mark.asyncio
    async def test_delete_runs_keep_zero(self, db_engine, clean_db):
        async with get_session_factory()() as session:
            repo = RunRepository(session)
            await repo.create_run("pipe")
            await repo.create_run("pipe")

            count = await repo.delete_runs_keep(0)
            assert count == 2

    @pytest.mark.asyncio
    async def test_delete_runs_keep_negative(self, db_engine, clean_db):
        async with get_session_factory()() as session:
            repo = RunRepository(session)
            with pytest.raises(ValueError, match="keep must be non-negative"):
                await repo.delete_runs_keep(-1)

    @pytest.mark.asyncio
    async def test_update_run_status_finished_at(self, db_engine, clean_db):
        from datetime import datetime, timezone

        async with get_session_factory()() as session:
            repo = RunRepository(session)
            run = await repo.create_run("test")
            now = datetime.now(timezone.utc)
            await repo.update_run_status(run.id, RunStatus.SUCCESS, finished_at=now)
            updated = await repo.get_run(run.id)
            assert updated.status == RunStatus.SUCCESS
            assert updated.finished_at is not None


class TestTaskRunRepositoryMore:
    @pytest.mark.asyncio
    async def test_get_running_tasks(self, db_engine, clean_db):
        async with get_session_factory()() as session:
            run_repo = RunRepository(session)
            task_repo = TaskRunRepository(session)
            run = await run_repo.create_run("test")
            t1 = await task_repo.create_task_run(run.id, "task-1")
            await task_repo.create_task_run(run.id, "task-2")
            await task_repo.update_task_status(t1.id, TaskStatus.RUNNING)

            running = await task_repo.get_running_tasks(run.id)
            assert len(running) == 1
            assert running[0].task_name == "task-1"

    @pytest.mark.asyncio
    async def test_get_running_tasks_none(self, db_engine, clean_db):
        async with get_session_factory()() as session:
            run_repo = RunRepository(session)
            task_repo = TaskRunRepository(session)
            run = await run_repo.create_run("test")
            await task_repo.create_task_run(run.id, "task-1")

            running = await task_repo.get_running_tasks(run.id)
            assert len(running) == 0

    @pytest.mark.asyncio
    async def test_delete_tasks_for_run(self, db_engine, clean_db):
        async with get_session_factory()() as session:
            run_repo = RunRepository(session)
            task_repo = TaskRunRepository(session)
            run = await run_repo.create_run("test")
            await task_repo.create_task_run(run.id, "task-1")
            await task_repo.create_task_run(run.id, "task-2")

            count = await task_repo.delete_tasks_for_run(run.id)
            assert count == 2

            tasks = await task_repo.list_task_runs(run.id)
            assert len(tasks) == 0

    @pytest.mark.asyncio
    async def test_update_task_status_started_finished_at(self, db_engine, clean_db):
        from datetime import datetime, timezone

        async with get_session_factory()() as session:
            run_repo = RunRepository(session)
            task_repo = TaskRunRepository(session)
            run = await run_repo.create_run("test")
            task = await task_repo.create_task_run(run.id, "task-1")

            now = datetime.now(timezone.utc)
            await task_repo.update_task_status(
                task.id, TaskStatus.SUCCESS, exit_code=0, started_at=now, finished_at=now
            )
            updated = await task_repo.get_task_run(task.id)
            assert updated.started_at is not None
            assert updated.finished_at is not None

    @pytest.mark.asyncio
    async def test_update_stuck_tasks(self, db_engine, clean_db):
        """Issue #68: update_stuck_tasks 应将 RUNNING/PENDING 的 task 批量更新为终态。"""
        from datetime import datetime, timezone

        async with get_session_factory()() as session:
            run_repo = RunRepository(session)
            task_repo = TaskRunRepository(session)
            run = await run_repo.create_run("test")
            t1 = await task_repo.create_task_run(run.id, "task-1")
            t2 = await task_repo.create_task_run(run.id, "task-2")
            t3 = await task_repo.create_task_run(run.id, "task-3")
            # t1: RUNNING, t2: PENDING, t3: SUCCESS
            await task_repo.update_task_status(t1.id, TaskStatus.RUNNING)
            await task_repo.update_task_status(t3.id, TaskStatus.SUCCESS, exit_code=0)

            now = datetime.now(timezone.utc)
            count = await task_repo.update_stuck_tasks(run.id, TaskStatus.FAILED, finished_at=now)
            assert count == 2

            updated_t1 = await task_repo.get_task_run(t1.id)
            updated_t2 = await task_repo.get_task_run(t2.id)
            updated_t3 = await task_repo.get_task_run(t3.id)
            assert updated_t1.status == TaskStatus.FAILED
            assert updated_t2.status == TaskStatus.FAILED
            assert updated_t3.status == TaskStatus.SUCCESS  # 未被修改

    @pytest.mark.asyncio
    async def test_update_stuck_tasks_no_stuck(self, db_engine, clean_db):
        """没有卡住的 task 时，update_stuck_tasks 应返回 0。"""
        async with get_session_factory()() as session:
            run_repo = RunRepository(session)
            task_repo = TaskRunRepository(session)
            run = await run_repo.create_run("test")
            t1 = await task_repo.create_task_run(run.id, "task-1")
            await task_repo.update_task_status(t1.id, TaskStatus.SUCCESS, exit_code=0)

            from datetime import datetime, timezone
            count = await task_repo.update_stuck_tasks(
                run.id, TaskStatus.FAILED, finished_at=datetime.now(timezone.utc)
            )
            assert count == 0

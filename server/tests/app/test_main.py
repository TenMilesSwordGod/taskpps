from __future__ import annotations

import contextlib
from datetime import datetime, timedelta, timezone

import pytest

from taskpps.main import app as _app
from taskpps.models.run import RunStatus, TaskStatus


@contextlib.contextmanager
def _registered_active(*run_ids: str):
    """把 run 模拟注册进本进程活跃表（与 pipeline_service 的注册方式一致）。"""
    from taskpps.engine.runner import _active_runs

    for run_id in run_ids:
        _active_runs[run_id] = object()
    try:
        yield
    finally:
        for run_id in run_ids:
            _active_runs.pop(run_id, None)


class TestAppCreation:
    @pytest.mark.zentao("TC-S0038", domain="server/app", priority="P0")
    def test_create_app(self):
        assert _app is not None
        assert _app.title is not None

    @pytest.mark.zentao("TC-S0039", domain="server/app", priority="P0")
    def test_create_app_routes(self):
        routes = [r.path for r in _app.routes]
        assert "/api/health" in routes
        assert "/api/runs/" in routes


class TestAppLifespan:
    @pytest.mark.asyncio
    @pytest.mark.zentao("TC-S0040", domain="server/app", priority="P2")
    async def test_app_lifespan(self, setup_project, tmp_project):
        import taskpps.config as cfg

        cfg.set_project_root(tmp_project)
        cfg._settings = None
        cfg.load_settings(str(tmp_project / "taskpps.yaml"))

        from httpx import ASGITransport, AsyncClient

        transport = ASGITransport(app=_app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/api/health")
            assert response.status_code == 200


class TestStaleRunSweeper:
    """Issue #212: sweeper 只能恢复「无活跃 runner」的超时 RUNNING 运行。

    原实现仅凭 run.created_at 判断停滞，本进程内存 _active_runs 中仍在执行的
    合法长任务会被误标 FAILED，runner 完成后又覆盖状态，表现为「先失败后自动恢复」。
    测试配置 default_timeout=60 → 阈值 max(3600, 60*2) = 3600s。
    """

    THRESHOLD = 3600

    @staticmethod
    async def _create_run(
        pipeline: str,
        age_seconds: float,
        *,
        task_status: TaskStatus = TaskStatus.RUNNING,
        retry_statuses: tuple[TaskStatus, ...] = (),
    ) -> tuple[str, str, list[str]]:
        """建 RUNNING run + task（可选 retry 记录），created_at 拨到 age_seconds 之前。"""
        from taskpps.db.engine import get_session_factory
        from taskpps.db.repository import RetryRecordRepository, RunRepository, TaskRunRepository

        async with get_session_factory()() as session:
            run_repo = RunRepository(session)
            task_repo = TaskRunRepository(session)
            retry_repo = RetryRecordRepository(session)
            run = await run_repo.create_run(pipeline)
            now = datetime.now(timezone.utc)
            await run_repo.update_run_status(run.id, RunStatus.RUNNING, started_at=now)
            task = await task_repo.create_task_run(run.id, f"{pipeline}.task", "command", f"/tmp/{pipeline}.log")
            await task_repo.update_task_status(task.id, task_status, started_at=now)
            retry_ids: list[str] = []
            for version, status in enumerate(retry_statuses, start=1):
                record = await retry_repo.create_retry_record(
                    run.id,
                    task.id,
                    task.task_name,
                    "",
                    version,
                    "echo retry",
                    "echo retry",
                    f"/tmp/{pipeline}.retry.log",
                )
                if status != TaskStatus.PENDING:
                    await retry_repo.update_retry_status(record.id, status)
                retry_ids.append(record.id)
            # created_at 无法通过 create_run 指定，直接改 ORM 对象模拟历史遗留 run
            run.created_at = now - timedelta(seconds=age_seconds)
            await session.commit()
        return run.id, task.id, retry_ids

    @staticmethod
    async def _load_states(
        run_id: str, task_id: str, retry_ids: list[str] | None = None
    ) -> tuple[RunStatus, str | None, TaskStatus, list[TaskStatus]]:
        """在会话内取状态快照，避免 detached 对象属性过期。"""
        from taskpps.db.engine import get_session_factory
        from taskpps.db.repository import RetryRecordRepository, RunRepository, TaskRunRepository

        async with get_session_factory()() as session:
            run = await RunRepository(session).get_run(run_id)
            task = await TaskRunRepository(session).get_task_run(task_id)
            retry_states: list[TaskStatus] = []
            if retry_ids:
                retry_repo = RetryRecordRepository(session)
                for retry_id in retry_ids:
                    record = await retry_repo.get_retry_record(retry_id)
                    retry_states.append(record.status)
            return run.status, run.error, task.status, retry_states

    @pytest.mark.asyncio
    async def test_active_long_running_run_not_swept(self, db_engine, clean_db):
        """回归主用例：活跃 3h 的长运行不能被标记失败（修复前为红灯）。"""
        from taskpps.main import _sweep_stale_runs_once

        run_id, task_id, _ = await self._create_run("long-pipeline", self.THRESHOLD * 3)
        with _registered_active(run_id):
            recovered = await _sweep_stale_runs_once()

        run_status, run_error, task_status, _ = await self._load_states(run_id, task_id)
        assert recovered == 0
        assert run_status == RunStatus.RUNNING
        assert run_error is None
        assert task_status == TaskStatus.RUNNING

    @pytest.mark.asyncio
    async def test_active_run_pending_task_and_retries_untouched(self, db_engine, clean_db):
        """活跃 run 的 PENDING task 与 PENDING/RUNNING retry 记录都不能被触碰。"""
        from taskpps.main import _sweep_stale_runs_once

        run_id, task_id, retry_ids = await self._create_run(
            "active-pending-pipeline",
            self.THRESHOLD * 3,
            task_status=TaskStatus.PENDING,
            retry_statuses=(TaskStatus.PENDING, TaskStatus.RUNNING),
        )
        with _registered_active(run_id):
            recovered = await _sweep_stale_runs_once()

        run_status, _, task_status, retry_states = await self._load_states(run_id, task_id, retry_ids)
        assert recovered == 0
        assert run_status == RunStatus.RUNNING
        assert task_status == TaskStatus.PENDING
        assert retry_states == [TaskStatus.PENDING, TaskStatus.RUNNING]

    @pytest.mark.asyncio
    async def test_below_threshold_inactive_run_not_swept(self, db_engine, clean_db):
        """边界（阈值下方 60s）：未超时的 RUNNING run 不能被误恢复。"""
        from taskpps.main import _sweep_stale_runs_once

        run_id, task_id, _ = await self._create_run("fresh-pipeline", self.THRESHOLD - 60)
        recovered = await _sweep_stale_runs_once()

        run_status, _, task_status, _ = await self._load_states(run_id, task_id)
        assert recovered == 0
        assert run_status == RunStatus.RUNNING
        assert task_status == TaskStatus.RUNNING

    @pytest.mark.asyncio
    async def test_above_threshold_inactive_run_swept(self, db_engine, clean_db):
        """边界（阈值上方 60s）：无活跃 runner 的超时 run 仍被恢复为 FAILED。"""
        from taskpps.main import _sweep_stale_runs_once

        run_id, task_id, _ = await self._create_run("orphan-pipeline", self.THRESHOLD + 60)
        recovered = await _sweep_stale_runs_once()

        run_status, run_error, task_status, _ = await self._load_states(run_id, task_id)
        assert recovered == 1
        assert run_status == RunStatus.FAILED
        assert run_error is not None and "运行超时自动恢复" in run_error
        assert task_status == TaskStatus.FAILED

    @pytest.mark.asyncio
    async def test_inactive_stale_pending_task_and_retries_failed(self, db_engine, clean_db):
        """兜底完整性：PENDING task 与 PENDING/RUNNING retry 一并置 FAILED，终态 retry 不动。"""
        from taskpps.main import _sweep_stale_runs_once

        run_id, task_id, retry_ids = await self._create_run(
            "retry-pipeline",
            self.THRESHOLD + 60,
            task_status=TaskStatus.PENDING,
            retry_statuses=(TaskStatus.PENDING, TaskStatus.RUNNING, TaskStatus.SUCCESS),
        )
        recovered = await _sweep_stale_runs_once()

        run_status, _, task_status, retry_states = await self._load_states(run_id, task_id, retry_ids)
        assert recovered == 1
        assert run_status == RunStatus.FAILED
        assert task_status == TaskStatus.FAILED
        assert retry_states == [TaskStatus.FAILED, TaskStatus.FAILED, TaskStatus.SUCCESS]

    @pytest.mark.asyncio
    async def test_mixed_batch_only_stale_inactive_run_swept(self, db_engine, clean_db):
        """混合批次：只恢复无活跃 runner 的超时 run，活跃/未超时 run 不受影响。"""
        from taskpps.main import _sweep_stale_runs_once

        active_id, active_task, _ = await self._create_run("mixed-active", self.THRESHOLD * 3)
        stale_id, stale_task, _ = await self._create_run("mixed-stale", self.THRESHOLD * 3)
        fresh_id, fresh_task, _ = await self._create_run("mixed-fresh", self.THRESHOLD - 60)

        with _registered_active(active_id):
            recovered = await _sweep_stale_runs_once()

        assert recovered == 1
        assert (await self._load_states(active_id, active_task))[0] == RunStatus.RUNNING
        assert (await self._load_states(stale_id, stale_task))[0] == RunStatus.FAILED
        assert (await self._load_states(fresh_id, fresh_task))[0] == RunStatus.RUNNING

    @pytest.mark.asyncio
    async def test_threshold_follows_default_timeout_setting(self, db_engine, clean_db):
        """阈值随 default_timeout 提高：3h run 在阈值 14400s 下不应被恢复。"""
        from taskpps.config import get_settings
        from taskpps.main import _sweep_stale_runs_once

        settings = get_settings()
        original = settings.executor.default_timeout
        settings.executor.default_timeout = 7200  # 阈值 = max(3600, 14400) = 14400s
        try:
            run_id, task_id, _ = await self._create_run("long-timeout-pipeline", 3 * 3600)
            recovered = await _sweep_stale_runs_once()
        finally:
            settings.executor.default_timeout = original

        run_status, _, _, _ = await self._load_states(run_id, task_id)
        assert recovered == 0
        assert run_status == RunStatus.RUNNING

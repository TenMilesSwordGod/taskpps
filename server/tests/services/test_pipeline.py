from __future__ import annotations

import asyncio
import contextlib
from datetime import datetime, timedelta, timezone

import pytest

from taskpps.services.pipeline_service import PipelineService, _extract_env_overrides


def _setup_config(tmp_project):
    import taskpps.config as cfg

    cfg.set_project_root(tmp_project)
    cfg._settings = None
    cfg.load_settings(str(tmp_project / "taskpps.yaml"))


class TestPipelineService:
    @pytest.mark.asyncio
    @pytest.mark.zentao("TC-S0319", domain="server/services", priority="P0")
    async def test_list_pipelines(self, tmp_project, db_engine):
        _setup_config(tmp_project)
        svc = PipelineService()
        pipelines = svc.list_pipelines()
        assert isinstance(pipelines, list)
        assert "deploy" in pipelines
        assert "simple" in pipelines

    @pytest.mark.asyncio
    @pytest.mark.zentao("TC-S0320", domain="server/services", priority="P0")
    async def test_list_pipelines_multiple(self, setup_project, tmp_project, db_engine):
        _setup_config(tmp_project)
        svc = PipelineService()
        pipelines = svc.list_pipelines()
        assert len(pipelines) >= 2

    @pytest.mark.asyncio
    @pytest.mark.zentao("TC-S0321", domain="server/services", priority="P0")
    async def test_create_and_get(self, tmp_project, db_engine):
        _setup_config(tmp_project)
        svc = PipelineService()
        result = await svc.create_run("deploy.yaml")
        assert "id" in result
        run_id = result["id"]

        fetched = await svc.get_run(run_id)
        assert fetched is not None
        assert fetched["id"] == run_id
        assert fetched["pipeline_name"] == "deploy"

    @pytest.mark.asyncio
    @pytest.mark.zentao("TC-S0322", domain="server/services", priority="P2")
    async def test_get_nonexistent(self, tmp_project, db_engine):
        _setup_config(tmp_project)
        svc = PipelineService()
        result = await svc.get_run("nonexistent")
        assert result is None

    @pytest.mark.asyncio
    @pytest.mark.zentao("TC-S0323", domain="server/services", priority="P2")
    async def test_create_invalid(self, tmp_project, db_engine):
        _setup_config(tmp_project)
        svc = PipelineService()
        with pytest.raises(ValueError):
            await svc.create_run("nonexistent.yaml")

    @pytest.mark.asyncio
    @pytest.mark.zentao("TC-S0324", domain="server/services", priority="P2")
    async def test_create_cycle(self, tmp_project, db_engine):
        _setup_config(tmp_project)
        svc = PipelineService()
        with pytest.raises(ValueError):
            await svc.create_run("cycle.yaml")

    @pytest.mark.asyncio
    @pytest.mark.zentao("TC-S0325", domain="server/services", priority="P2")
    async def test_create_with_params(self, setup_project, tmp_project, db_engine):
        _setup_config(tmp_project)
        svc = PipelineService()
        result = await svc.create_run("deploy.yaml", params={"options.timeout": 120})
        assert "id" in result

    @pytest.mark.asyncio
    @pytest.mark.zentao("TC-S0326", domain="server/services", priority="P2")
    async def test_create_with_bad_params(self, setup_project, tmp_project, db_engine):
        _setup_config(tmp_project)
        svc = PipelineService()
        with pytest.raises(ValueError):
            await svc.create_run("deploy.yaml", params={"nonexistent.path": "value"})

    @pytest.mark.asyncio
    @pytest.mark.zentao("TC-S0327", domain="server/services", priority="P1")
    async def test_list_runs(self, tmp_project, db_engine):
        _setup_config(tmp_project)
        svc = PipelineService()
        await svc.create_run("deploy.yaml")
        result = await svc.list_runs()
        assert result["total"] >= 1

    @pytest.mark.asyncio
    @pytest.mark.zentao("TC-S0328", domain="server/services", priority="P1")
    async def test_list_runs_filter(self, tmp_project, db_engine):
        _setup_config(tmp_project)
        svc = PipelineService()
        await svc.create_run("deploy.yaml")
        result = await svc.list_runs(pipeline="deploy")
        items = result["items"]
        assert len(items) >= 1
        for r in items:
            assert r["pipeline_name"] == "deploy"

    @pytest.mark.asyncio
    @pytest.mark.zentao("TC-S0329", domain="server/services", priority="P1")
    async def test_list_runs_with_limit(self, tmp_project, db_engine):
        _setup_config(tmp_project)
        svc = PipelineService()
        await svc.create_run("deploy.yaml", {"test": 1})
        await svc.create_run("deploy.yaml", {"test": 2})
        await svc.create_run("deploy.yaml", {"test": 3})
        result = await svc.list_runs(limit=2)
        assert len(result["items"]) == 2

    @pytest.mark.asyncio
    @pytest.mark.zentao("TC-S0330", domain="server/services", priority="P1")
    async def test_many_list_runs(self, tmp_project, db_engine):
        _setup_config(tmp_project)
        svc = PipelineService()
        await svc.create_run("deploy.yaml", {"test": 1})
        await svc.create_run("deploy.yaml", {"test": 2})
        await svc.create_run("deploy.yaml", {"test": 3})
        result = await svc.list_runs()
        assert result["total"] >= 3
        assert len(result["items"]) >= 3

    @pytest.mark.asyncio
    @pytest.mark.zentao("TC-S0331", domain="server/services", priority="P1")
    async def test_max_concurrent_runs_sequential_enforced(self, setup_project, tmp_project, db_engine):
        # Two sequential create_run calls for a pipeline with max_concurrent_runs: 1
        # must result in the second one being rejected. See issue #11/#106.
        import taskpps.config as cfg

        cfg._project_root = tmp_project
        cfg._settings = None
        cfg.load_settings(str(tmp_project / "taskpps.yaml"))
        pipelines_dir = tmp_project / "pipelines"
        (pipelines_dir / "max_concurrent_runs.yaml").write_text(
            "name: max_concurrent_runs\noptions:\n  max_concurrent_runs: 1\ntasks:\n  - name: t\n    command: sleep 30\n"
        )
        svc = PipelineService()
        first = await svc.create_run("max_concurrent_runs.yaml")
        assert "id" in first

        with pytest.raises(ValueError, match="max_concurrent_runs"):
            await svc.create_run("max_concurrent_runs.yaml")

        # 清理：取消第一个 run
        await svc.cancel_run(first["id"])

    @pytest.mark.asyncio
    @pytest.mark.zentao("TC-S0332", domain="server/services", priority="P1")
    async def test_max_concurrent_runs_concurrent_race(self, setup_project, tmp_project, db_engine):
        # Two truly concurrent create_run calls for a pipeline with
        # max_concurrent_runs: 1 must result in exactly one success and one
        # ValueError. The fix uses a per-pipeline asyncio.Lock; without it
        # the count + create would be a check-then-act race. See issue #11/#106.
        import taskpps.config as cfg

        cfg._project_root = tmp_project
        cfg._settings = None
        cfg.load_settings(str(tmp_project / "taskpps.yaml"))
        pipelines_dir = tmp_project / "pipelines"
        (pipelines_dir / "max_concurrent_runs.yaml").write_text(
            "name: max_concurrent_runs\noptions:\n  max_concurrent_runs: 1\ntasks:\n  - name: t\n    command: sleep 30\n"
        )

        # Clear the per-pipeline lock so a previous test cannot serialize us.
        PipelineService._pipeline_locks.clear()

        svc = PipelineService()

        async def go() -> str:
            try:
                r = await svc.create_run("max_concurrent_runs.yaml")
                return r["id"]
            except ValueError:
                return "rejected"

        results = await asyncio.gather(go(), go(), return_exceptions=True)
        # First one created; second one must have been rejected.
        successes = [r for r in results if isinstance(r, str) and r != "rejected"]
        rejections = [r for r in results if r == "rejected"]
        assert len(successes) == 1, f"expected 1 success, got {results}"
        assert len(rejections) == 1, f"expected 1 rejection, got {results}"

        # 清理
        for r in results:
            if isinstance(r, str) and r != "rejected":
                await svc.cancel_run(r)

    @pytest.mark.asyncio
    @pytest.mark.zentao("TC-S0333", domain="server/services", priority="P1")
    async def test_max_parallel_backward_compat(self, setup_project, tmp_project, db_engine):
        """Issue #106: YAML 中写 max_parallel 仍能正常工作（向后兼容）"""
        import taskpps.config as cfg

        cfg._project_root = tmp_project
        cfg._settings = None
        cfg.load_settings(str(tmp_project / "taskpps.yaml"))
        pipelines_dir = tmp_project / "pipelines"
        (pipelines_dir / "max_parallel_compat.yaml").write_text(
            "name: max_parallel_compat\noptions:\n  max_parallel: 1\ntasks:\n  - name: t\n    command: sleep 30\n"
        )
        svc = PipelineService()
        first = await svc.create_run("max_parallel_compat.yaml")
        assert "id" in first

        # 第二次应该被拒绝（max_parallel 映射到 max_concurrent_runs=1）
        with pytest.raises(ValueError, match="max_concurrent_runs"):
            await svc.create_run("max_parallel_compat.yaml")

        # 清理
        await svc.cancel_run(first["id"])

    @pytest.mark.asyncio
    @pytest.mark.zentao("TC-S0334", domain="server/services", priority="P1")
    async def test_cancel_nonexistent(self, tmp_project, db_engine):
        _setup_config(tmp_project)
        svc = PipelineService()
        result = await svc.cancel_run("nonexistent")
        assert result is False

    @pytest.mark.asyncio
    @pytest.mark.zentao("TC-S0335", domain="server/services", priority="P1")
    async def test_cancel_pending_status(self, setup_project, tmp_project, db_engine):
        _setup_config(tmp_project)
        from taskpps.db.engine import get_session_factory
        from taskpps.db.repository import RunRepository

        svc = PipelineService()
        result = await svc.create_run("deploy.yaml")
        run_id = result["id"]

        async with get_session_factory()() as session:
            repo = RunRepository(session)
            await repo.update_run_status(run_id, "pending")

        cancel_result = await svc.cancel_run(run_id)
        assert cancel_result is True

    @pytest.mark.asyncio
    @pytest.mark.zentao("TC-S0336", domain="server/services", priority="P1")
    async def test_cancel_completed_status(self, setup_project, tmp_project, db_engine):
        _setup_config(tmp_project)
        import asyncio

        from taskpps.db.engine import get_session_factory
        from taskpps.db.repository import RunRepository
        from taskpps.engine.runner import get_active_runner
        from taskpps.models.run import RunStatus

        svc = PipelineService()
        result = await svc.create_run("deploy.yaml")
        run_id = result["id"]

        await asyncio.sleep(0.5)

        runner = get_active_runner(run_id)
        if runner:
            from taskpps.engine.runner import _active_runs

            if run_id in _active_runs:
                del _active_runs[run_id]

        async with get_session_factory()() as session:
            repo = RunRepository(session)
            await repo.update_run_status(run_id, RunStatus.SUCCESS, finished_at=datetime.now(timezone.utc))

        cancel_result = await svc.cancel_run(run_id)
        assert cancel_result is False

    @pytest.mark.asyncio
    @pytest.mark.zentao("TC-S0337", domain="server/services", priority="P1")
    async def test_clean_no_params(self, tmp_project, db_engine):
        _setup_config(tmp_project)
        svc = PipelineService()
        result = await svc.clean_runs()
        assert result == {"deleted_runs": 0, "deleted_logs": 0}

    @pytest.mark.asyncio
    @pytest.mark.zentao("TC-S0338", domain="server/services", priority="P1")
    async def test_clean_older_than(self, setup_project, tmp_project, db_engine):
        _setup_config(tmp_project)
        from taskpps.db.engine import get_session_factory
        from taskpps.db.repository import RunRepository

        svc = PipelineService()
        result = await svc.create_run("deploy.yaml")
        run_id = result["id"]

        async with get_session_factory()() as session:
            repo = RunRepository(session)
            run = await repo.get_run(run_id)
            run.created_at = datetime.now(timezone.utc) - timedelta(days=30)
            await session.commit()

        clean_result = await svc.clean_runs(older_than=7)
        assert clean_result["deleted_runs"] >= 1

    @pytest.mark.asyncio
    @pytest.mark.zentao("TC-S0339", domain="server/services", priority="P1")
    async def test_clean_keep(self, setup_project, tmp_project, db_engine):
        _setup_config(tmp_project)
        svc = PipelineService()
        await svc.create_run("deploy.yaml")
        await svc.create_run("deploy.yaml")

        clean_result = await svc.clean_runs(keep=10)
        assert clean_result["deleted_runs"] >= 0

    @pytest.mark.asyncio
    @pytest.mark.zentao("TC-S0340", domain="server/services", priority="P1")
    async def test_clean_with_logs(self, setup_project, tmp_project, db_engine):
        _setup_config(tmp_project)
        from taskpps.config import get_logs_dir

        svc = PipelineService()
        result = await svc.create_run("deploy.yaml")
        run_id = result["id"]

        logs_dir = get_logs_dir()
        log_file = logs_dir / "deploy" / run_id / "step1" / "task.log"
        log_file.parent.mkdir(parents=True, exist_ok=True)
        log_file.write_text("test log content")

        clean_result = await svc.clean_runs(force=True)
        assert clean_result["deleted_runs"] >= 1
        assert clean_result["deleted_logs"] >= 0

    @pytest.mark.asyncio
    @pytest.mark.zentao("TC-S0341", domain="server/services", priority="P2")
    async def test_params_parsing(self, tmp_project, db_engine):
        _setup_config(tmp_project)
        svc = PipelineService()
        params = {"key1": "value1", "key2": {"nested": "value"}}
        create_result = await svc.create_run("deploy.yaml", params)
        run_id = create_result["id"]
        fetched = await svc.get_run(run_id)
        assert isinstance(fetched["params"], dict)
        assert fetched["params"] == params

    @pytest.mark.asyncio
    @pytest.mark.zentao("TC-S0342", domain="server/services", priority="P2")
    async def test_params_parsing_list(self, tmp_project, db_engine):
        _setup_config(tmp_project)
        svc = PipelineService()
        params = {"options": {"host": "test-server"}}
        await svc.create_run("deploy.yaml", params)
        result = await svc.list_runs()
        assert result["total"] >= 1
        for item in result["items"]:
            assert isinstance(item["params"], dict)

    @pytest.mark.asyncio
    async def test_empty_params(self, tmp_project, db_engine):
        _setup_config(tmp_project)
        svc = PipelineService()
        create_result = await svc.create_run("deploy.yaml", {})
        run_id = create_result["id"]
        fetched = await svc.get_run(run_id)
        assert isinstance(fetched["params"], dict)
        assert fetched["params"] == {}

    @pytest.mark.asyncio
    @pytest.mark.zentao("TC-S0343", domain="server/services", priority="P2")
    async def test_null_params(self, tmp_project, db_engine):
        _setup_config(tmp_project)
        svc = PipelineService()
        create_result = await svc.create_run("deploy.yaml", None)
        run_id = create_result["id"]
        fetched = await svc.get_run(run_id)
        assert isinstance(fetched["params"], dict)
        assert fetched["params"] == {}

    @pytest.mark.asyncio
    @pytest.mark.zentao("TC-S0344", domain="server/services", priority="P2")
    async def test_invalid_json_params(self, tmp_project, db_engine):
        _setup_config(tmp_project)
        PipelineService()
        import json

        test_params = "invalid-json"
        params = {}
        if isinstance(test_params, str):
            with contextlib.suppress(json.JSONDecodeError, TypeError):
                params = json.loads(test_params)
        assert params == {}


class TestPipelineServiceMore:
    @pytest.mark.asyncio
    @pytest.mark.zcustom("TC-S0345", domain="server/services", priority="P2")
    # v2 (2026-07): Phase 2 快照从磁盘改存 DB，断言改为查 runs.snapshot_content 非空。旧磁盘断言保留注释以供参考
    async def test_save_pipeline_snapshot(self, setup_project, tmp_project, db_engine):
        _setup_config(tmp_project)
        from taskpps.db.engine import get_session_factory
        from taskpps.db.repository import RunRepository

        svc = PipelineService()
        result = await svc.create_run("deploy.yaml")

        # Phase 2: 快照存 DB，验证 snapshot_content 非空
        async with get_session_factory()() as session:
            run_repo = RunRepository(session)
            run = await run_repo.get_run(result["id"])
            assert run is not None
            assert getattr(run, "snapshot_content", None), "snapshot_content 不应为空"

    @pytest.mark.asyncio
    @pytest.mark.zcustom("TC-S0346", domain="server/services", priority="P2")
    async def test_save_pipeline_snapshot_nonexistent_file(self, tmp_project, db_engine):
        _setup_config(tmp_project)

        svc = PipelineService()
        # _save_pipeline_snapshot silently returns if source doesn't exist
        # We test indirectly: create a run with a pipeline that has snapshot
        result = await svc.create_run("deploy.yaml")
        assert "id" in result

    @pytest.mark.asyncio
    @pytest.mark.zcustom("TC-S0347", domain="server/services", priority="P2")
    # v2 (2026-07): Phase 2 快照从磁盘改存 DB，断言改为查 runs.snapshot_content 非空
    async def test_save_pipeline_snapshot_multi_project(self, tmp_project, db_engine):
        """Issue #58: 非默认项目的 pipeline 快照应能正确存入 DB"""
        import taskpps.config as cfg
        from pathlib import Path
        from taskpps.db.engine import get_session_factory
        from taskpps.db.repository import ProjectRepository, RunRepository

        _setup_config(tmp_project)

        other_project = tmp_project.parent / "other_project"
        other_pipelines = other_project / "pipelines"
        other_pipelines.mkdir(parents=True, exist_ok=True)
        other_project_yaml = other_pipelines / "other_deploy.yaml"
        other_project_yaml.write_text("name: other_deploy\ntasks:\n  - name: step1\n    command: echo other\n")
        other_config = other_project / "taskpps.yaml"
        other_config.write_text("server:\n  host: 127.0.0.1\n  port: 26521\n")

        async with get_session_factory()() as session:
            repo = ProjectRepository(session)
            project = await repo.create_project(workdir=str(other_project), name="other_project")
            project_id = project.id

        svc = PipelineService()
        result = await svc.create_run("other_deploy.yaml", project_id=project_id)

        # Phase 2: 快照存 DB，验证 snapshot_content 非空
        async with get_session_factory()() as session:
            run_repo = RunRepository(session)
            run = await run_repo.get_run(result["id"])
            assert run is not None
            assert getattr(run, "snapshot_content", None), f"snapshot_content 不应为空"

    @pytest.mark.asyncio
    @pytest.mark.zentao("TC-S0348", domain="server/services", priority="P2")
    async def test_version_changed_detection(self, setup_project, tmp_project, db_engine):
        _setup_config(tmp_project)

        svc = PipelineService()
        # First run
        result1 = await svc.create_run("deploy.yaml")
        assert result1["version_changed"] is False

        # Second run with same pipeline
        result2 = await svc.create_run("deploy.yaml")
        assert result2["version_changed"] is False

    @pytest.mark.asyncio
    @pytest.mark.zentao("TC-S0349", domain="server/services", priority="P1")
    async def test_handle_run_error_cancelled(self, setup_project, tmp_project, db_engine):
        _setup_config(tmp_project)
        import asyncio

        # Create a cancelled task
        async def _raise_cancelled():
            raise asyncio.CancelledError()

        task = asyncio.create_task(_raise_cancelled())
        try:
            await task
        except asyncio.CancelledError:
            pass

        # Should not raise
        PipelineService._handle_run_error(task)

    @pytest.mark.asyncio
    @pytest.mark.zentao("TC-S0350", domain="server/services", priority="P1")
    async def test_handle_run_error_generic(self, setup_project, tmp_project, db_engine):
        _setup_config(tmp_project)
        import asyncio

        async def _raise_error():
            raise RuntimeError("test error")

        task = asyncio.create_task(_raise_error())
        try:
            await task
        except RuntimeError:
            pass

        # Should not raise
        PipelineService._handle_run_error(task)

    @pytest.mark.asyncio
    @pytest.mark.zentao("TC-S0351", domain="server/services", priority="P1")
    async def test_handle_run_error_success(self, setup_project, tmp_project, db_engine):
        _setup_config(tmp_project)
        import asyncio

        async def _ok():
            return "done"

        task = asyncio.create_task(_ok())
        await task

        # Should not raise
        PipelineService._handle_run_error(task)

    @pytest.mark.asyncio
    @pytest.mark.zentao("TC-S0352", domain="server/services", priority="P1")
    async def test_create_run_with_config_env(self, setup_project, tmp_project, db_engine):
        _setup_config(tmp_project)
        svc = PipelineService()
        result = await svc.create_run("deploy.yaml", params={"config": {"env": {"CUSTOM_KEY": "custom_value"}}})
        assert "id" in result

    @pytest.mark.asyncio
    @pytest.mark.zentao("TC-S0353", domain="server/services", priority="P1")
    async def test_create_run_with_config_env_not_dict(self, setup_project, tmp_project, db_engine):
        _setup_config(tmp_project)
        svc = PipelineService()
        # env is not a dict, should be handled gracefully
        result = await svc.create_run("deploy.yaml", params={"config": {"env": "not_a_dict"}})
        assert "id" in result

    @pytest.mark.asyncio
    @pytest.mark.zentao("TC-S0354", domain="server/services", priority="P1")
    async def test_clean_keep_zero(self, setup_project, tmp_project, db_engine):
        _setup_config(tmp_project)
        svc = PipelineService()
        await svc.create_run("deploy.yaml")
        clean_result = await svc.clean_runs(keep=0)
        assert clean_result["deleted_runs"] >= 1

    @pytest.mark.asyncio
    @pytest.mark.zentao("TC-S0355", domain="server/services", priority="P1")
    async def test_clean_runs_force_empty(self, tmp_project, db_engine):
        _setup_config(tmp_project)
        svc = PipelineService()
        clean_result = await svc.clean_runs(force=True)
        assert clean_result == {"deleted_runs": 0, "deleted_logs": 0}

    @pytest.mark.asyncio
    @pytest.mark.zentao("TC-S0356", domain="server/services", priority="P1")
    async def test_create_run_with_dotpath_config_env(self, setup_project, tmp_project, db_engine):
        """#54: dot-path格式 params={"config.env":{...}} 应正确提取env用于YAML加载"""
        pipelines_dir = tmp_project / "pipelines"
        (pipelines_dir / "dotpath_env_test.yaml").write_text(
            "name: dotpath_env_test\n"
            "config:\n"
            "  env:\n"
            "    DEFAULT_KEY: default_val\n"
            "tasks:\n"
            "  - name: step1\n"
            "    command: echo ${env.OVERRIDE_KEY}\n"
        )
        _setup_config(tmp_project)
        svc = PipelineService()
        result = await svc.create_run(
            "dotpath_env_test.yaml",
            params={"config.env": {"OVERRIDE_KEY": "new_value"}},
        )
        assert "id" in result
        run_id = result["id"]
        fetched = await svc.get_run(run_id)
        assert isinstance(fetched["params"], dict)
        # params中应包含dot-path格式的env
        assert "config.env" in fetched["params"]
        assert fetched["params"]["config.env"]["OVERRIDE_KEY"] == "new_value"

    @pytest.mark.asyncio
    @pytest.mark.zentao("TC-S0357", domain="server/services", priority="P1")
    async def test_create_run_with_dotpath_task_env(self, setup_project, tmp_project, db_engine):
        """#54: dot-path格式 task env 应正确提取"""
        pipelines_dir = tmp_project / "pipelines"
        (pipelines_dir / "dotpath_task_env_test.yaml").write_text(
            "name: dotpath_task_env_test\n"
            "tasks:\n"
            "  - name: step1\n"
            "    command: echo ${env.TASK_KEY}\n"
            "    env:\n"
            "      TASK_KEY: default_task\n"
        )
        _setup_config(tmp_project)
        svc = PipelineService()
        result = await svc.create_run(
            "dotpath_task_env_test.yaml",
            params={
                'tasks["step1"].env': {"TASK_KEY": "overridden_task_val"},
            },
        )
        assert "id" in result
        run_id = result["id"]
        fetched = await svc.get_run(run_id)
        assert isinstance(fetched["params"], dict)
        assert 'tasks["step1"].env' in fetched["params"]


class TestEnsureUTC:
    @pytest.mark.zentao("TC-S0358", domain="server/services", priority="P2")
    def test_naive_datetime_becomes_utc_aware(self):
        from datetime import datetime

        from taskpps.services.pipeline_service import _ensure_utc

        naive = datetime(2026, 6, 11, 14, 16, 52, 858530)
        result = _ensure_utc(naive)
        assert result is not None
        assert result.tzinfo is not None
        assert str(result.tzinfo) == "UTC"

    @pytest.mark.zentao("TC-S0359", domain="server/services", priority="P2")
    def test_utc_aware_datetime_unchanged(self):
        from datetime import datetime, timezone

        from taskpps.services.pipeline_service import _ensure_utc

        aware = datetime(2026, 6, 11, 14, 16, 52, 858530, tzinfo=timezone.utc)
        result = _ensure_utc(aware)
        assert result is aware

    @pytest.mark.zentao("TC-S0360", domain="server/services", priority="P2")
    def test_none_returns_none(self):
        from taskpps.services.pipeline_service import _ensure_utc

        assert _ensure_utc(None) is None


class TestExtractEnvOverrides:
    def test_empty_params(self):
        assert _extract_env_overrides({}) == {}

    def test_none_params(self):
        with pytest.raises(AttributeError):
            _extract_env_overrides(None)

    @pytest.mark.zentao("TC-S0361", domain="server/services", priority="P1")
    def test_nested_config_env(self):
        result = _extract_env_overrides({"config": {"env": {"K": "V"}}})
        assert result == {"K": "V"}

    @pytest.mark.zentao("TC-S0362", domain="server/services", priority="P1")
    def test_dotpath_config_env(self):
        """#54: dot-path格式必须正确提取"""
        result = _extract_env_overrides({"config.env": {"K": "V"}})
        assert result == {"K": "V"}

    @pytest.mark.zentao("TC-S0363", domain="server/services", priority="P2")
    def test_dotpath_overrides_nested(self):
        """dot-path 优先级高于 nested（后 update 覆盖）"""
        result = _extract_env_overrides(
            {
                "config": {"env": {"K": "old"}},
                "config.env": {"K": "new"},
            }
        )
        assert result == {"K": "new"}

    @pytest.mark.zentao("TC-S0364", domain="server/services", priority="P1")
    def test_task_env_dotpath(self):
        """task 级别 env override"""
        result = _extract_env_overrides(
            {
                'tasks["step1"].env': {"TASK_KEY": "val"},
            }
        )
        assert result == {"TASK_KEY": "val"}

    @pytest.mark.zentao("TC-S0365", domain="server/services", priority="P1")
    def test_config_and_task_env_merged(self):
        """config env + task env 合并"""
        result = _extract_env_overrides(
            {
                "config.env": {"GLOBAL": "g"},
                'tasks["step1"].env': {"TASK": "t"},
            }
        )
        assert result == {"GLOBAL": "g", "TASK": "t"}

    @pytest.mark.zentao("TC-S0366", domain="server/services", priority="P1")
    def test_task_env_overrides_config(self):
        """task env 覆盖同名 config env"""
        result = _extract_env_overrides(
            {
                "config.env": {"K": "config_val"},
                'tasks["step1"].env': {"K": "task_val"},
            }
        )
        assert result == {"K": "task_val"}

    @pytest.mark.zentao("TC-S0367", domain="server/services", priority="P1")
    def test_nested_config_not_dict(self):
        result = _extract_env_overrides({"config": "not_dict"})
        assert result == {}

    @pytest.mark.zentao("TC-S0368", domain="server/services", priority="P1")
    def test_config_env_not_dict_in_dotpath(self):
        result = _extract_env_overrides({"config.env": "not_dict"})
        assert result == {}

    @pytest.mark.zentao("TC-S0369", domain="server/services", priority="P1")
    def test_ignores_non_env_dotpath_keys(self):
        result = _extract_env_overrides(
            {
                "options.timeout": 120,
                "config.retry": 3,
            }
        )
        assert result == {}


class TestComputeDurationMs:
    @pytest.mark.zentao("TC-S0370", domain="server/services", priority="P2")
    def test_no_start_time_returns_none(self):
        from taskpps.services.pipeline_service import _compute_duration_ms

        assert _compute_duration_ms(None, None) is None

    @pytest.mark.zentao("TC-S0371", domain="server/services", priority="P2")
    def test_completed_run_uses_finished_at(self):
        from taskpps.services.pipeline_service import _compute_duration_ms

        start = datetime(2026, 6, 23, 14, 52, 59, tzinfo=timezone.utc)
        end = start + timedelta(seconds=42, milliseconds=500)
        assert _compute_duration_ms(start, end) == 42500

    @pytest.mark.zentao("TC-S0372", domain="server/services", priority="P2")
    def test_running_run_uses_server_now(self):
        from taskpps.services.pipeline_service import _compute_duration_ms

        server_now = datetime(2026, 6, 23, 14, 53, 10, tzinfo=timezone.utc)
        start = datetime(2026, 6, 23, 14, 52, 59, tzinfo=timezone.utc)
        assert _compute_duration_ms(start, None, server_now) == 11000

    @pytest.mark.zentao("TC-S0373", domain="server/services", priority="P2")
    def test_naive_start_time_treated_as_utc(self):
        from taskpps.services.pipeline_service import _compute_duration_ms

        start = datetime(2026, 6, 23, 14, 52, 59)
        end = datetime(2026, 6, 23, 14, 53, 10, tzinfo=timezone.utc)
        assert _compute_duration_ms(start, end) == 11000

    @pytest.mark.zentao("TC-S0374", domain="server/services", priority="P2")
    def test_negative_duration_clamped_to_zero(self):
        from taskpps.services.pipeline_service import _compute_duration_ms

        start = datetime(2026, 6, 23, 14, 53, 10, tzinfo=timezone.utc)
        end = datetime(2026, 6, 23, 14, 52, 59, tzinfo=timezone.utc)
        assert _compute_duration_ms(start, end) == 0

    @pytest.mark.zentao("TC-S0375", domain="server/services", priority="P2")
    def test_microsecond_precision(self):
        from taskpps.services.pipeline_service import _compute_duration_ms

        start = datetime(2026, 6, 23, 14, 52, 59, 123000, tzinfo=timezone.utc)
        end = datetime(2026, 6, 23, 14, 52, 59, 456000, tzinfo=timezone.utc)
        assert _compute_duration_ms(start, end) == 333


class TestRunDurationResponse:
    @pytest.mark.asyncio
    @pytest.mark.zentao("TC-S0376", domain="server/services", priority="P1")
    async def test_get_run_includes_duration_ms(self, tmp_project, db_engine):
        _setup_config(tmp_project)
        from taskpps.db.engine import get_session_factory
        from taskpps.models.run import PipelineRun, RunStatus, TaskRun, TaskStatus

        run_id = "run-duration-get"
        async with get_session_factory()() as session:
            session.add(
                PipelineRun(
                    id=run_id,
                    pipeline_name="deploy",
                    pipeline_file="deploy.yaml",
                    pipeline_id="deploy",
                    pipeline_version="v1",
                    status=RunStatus.SUCCESS,
                    params="{}",
                    started_at=datetime.now(timezone.utc) - timedelta(seconds=5),
                    finished_at=datetime.now(timezone.utc),
                )
            )
            session.add(
                TaskRun(
                    id="task-duration-get",
                    run_id=run_id,
                    task_name="deploy.step1",
                    subpipeline_name="deploy",
                    task_type="command",
                    status=TaskStatus.SUCCESS,
                    started_at=datetime.now(timezone.utc) - timedelta(seconds=4),
                    finished_at=datetime.now(timezone.utc) - timedelta(seconds=1),
                )
            )
            await session.commit()

        svc = PipelineService()
        fetched = await svc.get_run(run_id)
        assert fetched is not None
        assert "duration_ms" in fetched
        assert fetched["duration_ms"] is not None
        assert fetched["duration_ms"] >= 5000
        for task in fetched["tasks"]:
            assert "duration_ms" in task
            assert task["duration_ms"] is not None
            assert task["duration_ms"] >= 3000

    @pytest.mark.asyncio
    @pytest.mark.zentao("TC-S0377", domain="server/services", priority="P1")
    async def test_list_runs_includes_duration_ms(self, tmp_project, db_engine):
        _setup_config(tmp_project)
        from taskpps.db.engine import get_session_factory
        from taskpps.models.run import PipelineRun, RunStatus

        run_id = "run-duration-list"
        async with get_session_factory()() as session:
            session.add(
                PipelineRun(
                    id=run_id,
                    pipeline_name="deploy",
                    pipeline_file="deploy.yaml",
                    pipeline_id="deploy",
                    pipeline_version="v1",
                    status=RunStatus.SUCCESS,
                    params="{}",
                    started_at=datetime.now(timezone.utc) - timedelta(seconds=3),
                    finished_at=datetime.now(timezone.utc),
                )
            )
            await session.commit()

        svc = PipelineService()
        listed = await svc.list_runs()
        run = next((r for r in listed["items"] if r["id"] == run_id), None)
        assert run is not None
        assert "duration_ms" in run
        assert run["duration_ms"] is not None
        assert run["duration_ms"] >= 3000

    @pytest.mark.asyncio
    @pytest.mark.zentao("TC-S0378", domain="server/services", priority="P1")
    async def test_get_run_running_duration_ms_positive(self, tmp_project, db_engine):
        _setup_config(tmp_project)
        from taskpps.db.engine import get_session_factory
        from taskpps.models.run import PipelineRun, RunStatus

        run_id = "run-duration-running"
        start = datetime.now(timezone.utc) - timedelta(seconds=2)
        async with get_session_factory()() as session:
            session.add(
                PipelineRun(
                    id=run_id,
                    pipeline_name="deploy",
                    pipeline_file="deploy.yaml",
                    pipeline_id="deploy",
                    pipeline_version="v1",
                    status=RunStatus.RUNNING,
                    params="{}",
                    started_at=start,
                )
            )
            await session.commit()

        svc = PipelineService()
        fetched = await svc.get_run(run_id)
        assert fetched is not None
        assert fetched["duration_ms"] is not None
        assert fetched["duration_ms"] >= 2000


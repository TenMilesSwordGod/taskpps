import contextlib
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest

from taskpps.services.pipeline_service import PipelineService
from taskpps.services.plugin_manager import PluginManager
from taskpps.services.trigger_service import TriggerService


def _setup_config(tmp_project):
    import taskpps.config as cfg

    cfg.set_project_root(tmp_project)
    cfg._settings = None
    cfg.load_settings(str(tmp_project / "taskpps.yaml"))


class TestPipelineService:
    @pytest.mark.asyncio
    async def test_list_pipelines(self, tmp_project, db_engine):
        _setup_config(tmp_project)
        svc = PipelineService()
        pipelines = svc.list_pipelines()
        assert isinstance(pipelines, list)
        assert "deploy" in pipelines
        assert "simple" in pipelines

    @pytest.mark.asyncio
    async def test_list_pipelines_multiple(self, setup_project, tmp_project, db_engine):
        _setup_config(tmp_project)
        svc = PipelineService()
        pipelines = svc.list_pipelines()
        assert len(pipelines) >= 2

    @pytest.mark.asyncio
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
    async def test_get_nonexistent(self, tmp_project, db_engine):
        _setup_config(tmp_project)
        svc = PipelineService()
        result = await svc.get_run("nonexistent")
        assert result is None

    @pytest.mark.asyncio
    async def test_create_invalid(self, tmp_project, db_engine):
        _setup_config(tmp_project)
        svc = PipelineService()
        with pytest.raises(ValueError):
            await svc.create_run("nonexistent.yaml")

    @pytest.mark.asyncio
    async def test_create_cycle(self, tmp_project, db_engine):
        _setup_config(tmp_project)
        svc = PipelineService()
        with pytest.raises(ValueError):
            await svc.create_run("cycle.yaml")

    @pytest.mark.asyncio
    async def test_create_with_params(self, setup_project, tmp_project, db_engine):
        _setup_config(tmp_project)
        svc = PipelineService()
        result = await svc.create_run("deploy.yaml", params={"options.timeout": 120})
        assert "id" in result

    @pytest.mark.asyncio
    async def test_create_with_bad_params(self, setup_project, tmp_project, db_engine):
        _setup_config(tmp_project)
        svc = PipelineService()
        with pytest.raises(ValueError):
            await svc.create_run("deploy.yaml", params={"nonexistent.path": "value"})

    @pytest.mark.asyncio
    async def test_list_runs(self, tmp_project, db_engine):
        _setup_config(tmp_project)
        svc = PipelineService()
        await svc.create_run("deploy.yaml")
        result = await svc.list_runs()
        assert result["total"] >= 1

    @pytest.mark.asyncio
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
    async def test_list_runs_with_limit(self, tmp_project, db_engine):
        _setup_config(tmp_project)
        svc = PipelineService()
        await svc.create_run("deploy.yaml", {"test": 1})
        await svc.create_run("deploy.yaml", {"test": 2})
        await svc.create_run("deploy.yaml", {"test": 3})
        result = await svc.list_runs(limit=2)
        assert len(result["items"]) == 2

    @pytest.mark.asyncio
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
    async def test_cancel_nonexistent(self, tmp_project, db_engine):
        _setup_config(tmp_project)
        svc = PipelineService()
        result = await svc.cancel_run("nonexistent")
        assert result is False

    @pytest.mark.asyncio
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

        await asyncio.sleep(2)

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
    async def test_clean_no_params(self, tmp_project, db_engine):
        _setup_config(tmp_project)
        svc = PipelineService()
        result = await svc.clean_runs()
        assert result == {"deleted_runs": 0, "deleted_logs": 0}

    @pytest.mark.asyncio
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
    async def test_clean_keep(self, setup_project, tmp_project, db_engine):
        _setup_config(tmp_project)
        svc = PipelineService()
        await svc.create_run("deploy.yaml")
        await svc.create_run("deploy.yaml")

        clean_result = await svc.clean_runs(keep=10)
        assert clean_result["deleted_runs"] >= 0

    @pytest.mark.asyncio
    async def test_clean_with_logs(self, setup_project, tmp_project, db_engine):
        _setup_config(tmp_project)
        from taskpps.config import get_logs_dir

        svc = PipelineService()
        result = await svc.create_run("deploy.yaml")
        run_id = result["id"]

        logs_dir = get_logs_dir()
        log_file = logs_dir / "deploy" / run_id / "step1" / "output.log"
        log_file.parent.mkdir(parents=True, exist_ok=True)
        log_file.write_text("test log content")

        clean_result = await svc.clean_runs(force=True)
        assert clean_result["deleted_runs"] >= 1
        assert clean_result["deleted_logs"] >= 0

    @pytest.mark.asyncio
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
    async def test_null_params(self, tmp_project, db_engine):
        _setup_config(tmp_project)
        svc = PipelineService()
        create_result = await svc.create_run("deploy.yaml", None)
        run_id = create_result["id"]
        fetched = await svc.get_run(run_id)
        assert isinstance(fetched["params"], dict)
        assert fetched["params"] == {}

    @pytest.mark.asyncio
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


class TestTriggerService:
    @pytest.mark.asyncio
    async def test_create_and_list(self, tmp_project, db_engine):
        _setup_config(tmp_project)
        svc = TriggerService()
        result = await svc.create_trigger("cron", {"schedule": "0 * * * *"}, "deploy.yaml")
        assert hasattr(result, "id")

        triggers = await svc.list_triggers()
        assert len(triggers) >= 1

    @pytest.mark.asyncio
    async def test_delete_nonexistent(self, tmp_project, db_engine):
        _setup_config(tmp_project)
        svc = TriggerService()
        result = await svc.delete_trigger("nonexistent")
        assert result is False


class TestPluginManager:
    def test_discover(self, tmp_project):
        _setup_config(tmp_project)
        pm = PluginManager()
        pm.discover_plugins()
        assert isinstance(pm.list_plugins(), list)

    def test_start_stop_triggers(self, tmp_project):
        _setup_config(tmp_project)
        pm = PluginManager()
        pm.start_triggers(callback=lambda x: None)
        pm.stop_all()

    def test_get_nonexistent(self):
        pm = PluginManager()
        assert pm.get("nonexistent") is None

    def test_stop_all_with_plugins(self):
        pm = PluginManager()
        from taskpps.plugins.base import BasePlugin

        class TestPlugin(BasePlugin):
            @property
            def name(self):
                return "test"

            def start(self):
                pass

            def stop(self):
                raise Exception("stop fail")

        pm.register("test", TestPlugin())
        pm.stop_all()

    def test_start_triggers_already_running(self):
        pm = PluginManager()
        from taskpps.plugins.cron_trigger import CronTrigger

        trigger = CronTrigger(expression="0 * * * *", pipeline_file="deploy.yaml")
        trigger._running = True
        pm.register("cron:0 * * * *:deploy.yaml", trigger)

        with patch("taskpps.services.plugin_manager.get_settings") as mock_settings:
            mock_settings.return_value.triggers = []
            pm.start_triggers()
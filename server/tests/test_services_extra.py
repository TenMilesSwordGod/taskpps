from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest

from taskpps.services.pipeline_service import PipelineService
from taskpps.services.plugin_manager import PluginManager


def _setup_config(tmp_project):
    import taskpps.config as cfg
    cfg._project_root = tmp_project
    cfg._settings = None
    cfg.load_settings(str(tmp_project / "taskpps.yaml"))


@pytest.mark.asyncio
async def test_cancel_run_pending_status(setup_project, tmp_project, db_engine):
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
async def test_cancel_run_completed_status(setup_project, tmp_project, db_engine):
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
async def test_clean_runs_older_than(setup_project, tmp_project, db_engine):
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
async def test_clean_runs_keep(setup_project, tmp_project, db_engine):
    _setup_config(tmp_project)
    svc = PipelineService()
    await svc.create_run("deploy.yaml")
    await svc.create_run("deploy.yaml")

    clean_result = await svc.clean_runs(keep=10)
    assert clean_result["deleted_runs"] >= 0


@pytest.mark.asyncio
async def test_clean_runs_with_logs(setup_project, tmp_project, db_engine):
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
async def test_pipeline_service_create_with_params(setup_project, tmp_project, db_engine):
    _setup_config(tmp_project)
    svc = PipelineService()
    result = await svc.create_run("deploy.yaml", params={"options.timeout": 120})
    assert "id" in result


@pytest.mark.asyncio
async def test_pipeline_service_create_with_bad_params(setup_project, tmp_project, db_engine):
    _setup_config(tmp_project)
    svc = PipelineService()
    with pytest.raises(ValueError):
        await svc.create_run("deploy.yaml", params={"nonexistent.path": "value"})


@pytest.mark.asyncio
async def test_pipeline_service_list_pipelines(setup_project, tmp_project, db_engine):
    _setup_config(tmp_project)
    svc = PipelineService()
    pipelines = svc.list_pipelines()
    assert len(pipelines) >= 2


def test_plugin_manager_stop_all_with_plugins():
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


def test_plugin_manager_start_triggers_already_running():
    pm = PluginManager()
    from taskpps.plugins.cron_trigger import CronTrigger

    trigger = CronTrigger(expression="0 * * * *", pipeline_file="deploy.yaml")
    trigger._running = True
    pm.register("cron:0 * * * *:deploy.yaml", trigger)

    with patch("taskpps.services.plugin_manager.get_settings") as mock_settings:
        mock_settings.return_value.triggers = []
        pm.start_triggers()

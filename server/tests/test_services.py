import pytest
from taskpps.services.pipeline_service import PipelineService
from taskpps.services.trigger_service import TriggerService
from taskpps.services.plugin_manager import PluginManager
from taskpps.db.engine import get_session_factory
from taskpps.db.repository import RunRepository, TaskRunRepository


@pytest.mark.asyncio
async def test_pipeline_service_list_pipelines(setup_project, tmp_project, db_engine):
    svc = PipelineService()
    pipelines = svc.list_pipelines()
    assert isinstance(pipelines, list)
    assert "deploy" in pipelines
    assert "simple" in pipelines


@pytest.mark.asyncio
async def test_pipeline_service_create_and_get(setup_project, tmp_project, db_engine):
    svc = PipelineService()
    result = await svc.create_run("deploy.yaml")
    assert "id" in result
    run_id = result["id"]

    fetched = await svc.get_run(run_id)
    assert fetched is not None
    assert fetched["id"] == run_id
    assert fetched["pipeline_name"] == "deploy"


@pytest.mark.asyncio
async def test_pipeline_service_get_nonexistent(setup_project, tmp_project, db_engine):
    svc = PipelineService()
    result = await svc.get_run("nonexistent")
    assert result is None


@pytest.mark.asyncio
async def test_pipeline_service_create_invalid(setup_project, tmp_project, db_engine):
    svc = PipelineService()
    with pytest.raises(ValueError):
        await svc.create_run("nonexistent.yaml")


@pytest.mark.asyncio
async def test_pipeline_service_create_cycle(setup_project, tmp_project, db_engine):
    svc = PipelineService()
    with pytest.raises(ValueError, match="Cycle"):
        await svc.create_run("cycle.yaml")


@pytest.mark.asyncio
async def test_pipeline_service_list_runs(setup_project, tmp_project, db_engine):
    svc = PipelineService()
    await svc.create_run("deploy.yaml")
    runs = await svc.list_runs()
    assert len(runs) >= 1


@pytest.mark.asyncio
async def test_pipeline_service_list_runs_filter(setup_project, tmp_project, db_engine):
    svc = PipelineService()
    await svc.create_run("deploy.yaml")
    runs = await svc.list_runs(pipeline="deploy")
    assert len(runs) >= 1
    for r in runs:
        assert r["pipeline_name"] == "deploy"


@pytest.mark.asyncio
async def test_pipeline_service_cancel_nonexistent(setup_project, tmp_project, db_engine):
    svc = PipelineService()
    result = await svc.cancel_run("nonexistent")
    assert result is False


@pytest.mark.asyncio
async def test_pipeline_service_clean_no_params(setup_project, tmp_project, db_engine):
    svc = PipelineService()
    result = await svc.clean_runs()
    assert result == {"deleted_runs": 0, "deleted_logs": 0}


@pytest.mark.asyncio
async def test_trigger_service_create_and_list(setup_project, tmp_project, db_engine):
    svc = TriggerService()
    result = await svc.create_trigger("cron", {"schedule": "0 * * * *"}, "deploy.yaml")
    assert "id" in result

    triggers = await svc.list_triggers()
    assert len(triggers) >= 1


@pytest.mark.asyncio
async def test_trigger_service_delete_nonexistent(setup_project, tmp_project, db_engine):
    svc = TriggerService()
    result = await svc.delete_trigger("nonexistent")
    assert result is False


def test_plugin_manager_discover(setup_project, tmp_project):
    pm = PluginManager()
    pm.discover_plugins()
    assert isinstance(pm.list_plugins(), list)


def test_plugin_manager_start_stop_triggers(setup_project, tmp_project):
    pm = PluginManager()
    pm.start_triggers(callback=lambda x: None)
    pm.stop_all()


def test_plugin_manager_get_nonexistent():
    pm = PluginManager()
    assert pm.get("nonexistent") is None

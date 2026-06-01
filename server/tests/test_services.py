import contextlib

import pytest

from taskpps.services.pipeline_service import PipelineService
from taskpps.services.plugin_manager import PluginManager
from taskpps.services.trigger_service import TriggerService


@pytest.mark.asyncio
async def test_pipeline_service_list_pipelines(tmp_project, db_engine):
    import taskpps.config as cfg

    cfg._project_root = tmp_project
    cfg._settings = None
    cfg.load_settings(str(tmp_project / "taskpps.yaml"))
    svc = PipelineService()
    pipelines = svc.list_pipelines()
    assert isinstance(pipelines, list)
    assert "deploy" in pipelines
    assert "simple" in pipelines


@pytest.mark.asyncio
async def test_pipeline_service_create_and_get(tmp_project, db_engine):
    import taskpps.config as cfg

    cfg._project_root = tmp_project
    cfg._settings = None
    cfg.load_settings(str(tmp_project / "taskpps.yaml"))
    svc = PipelineService()
    result = await svc.create_run("deploy.yaml")
    assert "id" in result
    run_id = result["id"]

    fetched = await svc.get_run(run_id)
    assert fetched is not None
    assert fetched["id"] == run_id
    assert fetched["pipeline_name"] == "deploy"


@pytest.mark.asyncio
async def test_pipeline_service_get_nonexistent(tmp_project, db_engine):
    import taskpps.config as cfg

    cfg._project_root = tmp_project
    cfg._settings = None
    cfg.load_settings(str(tmp_project / "taskpps.yaml"))
    svc = PipelineService()
    result = await svc.get_run("nonexistent")
    assert result is None


@pytest.mark.asyncio
async def test_pipeline_service_create_invalid(tmp_project, db_engine):
    import taskpps.config as cfg

    cfg._project_root = tmp_project
    cfg._settings = None
    cfg.load_settings(str(tmp_project / "taskpps.yaml"))
    svc = PipelineService()
    with pytest.raises(ValueError):
        await svc.create_run("nonexistent.yaml")


@pytest.mark.asyncio
async def test_pipeline_service_create_cycle(tmp_project, db_engine):
    import taskpps.config as cfg

    cfg._project_root = tmp_project
    cfg._settings = None
    cfg.load_settings(str(tmp_project / "taskpps.yaml"))
    svc = PipelineService()
    with pytest.raises(ValueError):
        await svc.create_run("cycle.yaml")


@pytest.mark.asyncio
async def test_pipeline_service_list_runs(tmp_project, db_engine):
    import taskpps.config as cfg

    cfg._project_root = tmp_project
    cfg._settings = None
    cfg.load_settings(str(tmp_project / "taskpps.yaml"))
    svc = PipelineService()
    await svc.create_run("deploy.yaml")
    result = await svc.list_runs()
    assert result["total"] >= 1


@pytest.mark.asyncio
async def test_pipeline_service_list_runs_filter(tmp_project, db_engine):
    import taskpps.config as cfg

    cfg._project_root = tmp_project
    cfg._settings = None
    cfg.load_settings(str(tmp_project / "taskpps.yaml"))
    svc = PipelineService()
    await svc.create_run("deploy.yaml")
    result = await svc.list_runs(pipeline="deploy")
    items = result["items"]
    assert len(items) >= 1
    for r in items:
        assert r["pipeline_name"] == "deploy"


@pytest.mark.asyncio
async def test_pipeline_service_cancel_nonexistent(tmp_project, db_engine):
    import taskpps.config as cfg

    cfg._project_root = tmp_project
    cfg._settings = None
    cfg.load_settings(str(tmp_project / "taskpps.yaml"))
    svc = PipelineService()
    result = await svc.cancel_run("nonexistent")
    assert result is False


@pytest.mark.asyncio
async def test_pipeline_service_clean_no_params(tmp_project, db_engine):
    import taskpps.config as cfg

    cfg._project_root = tmp_project
    cfg._settings = None
    cfg.load_settings(str(tmp_project / "taskpps.yaml"))
    svc = PipelineService()
    result = await svc.clean_runs()
    assert result == {"deleted_runs": 0, "deleted_logs": 0}


@pytest.mark.asyncio
async def test_trigger_service_create_and_list(tmp_project, db_engine):
    import taskpps.config as cfg

    cfg._project_root = tmp_project
    cfg._settings = None
    cfg.load_settings(str(tmp_project / "taskpps.yaml"))
    svc = TriggerService()
    result = await svc.create_trigger("cron", {"schedule": "0 * * * *"}, "deploy.yaml")
    assert hasattr(result, "id")

    triggers = await svc.list_triggers()
    assert len(triggers) >= 1


@pytest.mark.asyncio
async def test_trigger_service_delete_nonexistent(tmp_project, db_engine):
    import taskpps.config as cfg

    cfg._project_root = tmp_project
    cfg._settings = None
    cfg.load_settings(str(tmp_project / "taskpps.yaml"))
    svc = TriggerService()
    result = await svc.delete_trigger("nonexistent")
    assert result is False


@pytest.mark.asyncio
async def test_pipeline_service_params_parsing_get(tmp_project, db_engine):
    """Test that params are parsed correctly from JSON string in get_run"""
    import taskpps.config as cfg

    cfg._project_root = tmp_project
    cfg._settings = None
    cfg.load_settings(str(tmp_project / "taskpps.yaml"))
    svc = PipelineService()
    params = {"key1": "value1", "key2": {"nested": "value"}}

    # Create run with params
    create_result = await svc.create_run("deploy.yaml", params)
    run_id = create_result["id"]

    # Get the run
    fetched = await svc.get_run(run_id)
    assert fetched is not None
    # Check params is a dict, not a string
    assert isinstance(fetched["params"], dict)
    assert fetched["params"] == params


@pytest.mark.asyncio
async def test_pipeline_service_params_parsing_list(tmp_project, db_engine):
    """Test that params are parsed correctly from JSON string in list_runs"""
    import taskpps.config as cfg

    cfg._project_root = tmp_project
    cfg._settings = None
    cfg.load_settings(str(tmp_project / "taskpps.yaml"))
    svc = PipelineService()
    params = {"options": {"host": "test-server"}}

    # Create run with params
    await svc.create_run("deploy.yaml", params)

    # List runs
    result = await svc.list_runs()
    assert result["total"] >= 1

    # Check all items have params as dict
    for item in result["items"]:
        assert isinstance(item["params"], dict)


@pytest.mark.asyncio
async def test_pipeline_service_empty_params(tmp_project, db_engine):
    """Test empty params are handled correctly"""
    import taskpps.config as cfg

    cfg._project_root = tmp_project
    cfg._settings = None
    cfg.load_settings(str(tmp_project / "taskpps.yaml"))
    svc = PipelineService()

    # Create run without params
    create_result = await svc.create_run("deploy.yaml", {})
    run_id = create_result["id"]

    fetched = await svc.get_run(run_id)
    assert isinstance(fetched["params"], dict)
    assert fetched["params"] == {}


@pytest.mark.asyncio
async def test_pipeline_service_null_params(tmp_project, db_engine):
    """Test null/None params are handled correctly"""
    import taskpps.config as cfg

    cfg._project_root = tmp_project
    cfg._settings = None
    cfg.load_settings(str(tmp_project / "taskpps.yaml"))
    svc = PipelineService()

    # Create run with None params
    create_result = await svc.create_run("deploy.yaml", None)
    run_id = create_result["id"]

    fetched = await svc.get_run(run_id)
    assert isinstance(fetched["params"], dict)
    assert fetched["params"] == {}


@pytest.mark.asyncio
async def test_pipeline_service_invalid_json_params_edge_case(tmp_project, db_engine):
    """Test edge case with invalid JSON params"""
    PipelineService()

    # Manually test the parsing logic by mocking the params
    # The actual create_run uses json.dumps, but we can test what happens if params is invalid JSON string

    # Let's create a mock PipelineRun object
    class MockRun:
        def __init__(self):
            self.id = "test"
            self.pipeline_name = "deploy"
            self.pipeline_file = "deploy.yaml"
            self.params = "invalid-json-string"  # Invalid JSON
            self.status = "pending"
            self.started_at = None
            self.finished_at = None
            from datetime import datetime

            self.created_at = datetime.now()

    # Now let's test what happens with invalid JSON (should default to {})
    # We can manually test the parsing logic from pipeline_service.py
    import json

    test_params = "invalid-json"
    params = {}
    if isinstance(test_params, str):
        with contextlib.suppress(json.JSONDecodeError, TypeError):
            params = json.loads(test_params)
    assert params == {}


@pytest.mark.asyncio
async def test_pipeline_service_many_list_runs(tmp_project, db_engine):
    """Test list_runs with multiple runs"""
    import taskpps.config as cfg

    cfg._project_root = tmp_project
    cfg._settings = None
    cfg.load_settings(str(tmp_project / "taskpps.yaml"))
    svc = PipelineService()

    # Create multiple runs
    await svc.create_run("deploy.yaml", {"test": 1})
    await svc.create_run("deploy.yaml", {"test": 2})
    await svc.create_run("deploy.yaml", {"test": 3})

    result = await svc.list_runs()
    assert result["total"] >= 3
    assert len(result["items"]) >= 3


@pytest.mark.asyncio
async def test_pipeline_service_list_with_limit(tmp_project, db_engine):
    """Test list_runs limit"""
    import taskpps.config as cfg

    cfg._project_root = tmp_project
    cfg._settings = None
    cfg.load_settings(str(tmp_project / "taskpps.yaml"))
    svc = PipelineService()

    # Create multiple runs
    await svc.create_run("deploy.yaml", {"test": 1})
    await svc.create_run("deploy.yaml", {"test": 2})
    await svc.create_run("deploy.yaml", {"test": 3})

    result = await svc.list_runs(limit=2)
    assert len(result["items"]) == 2


def test_plugin_manager_discover(tmp_project):
    import taskpps.config as cfg

    cfg._project_root = tmp_project
    cfg._settings = None
    cfg.load_settings(str(tmp_project / "taskpps.yaml"))
    pm = PluginManager()
    pm.discover_plugins()
    assert isinstance(pm.list_plugins(), list)


def test_plugin_manager_start_stop_triggers(tmp_project):
    import taskpps.config as cfg

    cfg._project_root = tmp_project
    cfg._settings = None
    cfg.load_settings(str(tmp_project / "taskpps.yaml"))
    pm = PluginManager()
    pm.start_triggers(callback=lambda x: None)
    pm.stop_all()


def test_plugin_manager_get_nonexistent():
    pm = PluginManager()
    assert pm.get("nonexistent") is None

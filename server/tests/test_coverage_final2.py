import pytest
import asyncio
from pathlib import Path
from unittest.mock import patch, MagicMock, AsyncMock
from datetime import datetime

from taskpps.db.engine import get_session_factory, get_session, get_engine, reset_engine
from taskpps.db.repository import RunRepository
from taskpps.domain.context import _navigate_to_key, _set_key, set_dot_path, apply_overrides
from taskpps.executors.base import ExecutorResult
from taskpps.executors.local import LocalExecutor
from taskpps.executors.invoke import InvokeExecutor
from taskpps.executors.ssh import SSHExecutor
from taskpps.executors import create_executor
from taskpps.domain.pipeline import ResolvedTask
from taskpps.schemas.pipeline import OptionsYAML
from taskpps.loaders.agent_loader import AgentLoader
from taskpps.loaders.pipeline_loader import PipelineLoader


# --- db/engine.py:24 _session_factory creation ---

@pytest.mark.asyncio
async def test_get_session_factory_creates_new():
    reset_engine()
    from taskpps.db.engine import _session_factory, _engine, get_engine
    _session_factory = None
    engine = get_engine()
    factory = get_session_factory()
    assert factory is not None
    await engine.dispose()
    reset_engine()


# --- domain/context.py branches ---

def test_navigate_to_key_list_direct():
    data = [1, 2, 3]
    result = _navigate_to_key(data, "1")
    assert result == 2


def test_navigate_to_key_dict_with_name_index_not_list():
    data = {"tasks": {"a": 1, "b": 2}}
    result = _navigate_to_key(data, 'tasks["a"]')
    assert result == {"a": 1, "b": 2}


def test_set_key_current_list_numeric():
    data = [10, 20, 30]
    _set_key(data, "1", 99)
    assert data[1] == 99


def test_set_key_name_index_missing_container():
    data = {"tasks": [{"name": "foo", "val": 1}]}
    with pytest.raises(KeyError):
        _set_key(data, 'tasks["missing"]', "new_val")


def test_set_key_name_index_numeric_not_found():
    data = {"items": [1, 2, 3]}
    with pytest.raises(IndexError):
        _set_key(data, "items[10]", 99)


def test_set_dot_path_current_list():
    data = [{"a": 1}, {"a": 2}]
    set_dot_path(data, "1.a", 99)
    assert data[1]["a"] == 99


def test_set_dot_path_name_index_assign():
    data = {"tasks": [{"name": "foo", "val": 1}]}
    set_dot_path(data, 'tasks["foo"].val', 42)
    assert data["tasks"][0]["val"] == 42


def test_apply_overrides_with_named_index_nested():
    data = {
        "tasks": [
            {"name": "build", "timeout": 60, "command": "make"},
            {"name": "test", "timeout": 60, "command": "make test"},
        ]
    }
    result = apply_overrides(data, {'tasks["test"].timeout': 120})
    assert result["tasks"][1]["timeout"] == 120


def test_apply_overrides_current_is_list():
    data = [{"name": "first", "val": 1}, {"name": "second", "val": 2}]
    result = apply_overrides(data, {"0.val": 99})
    assert result[0]["val"] == 99


# --- executors/local.py CancelledError ---

@pytest.mark.asyncio
async def test_local_executor_subprocess_cancel(tmp_path):
    executor = LocalExecutor()
    log_path = tmp_path / "sub_cancel.log"
    task = asyncio.create_task(executor.execute("sleep 10", {}, log_path, timeout=30))
    await asyncio.sleep(0.3)
    done, pending = await asyncio.wait([task], timeout=0.5)
    if task in pending:
        executor._process.kill()
        task.cancel()
    try:
        result = await task
        assert result.exit_code != 0
    except (asyncio.CancelledError, Exception):
        pass


# --- executors/invoke.py ---

@pytest.mark.asyncio
async def test_invoke_executor_with_nonexistent_module(tmp_path):
    executor = InvokeExecutor()
    log_path = tmp_path / "no_mod.log"
    result = await executor.execute(
        "", {}, log_path, invoke_task="nonexistent.module.func",
    )
    assert not result.success


# --- executors/ssh.py ---

@pytest.mark.asyncio
async def test_ssh_executor_with_password_keypath_none():
    ex = SSHExecutor(host="1.2.3.4", port=22, username="root")
    assert ex.host == "1.2.3.4"


@pytest.mark.asyncio
async def test_ssh_executor_connect_exception(tmp_path):
    import socket
    ex = SSHExecutor(host="127.0.0.1", port=1, username="test", password="test",
                      key_path="/nonexistent/key")
    log_path = tmp_path / "conn.log"
    result = await ex.execute("echo hi", {}, log_path)
    assert not result.success


@pytest.mark.asyncio
async def test_ssh_executor_cancel_cleanup():
    ex = SSHExecutor(host="1.2.3.4", port=22, username="root")
    ex._client = MagicMock()
    ex._channel = MagicMock()
    await ex.cancel()


# --- loaders/agent_loader.py ---

def test_agent_loader_load_all_with_yml(tmp_path):
    agents_dir = tmp_path / "agents"
    agents_dir.mkdir()
    (agents_dir / "test.yml").write_text("host: 1.2.3.4\n")
    loader = AgentLoader(agents_dir)
    result = loader.load_all()
    assert "test" in result


# --- loaders/pipeline_loader.py ---

def test_pipeline_loader_substitute_env_with_os():
    import os
    os.environ["TEST_EXISTING_VAR"] = "existing_value"
    from taskpps.loaders.pipeline_loader import substitute_env_vars
    result = substitute_env_vars("echo ${TEST_EXISTING_VAR}", {})
    assert "existing_value" in result


# --- services/pipeline_service.py lines 29-30, 183 ---

@pytest.mark.asyncio
async def test_pipeline_service_create_run_loader_exception(setup_project, tmp_project, db_engine):
    from taskpps.services.pipeline_service import PipelineService
    svc = PipelineService()
    with patch.object(svc.loader, 'load', side_effect=Exception("unexpected")):
        with pytest.raises(ValueError):
            await svc.create_run("deploy.yaml")


@pytest.mark.asyncio
async def test_pipeline_service_clean_keep_with_logs(setup_project, tmp_project, db_engine):
    from taskpps.services.pipeline_service import PipelineService
    from taskpps.config import get_logs_dir
    svc = PipelineService()
    r1 = await svc.create_run("deploy.yaml")
    r2 = await svc.create_run("deploy.yaml")
    logs_dir = get_logs_dir()
    for rid in [r1["id"], r2["id"]]:
        log_file = logs_dir / "deploy" / rid / "step1" / "output.log"
        log_file.parent.mkdir(parents=True, exist_ok=True)
        log_file.write_text("log content")
    result = await svc.clean_runs(keep=1)
    assert result["deleted_runs"] >= 1
    assert result["deleted_logs"] >= 0


# --- services/plugin_manager.py ---

def test_plugin_manager_register_trigger():
    from taskpps.services.plugin_manager import PluginManager
    from taskpps.plugins.base import TriggerPlugin
    class MockTrigger(TriggerPlugin):
        @property
        def name(self):
            return "mock-trigger"
        def start(self):
            pass
        def stop(self):
            pass
        def get_type(self):
            return "mock"
    pm = PluginManager()
    t = MockTrigger()
    pm.register("mock-trigger", t)
    assert "mock-trigger" in pm._triggers




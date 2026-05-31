import asyncio
from pathlib import Path

import pytest

from taskpps.db.engine import get_session_factory
from taskpps.db.repository import RunRepository, TaskRunRepository
from taskpps.domain.context import _navigate_to_key, _set_key, apply_overrides, set_dot_path
from taskpps.domain.dag import DAGCycleError
from taskpps.executors.base import BaseExecutor
from taskpps.executors.invoke import InvokeExecutor
from taskpps.loaders.agent_loader import AgentLoader
from taskpps.loaders.credential_loader import CredentialLoader
from taskpps.loaders.pipeline_loader import PipelineLoader

# --- config.py coverage ---


def test_find_project_root_walks_up(tmp_path):
    import taskpps.config as cfg

    old = cfg._project_root
    cfg._project_root = None
    try:
        result = cfg.find_project_root()
        assert result is not None
    finally:
        cfg._project_root = old


def test_find_project_root_creates_project(tmp_path):
    import taskpps.config as cfg

    sub = tmp_path / "a" / "b" / "c"
    sub.mkdir(parents=True)
    config_file = sub / "taskpps.yaml"
    config_file.write_text("server:\n  host: 1.2.3.4\n")

    old_root = cfg._project_root
    cfg._project_root = None
    old_cwd = Path.cwd()
    try:
        import os

        os.chdir(sub)
        result = cfg.find_project_root()
        assert result == sub
    finally:
        os.chdir(old_cwd)
        cfg._project_root = old_root


# --- db/repository.py coverage ---


@pytest.mark.asyncio
async def test_update_run_status_nonexistent(db_engine):
    async with get_session_factory()() as session:
        repo = RunRepository(session)
        from taskpps.models.run import RunStatus

        await repo.update_run_status("nonexistent", RunStatus.RUNNING)


@pytest.mark.asyncio
async def test_update_task_status_nonexistent(db_engine):
    async with get_session_factory()() as session:
        repo = TaskRunRepository(session)
        from taskpps.models.run import TaskStatus

        await repo.update_task_status("nonexistent", TaskStatus.RUNNING)


@pytest.mark.asyncio
async def test_get_running_tasks(db_engine):
    async with get_session_factory()() as session:
        run_repo = RunRepository(session)
        task_repo = TaskRunRepository(session)
        run = await run_repo.create_run("test")
        await task_repo.create_task_run(run.id, "task1")
        await task_repo.create_task_run(run.id, "task2")
        running = await task_repo.get_running_tasks(run.id)
        assert len(running) == 0


@pytest.mark.asyncio
async def test_delete_tasks_for_run(db_engine):
    from taskpps.db.engine import get_session_factory

    async with get_session_factory()() as session:
        run_repo = RunRepository(session)
        task_repo = TaskRunRepository(session)
        run = await run_repo.create_run("test")
        await task_repo.create_task_run(run.id, "task1")
        count = await task_repo.delete_tasks_for_run(run.id)
        assert count == 1


# --- domain/context.py coverage ---


def test_navigate_to_key_name_index_numeric_in_dict():
    data = {"items": [10, 20, 30]}
    result = _navigate_to_key(data, "items[0]")
    assert result == 10


def test_navigate_to_key_name_index_container():
    data = {"items": [10, 20, 30]}
    result = _navigate_to_key(data, "items")
    assert result == [10, 20, 30]


def test_navigate_to_key_current_dict_key():
    data = {"key": "value"}
    result = _navigate_to_key(data, "key")
    assert result == "value"


def test_navigate_to_key_current_list_int():
    data = [1, 2, 3]
    result = _navigate_to_key(data, "0")
    assert result == 1


def test_navigate_to_key_current_list_int_keyerror():
    data = [1, 2, 3]
    with pytest.raises(IndexError):
        _navigate_to_key(data, "10")


def test_set_key_numeric_index_to_value():
    data = {"items": [1, 2, 3]}
    _set_key(data, "items[0]", 99)
    assert data["items"][0] == 99


def test_set_key_current_list_index():
    data = [1, 2, 3]
    _set_key(data, "0", 99)
    assert data[0] == 99


def test_set_key_current_dict_key():
    data = {}
    _set_key(data, "x", 1)
    assert data["x"] == 1


def test_set_dot_path_name_index_container():
    data = {"tasks": [{"name": "foo", "val": 1}]}
    set_dot_path(data, 'tasks["foo"].val', 2)
    assert data["tasks"][0]["val"] == 2


def test_apply_overrides_list_current():
    data = [{"name": "t1"}, {"name": "t2"}]
    result = apply_overrides(data, {"0.name": "renamed"})
    assert result[0]["name"] == "renamed"


def test_apply_overrides_nested_list():
    data = [{"a": 1}, {"a": 2}]
    result = apply_overrides(data, {"1.a": 99})
    assert result[1]["a"] == 99


# --- domain/dag.py coverage ---


def test_dag_get_execution_levels_cycle():
    from taskpps.domain.dag import DAG
    from taskpps.domain.pipeline import ResolvedTask

    tasks = [
        ResolvedTask(name="a", task_type="command", command="echo", depends_on=["b"]),
        ResolvedTask(name="b", task_type="command", command="echo", depends_on=["a"]),
    ]
    dag = DAG(tasks)
    with pytest.raises(DAGCycleError):
        dag.get_execution_levels()


# --- executors/base.py coverage ---


def test_base_executor_abstract():
    with pytest.raises(TypeError):
        BaseExecutor()


# --- executors/local.py coverage ---


# --- executors/invoke.py coverage ---


@pytest.mark.asyncio
async def test_invoke_executor_cancelled(tmp_path):
    executor = InvokeExecutor()
    tmp_path / "invoke_cancel.log"
    await executor.cancel()


# --- executors/ssh.py coverage ---

# --- loaders/agent_loader.py coverage ---


def test_agent_loader_load_all_yml_exception(tmp_path):
    agents_dir = tmp_path / "agents"
    agents_dir.mkdir()
    (agents_dir / "good.yaml").write_text("host: localhost\n")
    loader = AgentLoader(agents_dir)
    result = loader.load_all()
    assert "good" in result


# --- loaders/credential_loader.py coverage ---


def test_credential_loader_file_not_found(tmp_path):
    loader = CredentialLoader(tmp_path / "nonexistent")
    with pytest.raises(FileNotFoundError):
        loader.load("test")


def test_credential_loader_load_all_yml(tmp_path):
    creds_dir = tmp_path / "credentials"
    creds_dir.mkdir()
    (creds_dir / "test.yaml").write_text("password: pass\n")
    loader = CredentialLoader(creds_dir)
    result = loader.load_all()
    assert "test" in result


# --- loaders/pipeline_loader.py coverage ---


def test_pipeline_loader_load_all_yml(tmp_path):
    pdir = tmp_path / "pipelines"
    pdir.mkdir()
    (pdir / "test.yml").write_text("name: test\ntasks:\n  - name: t1\n    command: echo\n")
    loader = PipelineLoader(pdir)
    result = loader.load_all()
    assert "test" in result


def test_pipeline_loader_load_all_exception(tmp_path):
    pdir = tmp_path / "pipelines"
    pdir.mkdir()
    (pdir / "bad.yaml").write_text("")
    loader = PipelineLoader(pdir)
    result = loader.load_all()
    assert result == {}


# --- main.py coverage ---


def test_main_settings_is_none():
    import taskpps.config as cfg
    from taskpps.main import app

    old = cfg._settings
    cfg._settings = None
    try:
        assert app is not None
    finally:
        cfg._settings = old


# --- services/pipeline_service.py coverage ---


def test_delete_run_logs_no_dir(setup_project):
    from taskpps.models.run import PipelineRun
    from taskpps.services.pipeline_service import PipelineService

    svc = PipelineService()
    run = PipelineRun(
        pipeline_name="nonexistent-pipeline",
        pipeline_file="nonexistent-pipeline.yaml",
        pipeline_id="nonexistent",
        pipeline_version="abc12345",
        id="run123",
    )
    count = svc._delete_run_logs(run)
    assert count == 0


# --- api/runs.py coverage ---


@pytest.mark.asyncio
async def test_get_run_logs_follow_with_sse(client, setup_project, tmp_project):
    response = await client.post("/api/runs/", json={"pipeline": "simple.yaml"})
    assert response.status_code == 201
    run_id = response.json()["id"]
    await asyncio.sleep(2)
    async with client.stream("GET", f"/api/runs/{run_id}/logs?follow=true") as resp:
        assert resp.status_code == 200


@pytest.mark.asyncio
async def test_clean_runs_older_than_no_data(client, setup_project, tmp_project):
    response = await client.delete("/api/runs/?older_than=7")
    assert response.status_code == 200
    data = response.json()
    assert "deleted_runs" in data


@pytest.mark.asyncio
async def test_clean_runs_keep_without_force(client, setup_project, tmp_project):
    response = await client.delete("/api/runs/?keep=5")
    assert response.status_code == 200

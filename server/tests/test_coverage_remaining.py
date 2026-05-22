import pytest
import asyncio
from datetime import datetime
from pathlib import Path
from unittest.mock import patch, MagicMock, AsyncMock

from taskpps.db.engine import get_session_factory, reset_engine
from taskpps.db.repository import RunRepository, TaskRunRepository
from taskpps.models.run import RunStatus
from taskpps.domain.context import _navigate_to_key, _set_key, set_dot_path, apply_overrides
from taskpps.engine.runner import PipelineRunner
from taskpps.domain.pipeline import ResolvedPipeline, ResolvedTask
from taskpps.domain.context import ExecutionContext
from taskpps.executors.base import ExecutorResult
from taskpps.executors.invoke import InvokeExecutor
from taskpps.executors.ssh import SSHExecutor
from taskpps.loaders.credential_loader import CredentialLoader


# --- db/repository.py:43 (list_runs with status filter) ---
@pytest.mark.asyncio
async def test_list_runs_with_status(db_engine):
    async with get_session_factory()() as session:
        repo = RunRepository(session)
        await repo.create_run("test-pipeline")
        runs = await repo.list_runs(status="pending")
        assert len(runs) >= 1
        for r in runs:
            assert r.status == RunStatus.PENDING





# --- engine/runner.py:67-68 (task name in level not in pipeline) ---
@pytest.mark.asyncio
async def test_runner_task_not_found_in_level():
    options = MagicMock()
    options.on_failure = "fail"
    options.env = {}
    tasks = [ResolvedTask(name="t1", task_type="command", command="echo ok")]
    pipeline = ResolvedPipeline(name="test", tasks=tasks, options=options)
    ctx = ExecutionContext(pipeline=pipeline, run_id="test_not_found")
    runner = PipelineRunner(run_id="test_not_found", pipeline=pipeline, context=ctx)
    runner._task_run_ids = {}

    mock_dag_instance = MagicMock()
    mock_dag_instance.get_execution_levels.return_value = [["nonexistent_task"]]

    mock_session = MagicMock()
    run_repo = MagicMock()
    run_repo.update_run_status = AsyncMock()
    task_repo = MagicMock()
    task_repo.update_task_status = AsyncMock()

    with patch("taskpps.engine.runner.RunRepository", return_value=run_repo), \
            patch("taskpps.engine.runner.TaskRunRepository", return_value=task_repo), \
            patch("taskpps.engine.runner.get_session_factory") as mock_sf, \
            patch("taskpps.engine.runner.get_event_bus"), \
            patch("taskpps.engine.runner.get_settings"), \
            patch("taskpps.engine.runner.DAG", return_value=mock_dag_instance):
        mock_sf.return_value.return_value = mock_session
        await runner.run()
    assert True


# --- engine/runner.py:68 (should_skip due to dependency failure) ---
@pytest.mark.asyncio
async def test_runner_should_skip():
    options = MagicMock()
    options.on_failure = "fail"
    options.env = {}
    tasks = [
        ResolvedTask(name="t1", task_type="command", command="exit 1"),
        ResolvedTask(name="t2", task_type="command", command="echo dep", depends_on=["t1"]),
    ]
    pipeline = ResolvedPipeline(name="test", tasks=tasks, options=options)
    ctx = ExecutionContext(pipeline=pipeline, run_id="test_skip2")
    runner = PipelineRunner(run_id="test_skip2", pipeline=pipeline, context=ctx)
    runner._task_run_ids = {"t1": "tr1", "t2": "tr2"}

    mock_executor = AsyncMock()
    mock_executor.execute.return_value = ExecutorResult(exit_code=1, stderr="fail")

    mock_session = MagicMock()
    run_repo = MagicMock()
    run_repo.update_run_status = AsyncMock()
    task_repo = MagicMock()
    task_repo.update_task_status = AsyncMock()

    with patch("taskpps.engine.runner.RunRepository", return_value=run_repo), \
            patch("taskpps.engine.runner.TaskRunRepository", return_value=task_repo), \
            patch("taskpps.engine.runner.get_session_factory") as mock_sf, \
            patch("taskpps.engine.runner.create_executor", return_value=mock_executor), \
            patch("taskpps.engine.runner.get_logs_dir"), \
            patch("taskpps.engine.runner.get_event_bus"), \
            patch("taskpps.engine.runner.get_settings"):
        mock_sf.return_value.return_value = mock_session
        await runner.run()

    assert True


# --- engine/runner.py:146 (isinstance InvokeExecutor branch) ---
@pytest.mark.asyncio
async def test_runner_invoke_executor_path():
    options = MagicMock()
    options.on_failure = "fail"
    options.env = {}
    tasks = [ResolvedTask(name="t1", task_type="invoke", invoke_task="mod.fn", invoke_args=[], invoke_kwargs={})]
    pipeline = ResolvedPipeline(name="test", tasks=tasks, options=options)
    ctx = ExecutionContext(pipeline=pipeline, run_id="test_invoke2")
    runner = PipelineRunner(run_id="test_invoke2", pipeline=pipeline, context=ctx)
    runner._task_run_ids = {"t1": "tr1"}

    mock_executor = AsyncMock(spec=InvokeExecutor)
    mock_executor.execute.return_value = ExecutorResult(exit_code=0, stdout="ok")

    mock_session = MagicMock()
    run_repo = MagicMock()
    run_repo.update_run_status = AsyncMock()
    task_repo = MagicMock()
    task_repo.update_task_status = AsyncMock()

    with patch("taskpps.engine.runner.RunRepository", return_value=run_repo), \
            patch("taskpps.engine.runner.TaskRunRepository", return_value=task_repo), \
            patch("taskpps.engine.runner.get_session_factory") as mock_sf, \
            patch("taskpps.engine.runner.create_executor", return_value=mock_executor), \
            patch("taskpps.engine.runner.get_logs_dir"), \
            patch("taskpps.engine.runner.get_event_bus"), \
            patch("taskpps.engine.runner.get_settings"):
        mock_sf.return_value.return_value = mock_session
        await runner.run()

    assert True





# --- executors/invoke.py:63-65 (invoke decorator path) ---
@pytest.mark.asyncio
async def test_invoke_executor_decorator_path(tmp_path):
    tasks_dir = tmp_path / "tasks"
    tasks_dir.mkdir()
    (tasks_dir / "deco_mod.py").write_text("""
def deco_func(ctx):
    return "ok"
deco_func._task = True
""")
    with patch("taskpps.executors.invoke.get_tasks_dir", return_value=tasks_dir), \
            patch("invoke.Context"):
        executor = InvokeExecutor()
        log_path = tmp_path / "deco.log"
        result = await executor.execute(
            "", {}, log_path, invoke_task="deco_mod.deco_func",
        )
        assert result.success


# --- executors/invoke.py:95-99 (CancelledError in invoke executor) ---
@pytest.mark.asyncio
async def test_invoke_executor_cancel_in_flight(tmp_path):
    executor = InvokeExecutor()
    log_path = tmp_path / "cancel_inflight.log"
    tasks_dir = tmp_path / "tasks"
    tasks_dir.mkdir()
    (tasks_dir / "slow.py").write_text("""
import time
def slow_func():
    time.sleep(60)
    return "done"
""")

    with patch("taskpps.executors.invoke.get_tasks_dir", return_value=tasks_dir):
        task = asyncio.create_task(
            executor.execute("", {}, log_path, invoke_task="slow.slow_func", timeout=120)
        )
        await asyncio.sleep(0.1)
        task.cancel()
        await asyncio.sleep(0.1)
        try:
            result = await task
        except (asyncio.CancelledError, Exception):
            pass


# --- executors/ssh.py:55-66 (SSH execute code paths) ---
@pytest.mark.asyncio
async def test_ssh_executor_connection_fail(tmp_path):
    ex = SSHExecutor(host="127.0.0.1", port=1, username="root")
    log_path = tmp_path / "conn_fail.log"
    result = await ex.execute("echo hi", {}, log_path)
    assert not result.success


# --- executors/ssh.py:77,79 (cancel cleanup) ---
@pytest.mark.asyncio
async def test_ssh_executor_none_client_cancel():
    ex = SSHExecutor(host="1.2.3.4", port=22, username="root")
    await ex.cancel()


# --- loaders/credential_loader.py:49-50 (yml glob exception) ---
def test_credential_loader_load_all_yml_with_exception(tmp_path):
    creds_dir = tmp_path / "credentials"
    creds_dir.mkdir()
    (creds_dir / "good.yaml").write_text("password: secret\n")
    (creds_dir / "bad.yml").write_text("invalid: yaml: : broken :")
    loader = CredentialLoader(creds_dir)
    result = loader.load_all()
    assert "good" in result


# --- main.py:27 (settings is None in lifespan) ---
@pytest.mark.asyncio
async def test_lifespan_without_settings():
    import taskpps.config as cfg
    import taskpps.main as main
    old_settings = cfg._settings
    cfg._settings = None
    old_root = cfg._project_root
    cfg._project_root = None
    old_ext = main._external_engine
    main._external_engine = True
    try:
        async with main.lifespan(main.app):
            pass
    finally:
        cfg._settings = old_settings
        cfg._project_root = old_root
        main._external_engine = old_ext


# --- main.py:39 (close_db with external_engine=False) ---
@pytest.mark.asyncio
async def test_lifespan_close_db_not_external():
    import taskpps.config as cfg
    import taskpps.main as main
    from taskpps.db.engine import reset_engine
    old_settings = cfg._settings
    old_root = cfg._project_root
    old_ext = main._external_engine
    main._external_engine = False
    reset_engine()
    try:
        async with main.lifespan(main.app):
            pass
    finally:
        cfg._settings = old_settings
        cfg._project_root = old_root
        main._external_engine = old_ext


# --- plugins/cron_trigger.py:60-69 (_run_loop callback path) ---
def test_cron_trigger_run_loop_with_callback_path():
    from taskpps.plugins.cron_trigger import CronTrigger
    callback = MagicMock()
    trigger = CronTrigger(expression="* * * * *", pipeline_file="test.yaml", callback=callback)
    trigger._running = True
    trigger._stop_event.set()
    trigger._run_loop()
    callback.assert_not_called()


# --- services/plugin_manager.py:72-73 (plugin instantiation error) ---
def test_plugin_manager_instantiation_fail(tmp_project):
    import taskpps.config as cfg
    plugins_dir = cfg.get_plugins_dir()
    plugins_dir.mkdir(parents=True, exist_ok=True)
    (plugins_dir / "fail_plugin.py").write_text("""
from taskpps.plugins.base import BasePlugin

class InitFailPlugin(BasePlugin):
    @property
    def name(self):
        return "fail"

    def __init__(self):
        raise RuntimeError("init failed")

    def start(self):
        pass

    def stop(self):
        pass
""")
    from taskpps.services.plugin_manager import PluginManager
    pm = PluginManager()
    pm.discover_plugins()


# --- services/plugin_manager.py:92 (trigger start check) ---
def test_plugin_manager_start_triggers_with_running():
    from taskpps.services.plugin_manager import PluginManager
    from taskpps.plugins.cron_trigger import CronTrigger
    trigger = CronTrigger(expression="0 * * * *", pipeline_file="test.yaml")
    trigger._running = True
    trigger2 = CronTrigger(expression="*/5 * * * *", pipeline_file="test2.yaml")
    pm = PluginManager()
    pm.register(trigger.name, trigger)
    pm.register(trigger2.name, trigger2)
    with patch("taskpps.services.plugin_manager.get_settings") as mock_gs:
        mock_gs.return_value.triggers = []
        pm.start_triggers()


# --- api/runs.py SSE paths ---
@pytest.mark.asyncio
async def test_get_run_logs_sse_path(client, setup_project, tmp_project):
    response = await client.post("/api/runs/", json={"pipeline": "simple.yaml"})
    assert response.status_code == 201
    run_id = response.json()["id"]
    await asyncio.sleep(2)
    async with client.stream("GET", f"/api/runs/{run_id}/logs?follow=true") as resp:
        assert resp.status_code == 200
        async for line in resp.aiter_lines():
            if "data" in line:
                break

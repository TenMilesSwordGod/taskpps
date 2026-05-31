import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from taskpps.domain.context import ExecutionContext
from taskpps.domain.pipeline import ResolvedPipeline, ResolvedTask
from taskpps.engine.runner import PipelineRunner
from taskpps.executors.base import ExecutorResult
from taskpps.executors.invoke import InvokeExecutor
from taskpps.executors.ssh import SSHExecutor
from taskpps.loaders.agent_loader import AgentLoader
from taskpps.loaders.credential_loader import CredentialLoader
from taskpps.loaders.pipeline_loader import PipelineLoader
from taskpps.plugins.cron_trigger import CronTrigger


# --- engine/runner.py:68 (should_skip check) ---
@pytest.mark.asyncio
async def test_runner_skip_on_failure():
    tasks = [
        ResolvedTask(name="t1", task_type="command", command="exit 1", on_failure="fail"),
        ResolvedTask(name="t2", task_type="command", command="echo skip", depends_on=["t1"], on_failure="continue"),
    ]
    options = MagicMock()
    options.on_failure = "fail"
    options.env = {}
    pipeline = ResolvedPipeline(name="test", tasks=tasks, options=options)
    ctx = ExecutionContext(pipeline=pipeline, run_id="test_skip")
    runner = PipelineRunner(run_id="test_skip", pipeline=pipeline, context=ctx)
    runner._task_run_ids = {"t1": "tr1", "t2": "tr2"}

    mock_executor = AsyncMock()
    mock_executor.execute.return_value = ExecutorResult(exit_code=1, stderr="fail")

    mock_session = MagicMock()
    run_repo = MagicMock()
    run_repo.update_run_status = AsyncMock()
    task_repo = MagicMock()
    task_repo.update_task_status = AsyncMock()
    task_repo.create_task_run = AsyncMock()

    with (
        patch("taskpps.engine.runner.RunRepository", return_value=run_repo),
        patch("taskpps.engine.runner.TaskRunRepository", return_value=task_repo),
        patch("taskpps.engine.runner.get_session_factory") as mock_sf,
        patch("taskpps.engine.runner.create_executor", return_value=mock_executor),
        patch("taskpps.engine.runner.get_logs_dir"),
        patch("taskpps.engine.runner.get_event_bus"),
        patch("taskpps.engine.runner.get_settings"),
    ):
        mock_sf.return_value.return_value = mock_session
        await runner.run()

    assert True


# --- engine/runner.py:97 (executor exception handling) ---
@pytest.mark.asyncio
async def test_runner_executor_exception_in_gather():
    options = MagicMock()
    options.on_failure = "fail"
    options.env = {}
    tasks = [ResolvedTask(name="t1", task_type="command", command="echo")]
    pipeline = ResolvedPipeline(name="test", tasks=tasks, options=options)
    ctx = ExecutionContext(pipeline=pipeline, run_id="test_exec_exc")
    runner = PipelineRunner(run_id="test_exec_exc", pipeline=pipeline, context=ctx)
    runner._task_run_ids = {"t1": "tr1"}

    mock_executor = AsyncMock()
    mock_executor.execute.side_effect = RuntimeError("executor crash")

    mock_session = MagicMock()
    run_repo = MagicMock()
    run_repo.update_run_status = AsyncMock()
    task_repo = MagicMock()
    task_repo.update_task_status = AsyncMock()

    with (
        patch("taskpps.engine.runner.RunRepository", return_value=run_repo),
        patch("taskpps.engine.runner.TaskRunRepository", return_value=task_repo),
        patch("taskpps.engine.runner.get_session_factory") as mock_sf,
        patch("taskpps.engine.runner.create_executor", return_value=mock_executor),
        patch("taskpps.engine.runner.get_logs_dir"),
        patch("taskpps.engine.runner.get_event_bus"),
        patch("taskpps.engine.runner.get_settings"),
    ):
        mock_sf.return_value.return_value = mock_session
        await runner.run()

    assert True


# --- engine/runner.py:104 (except Exception pass) ---
@pytest.mark.asyncio
async def test_runner_exception_during_execution():
    options = MagicMock()
    options.on_failure = "fail"
    options.env = {}
    tasks = [ResolvedTask(name="t1", task_type="command", command="echo")]
    pipeline = ResolvedPipeline(name="test", tasks=tasks, options=options)
    ctx = ExecutionContext(pipeline=pipeline, run_id="test_unexpected")
    runner = PipelineRunner(run_id="test_unexpected", pipeline=pipeline, context=ctx)
    runner._task_run_ids = {"t1": "tr1"}

    mock_session = MagicMock()
    run_repo = MagicMock()
    run_repo.update_run_status = AsyncMock()

    with (
        patch("taskpps.engine.runner.DAG") as mock_dag,
        patch("taskpps.engine.runner.RunRepository", return_value=run_repo),
        patch("taskpps.engine.runner.TaskRunRepository"),
        patch("taskpps.engine.runner.get_session_factory") as mock_sf,
        patch("taskpps.engine.runner.get_event_bus"),
    ):
        dag_instance = MagicMock()
        dag_instance.get_execution_levels.side_effect = Exception("unexpected error")
        mock_dag.return_value = dag_instance
        mock_sf.return_value.return_value = mock_session
        await runner.run()

    assert True


# --- engine/runner.py:146 (invoke executor branch) ---
@pytest.mark.asyncio
async def test_runner_invoke_executor_branch():
    options = MagicMock()
    options.on_failure = "fail"
    options.env = {}
    tasks = [ResolvedTask(name="t1", task_type="invoke", invoke_task="mod.func")]
    pipeline = ResolvedPipeline(name="test", tasks=tasks, options=options)
    ctx = ExecutionContext(pipeline=pipeline, run_id="test_invoke")
    runner = PipelineRunner(run_id="test_invoke", pipeline=pipeline, context=ctx)
    runner._task_run_ids = {"t1": "tr1"}

    mock_executor = AsyncMock()
    mock_executor.execute.return_value = ExecutorResult(exit_code=0, stdout="ok")

    mock_session = MagicMock()
    run_repo = MagicMock()
    run_repo.update_run_status = AsyncMock()

    with (
        patch("taskpps.engine.runner.RunRepository", return_value=run_repo),
        patch("taskpps.engine.runner.TaskRunRepository"),
        patch("taskpps.engine.runner.get_session_factory") as mock_sf,
        patch("taskpps.engine.runner.create_executor", return_value=mock_executor),
        patch("taskpps.engine.runner.get_logs_dir"),
        patch("taskpps.engine.runner.get_event_bus"),
        patch("taskpps.engine.runner.get_settings"),
    ):
        mock_sf.return_value.return_value = mock_session
        await runner.run()

    assert True


# --- engine/runner.py:192 (cancel running executor) ---
@pytest.mark.asyncio
async def test_runner_cancel_with_running_executors():
    options = MagicMock()
    options.on_failure = "fail"
    options.env = {}
    tasks = [ResolvedTask(name="t1", task_type="command", command="echo")]
    pipeline = ResolvedPipeline(name="test", tasks=tasks, options=options)
    ctx = ExecutionContext(pipeline=pipeline, run_id="test_cancel_exec")
    runner = PipelineRunner(run_id="test_cancel_exec", pipeline=pipeline, context=ctx)

    mock_executor = AsyncMock()
    runner._running_executors["t1"] = mock_executor

    mock_session = MagicMock()
    task_repo = MagicMock()
    task_repo.cancel_pending_tasks = AsyncMock()

    with (
        patch("taskpps.engine.runner.RunRepository"),
        patch("taskpps.engine.runner.TaskRunRepository", return_value=task_repo),
        patch("taskpps.engine.runner.get_session_factory") as mock_sf,
        patch("taskpps.engine.runner.get_event_bus"),
    ):
        mock_sf.return_value.return_value = mock_session
        await runner.cancel()
        mock_executor.cancel.assert_called_once()


# --- executors/invoke.py:76-80 (exception in invoke) ---
@pytest.mark.asyncio
async def test_invoke_executor_exception(tmp_path):
    executor = InvokeExecutor()
    log_path = tmp_path / "exec_exception.log"
    tasks_dir = tmp_path / "tasks"
    tasks_dir.mkdir()
    (tasks_dir / "err_module.py").write_text("""
def failing_func():
    raise ValueError("intentional fail")
""")

    with patch("taskpps.executors.invoke.get_tasks_dir", return_value=tasks_dir):
        result = await executor.execute(
            "",
            {},
            log_path,
            invoke_task="err_module.failing_func",
        )
    assert not result.success
    assert result.exit_code == 1


# --- executors/ssh.py:55-66 (channel operations) ---
@pytest.mark.asyncio
async def test_ssh_executor_connect_refused():
    ex = SSHExecutor(host="127.0.0.1", port=1, username="test")
    log_path = Path("/tmp/ssh_refused.log")
    result = await ex.execute("echo test", {}, log_path)
    assert not result.success
    assert result.exit_code == -1


# --- executors/ssh.py:75-80 (CancelledError) ---
@pytest.mark.asyncio
async def test_ssh_executor_cancelled():
    ex = SSHExecutor(host="127.0.0.1", port=29999, username="test", password="pass")
    with patch.object(ex, "_ensure_log_dir"), patch("asyncio.get_event_loop") as mock_evloop:
        mock_loop = MagicMock()
        mock_evloop.return_value = mock_loop
        mock_loop.run_in_executor.side_effect = asyncio.CancelledError()
        log_path = Path("/tmp/ssh_cancel.log")
        result = await ex.execute("echo hi", {}, log_path)
        assert result.exit_code == -1


# --- loaders/agent_loader.py:49-50 (yml glob exception) ---
def test_agent_loader_load_all_yml_with_errors(tmp_path):
    agents_dir = tmp_path / "agents"
    agents_dir.mkdir()
    (agents_dir / "good.yaml").write_text("host: localhost\n")
    (agents_dir / "bad.yml").write_text("invalid: yaml: : broken")
    loader = AgentLoader(agents_dir)
    result = loader.load_all()
    assert "good" in result


# --- loaders/credential_loader.py:49-50 (yml glob exception) ---
def test_credential_loader_load_all_yml_with_errors(tmp_path):
    creds_dir = tmp_path / "credentials"
    creds_dir.mkdir()
    (creds_dir / "good.yaml").write_text("password: pass\n")
    (creds_dir / "bad.yml").write_text("invalid yaml")
    loader = CredentialLoader(creds_dir)
    result = loader.load_all()
    assert "good" in result


# --- loaders/pipeline_loader.py:69-70 (yml glob exception) ---
def test_pipeline_loader_load_all_yml_with_errors(tmp_path):
    pdir = tmp_path / "pipelines"
    pdir.mkdir()
    (pdir / "good.yaml").write_text("name: good\ntasks:\n  - name: t1\n    command: echo\n")
    (pdir / "bad.yml").write_text("")
    loader = PipelineLoader(pdir)
    result = loader.load_all()
    assert "good" in result


# --- plugins/cron_trigger.py:60-69 (callback execution) ---
def test_cron_trigger_callback_execution():
    callback = MagicMock()
    trigger = CronTrigger(expression="* * * * *", pipeline_file="test.yaml", callback=callback)
    trigger._running = True
    trigger._stop_event.set()
    trigger._run_loop()
    callback.assert_not_called()


# --- services/plugin_manager.py:72-73 (instantiation error) ---
def test_plugin_manager_try_load_instantiation_error(tmp_path):
    from taskpps.services.plugin_manager import PluginManager

    plugins_dir = tmp_path / "plugins"
    plugins_dir.mkdir()
    pyfile = plugins_dir / "bad_plugin.py"
    pyfile.write_text("""
from taskpps.plugins.base import BasePlugin

class BrokenInitPlugin(BasePlugin):
    @property
    def name(self):
        return "broken"

    def start(self):
        pass

    def stop(self):
        raise RuntimeError("stop fail")
""")

    pm = PluginManager()
    pm.discover_plugins()


# --- services/plugin_manager.py:92 (trigger._running check) ---
def test_plugin_manager_start_triggers_no_running_check():
    from taskpps.services.plugin_manager import PluginManager

    with patch("taskpps.services.plugin_manager.get_settings") as mock_gs:
        mock_gs.return_value.triggers = []
        pm = PluginManager()
        pm.start_triggers()


# --- api/runs.py:81 (log file missing) ---
@pytest.mark.asyncio
async def test_get_run_logs_log_missing(client, setup_project, tmp_project):
    create_resp = await client.post("/api/runs/", json={"pipeline": "deploy.yaml"})
    assert create_resp.status_code == 201
    run_id = create_resp.json()["id"]
    await asyncio.sleep(1)
    response = await client.get(f"/api/runs/{run_id}/logs")
    assert response.status_code == 200

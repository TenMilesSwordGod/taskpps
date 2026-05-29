import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from datetime import datetime

from taskpps.domain.pipeline import ResolvedPipeline, ResolvedTask
from taskpps.domain.context import ExecutionContext
from taskpps.engine.runner import PipelineRunner, get_active_runner
from taskpps.domain.dag import DAGCycleError
from taskpps.executors.base import ExecutorResult
from taskpps.schemas.pipeline import OptionsYAML


def make_pipeline(name="test", tasks=None, options=None):
    if tasks is None:
        tasks = [ResolvedTask(name="t1", task_type="command", command="echo hi")]
    return ResolvedPipeline(name=name, tasks=tasks, options=options or OptionsYAML())


@pytest.fixture
def mock_repos():
    run_repo = MagicMock()
    run_repo.update_run_status = AsyncMock()
    run_repo.get_run = AsyncMock()
    run_repo.create_run = AsyncMock()
    task_repo = MagicMock()
    task_repo.update_task_status = AsyncMock()
    task_repo.create_task_run = AsyncMock()
    task_repo.list_task_runs = AsyncMock()
    task_repo.cancel_pending_tasks = AsyncMock()
    task_repo.get_running_tasks = AsyncMock()
    task_repo.get_task_run = AsyncMock()
    return run_repo, task_repo


@pytest.fixture
def mock_session_factory(mock_repos):
    run_repo, task_repo = mock_repos
    mock_session = MagicMock()

    def repo_side_effect(cls):
        if cls.__name__ == "RunRepository":
            return run_repo
        return task_repo

    with patch("taskpps.engine.runner.RunRepository") as mock_rr, \
            patch("taskpps.engine.runner.TaskRunRepository") as mock_tr:
        mock_rr.side_effect = lambda s: run_repo
        mock_tr.side_effect = lambda s: task_repo

        mock_sf = MagicMock()
        mock_sf.return_value = mock_session

        with patch("taskpps.engine.runner.get_session_factory", return_value=mock_sf):
            yield run_repo, task_repo


@pytest.mark.asyncio
async def test_runner_run_unknown_dependency(mock_session_factory):
    run_repo, task_repo = mock_session_factory
    tasks = [
        ResolvedTask(name="a", task_type="command", command="echo", depends_on=["unknown"]),
    ]
    pipeline = make_pipeline(tasks=tasks)
    ctx = ExecutionContext(pipeline=pipeline, run_id="test1")
    runner = PipelineRunner(run_id="test1", pipeline=pipeline, context=ctx)

    await runner.run()
    calls = [c[0][1] for c in run_repo.update_run_status.call_args_list]
    assert "failed" in calls


@pytest.mark.asyncio
async def test_runner_run_success(mock_session_factory):
    run_repo, task_repo = mock_session_factory
    tasks = [ResolvedTask(name="t1", task_type="command", command="echo hi")]
    pipeline = make_pipeline(tasks=tasks)
    ctx = ExecutionContext(pipeline=pipeline, run_id="test2")
    runner = PipelineRunner(run_id="test2", pipeline=pipeline, context=ctx)
    runner._task_run_ids = {"t1": "tr1"}

    mock_executor = AsyncMock()
    mock_executor.execute.return_value = ExecutorResult(exit_code=0, stdout="ok")

    with patch("taskpps.engine.runner.create_executor", return_value=mock_executor):
        with patch("taskpps.engine.runner.get_logs_dir"):
            with patch("taskpps.engine.runner.get_event_bus"):
                await runner.run()

    assert run_repo.update_run_status.call_count >= 1
    assert run_repo.update_run_status.call_args[0][1] == "success"


@pytest.mark.asyncio
async def test_runner_cancel(mock_session_factory):
    run_repo, task_repo = mock_session_factory
    tasks = [ResolvedTask(name="t1", task_type="command", command="echo hi")]
    pipeline = make_pipeline(tasks=tasks)
    ctx = ExecutionContext(pipeline=pipeline, run_id="test3")
    runner = PipelineRunner(run_id="test3", pipeline=pipeline, context=ctx)

    with patch("taskpps.engine.runner.get_event_bus"):
        await runner.cancel()

    assert runner._cancelled is True


@pytest.mark.asyncio
async def test_runner_run_with_executor_exception(mock_session_factory):
    run_repo, task_repo = mock_session_factory
    tasks = [ResolvedTask(name="t1", task_type="command", command="echo hi")]
    pipeline = make_pipeline(tasks=tasks)
    ctx = ExecutionContext(pipeline=pipeline, run_id="test4")
    runner = PipelineRunner(run_id="test4", pipeline=pipeline, context=ctx)
    runner._task_run_ids = {"t1": "tr1"}

    mock_executor = AsyncMock()
    mock_executor.execute.side_effect = Exception("unexpected error")

    with patch("taskpps.engine.runner.create_executor", return_value=mock_executor):
        with patch("taskpps.engine.runner.get_logs_dir"):
            with patch("taskpps.engine.runner.get_event_bus"):
                await runner.run()

    assert run_repo.update_run_status.call_count >= 1


@pytest.mark.asyncio
async def test_runner_run_with_dependency_failure(mock_session_factory):
    run_repo, task_repo = mock_session_factory
    tasks = [
        ResolvedTask(name="t1", task_type="command", command="exit 1"),
        ResolvedTask(name="t2", task_type="command", command="echo should not run", depends_on=["t1"]),
    ]
    pipeline = make_pipeline(tasks=tasks)
    ctx = ExecutionContext(pipeline=pipeline, run_id="test5")
    runner = PipelineRunner(run_id="test5", pipeline=pipeline, context=ctx)
    runner._task_run_ids = {"t1": "tr1", "t2": "tr2"}

    mock_executor = AsyncMock()
    mock_executor.execute.return_value = ExecutorResult(exit_code=1, stderr="failed")

    with patch("taskpps.engine.runner.create_executor", return_value=mock_executor):
        with patch("taskpps.engine.runner.get_logs_dir"):
            with patch("taskpps.engine.runner.get_event_bus"):
                await runner.run()

    assert run_repo.update_run_status.call_args[0][1] in ("failed", "partial")


@pytest.mark.asyncio
async def test_runner_run_skip_dependency_failed(mock_session_factory):
    run_repo, task_repo = mock_session_factory
    tasks = [
        ResolvedTask(name="t1", task_type="command", command="exit 1"),
        ResolvedTask(name="t2", task_type="command", command="echo dep", depends_on=["t1"]),
    ]
    pipeline = make_pipeline(tasks=tasks)
    ctx = ExecutionContext(pipeline=pipeline, run_id="test6")
    runner = PipelineRunner(run_id="test6", pipeline=pipeline, context=ctx)
    runner._task_run_ids = {"t1": "tr1", "t2": "tr2"}

    mock_executor = AsyncMock()
    mock_executor.execute.return_value = ExecutorResult(exit_code=1, stderr="failed")

    with patch("taskpps.engine.runner.create_executor", return_value=mock_executor):
        with patch("taskpps.engine.runner.get_logs_dir"):
            with patch("taskpps.engine.runner.get_event_bus"):
                with patch("taskpps.engine.runner.get_settings"):
                    await runner.run()

    assert task_repo.update_task_status.call_count >= 1


@pytest.mark.asyncio
async def test_runner_run_cancelled_during_execution(mock_session_factory):
    run_repo, task_repo = mock_session_factory
    tasks = [
        ResolvedTask(name="t1", task_type="command", command="echo hi"),
        ResolvedTask(name="t2", task_type="command", command="echo there", depends_on=["t1"]),
    ]
    pipeline = make_pipeline(tasks=tasks)
    ctx = ExecutionContext(pipeline=pipeline, run_id="test7")
    runner = PipelineRunner(run_id="test7", pipeline=pipeline, context=ctx)
    runner._cancelled = True

    with patch("taskpps.engine.runner.get_event_bus"):
        await runner.run()

    assert run_repo.update_run_status.call_args[0][1] == "cancelled"


def test_get_active_runner_returns_none():
    assert get_active_runner("nonexistent") is None


@pytest.mark.asyncio
async def test_runner_unexpected_error_init(mock_session_factory):
    """Runner 应初始化 _unexpected_error 为 False"""
    tasks = [ResolvedTask(name="t1", task_type="command", command="echo hi")]
    pipeline = make_pipeline(tasks=tasks)
    ctx = ExecutionContext(pipeline=pipeline, run_id="test8")
    runner = PipelineRunner(run_id="test8", pipeline=pipeline, context=ctx)
    assert runner._unexpected_error is False


@pytest.mark.asyncio
async def test_runner_unexpected_error_sets_failed_status(mock_session_factory):
    """内层 try 意外异常应标记 run 为 FAILED 而非 SUCCESS"""
    run_repo, task_repo = mock_session_factory
    tasks = [ResolvedTask(name="t1", task_type="command", command="echo hi")]
    pipeline = make_pipeline(tasks=tasks)
    ctx = ExecutionContext(pipeline=pipeline, run_id="test9")
    runner = PipelineRunner(run_id="test9", pipeline=pipeline, context=ctx)
    runner._task_run_ids = {"t1": "tr1"}

    with patch("taskpps.domain.dag.DAG.get_execution_levels", side_effect=RuntimeError("dag crash")), \
         patch("taskpps.engine.runner.get_event_bus"), \
         patch("taskpps.engine.runner.get_logs_dir"), \
         patch("taskpps.engine.runner.get_settings"):
        await runner.run()

    assert runner._unexpected_error is True
    assert run_repo.update_run_status.call_args[0][1] == "failed"

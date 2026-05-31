import pytest

from taskpps.domain.pipeline import ResolvedTask
from taskpps.executors import create_executor
from taskpps.executors.base import ExecutorResult
from taskpps.executors.invoke import InvokeExecutor
from taskpps.executors.local import LocalExecutor


def test_executor_result_success():
    r = ExecutorResult(exit_code=0, stdout="ok")
    assert r.success is True


def test_executor_result_failure():
    r = ExecutorResult(exit_code=1, stderr="err")
    assert r.success is False


@pytest.mark.asyncio
async def test_local_executor(tmp_path):
    executor = LocalExecutor()
    log_path = tmp_path / "test.log"
    result = await executor.execute("echo hello world", {}, log_path)
    assert result.success
    assert "hello world" in result.stdout
    assert log_path.exists()


@pytest.mark.asyncio
async def test_local_executor_failure(tmp_path):
    executor = LocalExecutor()
    log_path = tmp_path / "test.log"
    result = await executor.execute("exit 42", {}, log_path)
    assert not result.success
    assert result.exit_code == 42


@pytest.mark.asyncio
async def test_local_executor_env(tmp_path):
    executor = LocalExecutor()
    log_path = tmp_path / "test.log"
    result = await executor.execute("echo $MY_VAR", {"MY_VAR": "test_value"}, log_path)
    assert result.success
    assert "test_value" in result.stdout


@pytest.mark.asyncio
async def test_local_executor_timeout(tmp_path):
    executor = LocalExecutor()
    log_path = tmp_path / "test.log"
    result = await executor.execute("sleep 10", {}, log_path, timeout=1)
    assert not result.success
    assert result.exit_code == -1


@pytest.mark.asyncio
async def test_invoke_executor(tmp_path, setup_project, tmp_project):
    executor = InvokeExecutor()
    log_path = tmp_path / "test.log"
    result = await executor.execute(
        "",
        {},
        log_path,
        invoke_task="sample_tasks.hello",
    )
    assert result.success


@pytest.mark.asyncio
async def test_invoke_executor_invalid(tmp_path):
    executor = InvokeExecutor()
    log_path = tmp_path / "test.log"
    result = await executor.execute(
        "",
        {},
        log_path,
        invoke_task="nonexistent.func",
    )
    assert not result.success


def test_create_executor_local():
    task = ResolvedTask(name="t", task_type="command", command="echo")
    executor = create_executor(task)
    assert isinstance(executor, LocalExecutor)


def test_create_executor_invoke():
    task = ResolvedTask(name="t", task_type="invoke", invoke_task="mod.fn")
    executor = create_executor(task)
    assert isinstance(executor, InvokeExecutor)

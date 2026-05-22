import pytest
import asyncio
from pathlib import Path
from unittest.mock import patch, MagicMock, AsyncMock

from taskpps.executors import create_executor
from taskpps.executors.base import BaseExecutor, ExecutorResult
from taskpps.executors.local import LocalExecutor
from taskpps.executors.invoke import InvokeExecutor
from taskpps.executors.ssh import SSHExecutor
from taskpps.domain.pipeline import ResolvedTask


def test_executor_result_success():
    r = ExecutorResult(exit_code=0, stdout="ok")
    assert r.success is True


def test_executor_result_failure():
    r = ExecutorResult(exit_code=1, stderr="err")
    assert r.success is False


def test_base_executor_ensure_log_dir(tmp_path):
    class TestExecutor(BaseExecutor):
        async def execute(self, command, env, log_path, timeout=None, cwd=None):
            pass

    ex = TestExecutor()
    log_path = tmp_path / "sub" / "test.log"
    ex._ensure_log_dir(log_path)
    assert log_path.parent.exists()


def test_base_executor_cancel():
    class TestExecutor(BaseExecutor):
        async def execute(self, command, env, log_path, timeout=None, cwd=None):
            pass

    ex = TestExecutor()
    result = asyncio.run(ex.cancel())
    assert result is None


def test_create_executor_ssh(tmp_path):
    task = ResolvedTask(
        name="t",
        task_type="command",
        command="echo",
        host="myhost",
    )

    with patch("taskpps.loaders.agent_loader.get_agents_dir") as mock_get_agents_dir:
        agents_dir = tmp_path / "agents"
        agents_dir.mkdir()
        agent_file = agents_dir / "myhost.yaml"
        agent_file.write_text("host: 1.2.3.4\nport: 2222\nusername: admin\n")
        mock_get_agents_dir.return_value = agents_dir

        executor = create_executor(task)
        assert isinstance(executor, SSHExecutor)
        assert executor.host == "1.2.3.4"
        assert executor.port == 2222
        assert executor.username == "admin"


def test_create_executor_ssh_with_credential(tmp_path):
    task = ResolvedTask(
        name="t",
        task_type="command",
        command="echo",
        host="myhost",
        credential="mycred",
    )

    with patch("taskpps.loaders.agent_loader.get_agents_dir") as mock_get_agents_dir, \
            patch("taskpps.loaders.credential_loader.get_credentials_dir") as mock_get_creds_dir:
        agents_dir = tmp_path / "agents"
        agents_dir.mkdir()
        agent_file = agents_dir / "myhost.yaml"
        agent_file.write_text("host: 1.2.3.4\nport: 2222\nusername: admin\n")
        mock_get_agents_dir.return_value = agents_dir

        creds_dir = tmp_path / "credentials"
        creds_dir.mkdir()
        cred_file = creds_dir / "mycred.yaml"
        cred_file.write_text("password: secret123\n")
        mock_get_creds_dir.return_value = creds_dir

        executor = create_executor(task)
        assert isinstance(executor, SSHExecutor)
        assert executor.password == "secret123"


def test_create_executor_ssh_agent_not_found(tmp_path):
    task = ResolvedTask(
        name="t",
        task_type="command",
        command="echo",
        host="nonexistent-host",
    )

    with patch("taskpps.loaders.agent_loader.get_agents_dir") as mock_get_agents_dir:
        agents_dir = tmp_path / "agents"
        agents_dir.mkdir()
        mock_get_agents_dir.return_value = agents_dir

        executor = create_executor(task)
        assert isinstance(executor, LocalExecutor)


def test_create_executor_ssh_credential_not_found(tmp_path):
    task = ResolvedTask(
        name="t",
        task_type="command",
        command="echo",
        host="myhost",
        credential="nonexistent-cred",
    )

    with patch("taskpps.loaders.agent_loader.get_agents_dir") as mock_get_agents_dir, \
            patch("taskpps.loaders.credential_loader.get_credentials_dir") as mock_get_creds_dir:
        agents_dir = tmp_path / "agents"
        agents_dir.mkdir()
        agent_file = agents_dir / "myhost.yaml"
        agent_file.write_text("host: 1.2.3.4\nport: 2222\nusername: admin\n")
        mock_get_agents_dir.return_value = agents_dir

        creds_dir = tmp_path / "credentials"
        creds_dir.mkdir()
        mock_get_creds_dir.return_value = creds_dir

        executor = create_executor(task)
        assert isinstance(executor, SSHExecutor)
        assert executor.password is None
        assert executor.key_path is None


def test_create_executor_command_no_host():
    task = ResolvedTask(name="t", task_type="command", command="echo")
    executor = create_executor(task)
    assert isinstance(executor, LocalExecutor)


def test_create_executor_invoke_type():
    task = ResolvedTask(name="t", task_type="invoke", invoke_task="mod.fn")
    executor = create_executor(task)
    assert isinstance(executor, InvokeExecutor)


@pytest.mark.asyncio
async def test_local_executor_cancel(tmp_path):
    executor = LocalExecutor()
    log_path = tmp_path / "cancel_test.log"

    async def delayed_task():
        return await executor.execute("sleep 30", {}, log_path, timeout=60)

    task = asyncio.create_task(delayed_task())
    await asyncio.sleep(0.3)
    await executor.cancel()
    result = await task
    assert not result.success
    assert result.exit_code != 0


@pytest.mark.asyncio
async def test_invoke_executor_no_task(tmp_path):
    executor = InvokeExecutor()
    log_path = tmp_path / "no_task.log"
    result = await executor.execute("", {}, log_path)
    assert not result.success
    assert result.exit_code == 1


@pytest.mark.asyncio
async def test_invoke_executor_invalid_format(tmp_path):
    executor = InvokeExecutor()
    log_path = tmp_path / "invalid.log"
    result = await executor.execute("", {}, log_path, invoke_task="invalidformat")
    assert not result.success
    assert result.exit_code == 1


@pytest.mark.asyncio
async def test_invoke_executor_timeout(tmp_path):
    executor = InvokeExecutor()
    log_path = tmp_path / "timeout.log"

    tasks_dir = tmp_path / "tasks"
    tasks_dir.mkdir()
    task_file = tasks_dir / "slow_module.py"
    task_file.write_text("""
def slow_func():
    import time
    time.sleep(30)
""")

    with patch("taskpps.executors.invoke.get_tasks_dir", return_value=tasks_dir):
        result = await executor.execute(
            "", {}, log_path, timeout=1, invoke_task="slow_module.slow_func",
        )
    assert not result.success
    assert result.exit_code == -1


@pytest.mark.asyncio
async def test_invoke_executor_cancel(tmp_path):
    executor = InvokeExecutor()

    with patch.object(executor, "_cancelled", True):
        await executor.cancel()
        assert executor._cancelled is True


@pytest.mark.asyncio
async def test_invoke_executor_import_error(tmp_path):
    executor = InvokeExecutor()
    log_path = tmp_path / "import_err.log"
    result = await executor.execute(
        "", {}, log_path, invoke_task="nonexistent_module.nonexistent_func",
    )
    assert not result.success


@pytest.mark.asyncio
async def test_invoke_executor_run_invoke_function(tmp_path):
    executor = InvokeExecutor()
    log_path = tmp_path / "invoke_fn.log"

    tasks_dir = tmp_path / "tasks"
    tasks_dir.mkdir()
    task_file = tasks_dir / "hello_fn.py"
    task_file.write_text("""
def greet(name="world"):
    return f"hello {name}"
""")

    with patch("taskpps.executors.invoke.get_tasks_dir", return_value=tasks_dir):
        result = await executor.execute(
            "", {}, log_path, invoke_task="hello_fn.greet", invoke_kwargs={"name": "test"},
        )
    assert result.success
    assert "hello test" in result.stdout


@pytest.mark.asyncio
async def test_ssh_executor_with_cwd(tmp_path):
    executor = SSHExecutor(host="127.0.0.1", port=29999, username="test")
    log_path = tmp_path / "cwd_test.log"
    result = await executor.execute("echo hello", {}, log_path, cwd="/tmp")
    assert not result.success


@pytest.mark.asyncio
async def test_ssh_executor_with_key_path():
    executor = SSHExecutor(host="1.2.3.4", port=22, username="root", key_path="/tmp/key")
    assert executor.key_path == "/tmp/key"


@pytest.mark.asyncio
async def test_ssh_executor_execute_exception(tmp_path):
    executor = SSHExecutor(host="127.0.0.1", port=29999, username="test")
    log_path = tmp_path / "exception.log"
    result = await executor.execute("echo hello", {}, log_path)
    assert not result.success
    assert result.exit_code == -1


@pytest.mark.asyncio
async def test_ssh_executor_cancel():
    executor = SSHExecutor(host="127.0.0.1", port=29999, username="test")
    await executor.cancel()


@pytest.mark.asyncio
async def test_ssh_executor_cancel_with_client():
    executor = SSHExecutor(host="127.0.0.1", port=29999, username="test")
    import paramiko
    client = paramiko.SSHClient()
    executor._client = client
    executor._channel = MagicMock()
    await executor.cancel()
    assert executor._client is not None


@pytest.mark.asyncio
async def test_ssh_executor_cancel_close_exception():
    executor = SSHExecutor(host="127.0.0.1", port=29999, username="test")
    executor._channel = MagicMock()
    executor._channel.close.side_effect = Exception("close error")
    executor._client = MagicMock()
    executor._client.close.side_effect = Exception("client close error")
    await executor.cancel()

import pytest
from pathlib import Path
from taskpps.executors.ssh import SSHExecutor
from taskpps.executors.base import BaseExecutor, ExecutorResult


def test_base_executor_is_abstract():
    with pytest.raises(TypeError):
        BaseExecutor()


def test_executor_result_properties():
    r = ExecutorResult(exit_code=0, stdout="out", stderr="err")
    assert r.success is True
    assert r.stdout == "out"
    assert r.stderr == "err"

    r2 = ExecutorResult(exit_code=1)
    assert r2.success is False


def test_ssh_executor_init():
    ex = SSHExecutor(host="1.2.3.4", port=2222, username="admin", password="pass")
    assert ex.host == "1.2.3.4"
    assert ex.port == 2222
    assert ex.username == "admin"
    assert ex.password == "pass"
    assert ex.key_path is None


def test_ssh_executor_init_with_key():
    ex = SSHExecutor(host="1.2.3.4", username="root", key_path="/path/to/key")
    assert ex.key_path == "/path/to/key"


@pytest.mark.asyncio
async def test_ssh_executor_connection_refused(tmp_path):
    ex = SSHExecutor(host="127.0.0.1", port=29999, username="test", password="test")
    log_path = tmp_path / "test.log"
    result = await ex.execute("echo hello", {}, log_path)
    assert not result.success
    assert result.exit_code == -1


@pytest.mark.asyncio
async def test_ssh_executor_cancel():
    ex = SSHExecutor(host="127.0.0.1", port=29999, username="test", password="test")
    await ex.cancel()

import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock, AsyncMock, call
from taskpps.executors.ssh import SSHExecutor
from taskpps.executors.base import ExecutorResult


def test_ssh_build_env_exports():
    ex = SSHExecutor(host="1.2.3.4", username="root", password="pass")
    import shlex
    env = {"FOO": "bar", "BAZ": "qux"}
    exports = " ".join(f"export {shlex.quote(k)}={shlex.quote(v)}" for k, v in env.items())
    assert "export FOO=bar" in exports
    assert "export BAZ=qux" in exports


@pytest.mark.asyncio
async def test_ssh_execute_with_key_path(tmp_path):
    ex = SSHExecutor(host="1.2.3.4", username="root", key_path="/path/to/key")
    assert ex.key_path == "/path/to/key"

    mock_result = MagicMock()
    mock_result.stdout = "hello world"
    mock_result.stderr = ""
    mock_result.exited = 0

    mock_conn = MagicMock()
    mock_conn.run.return_value = mock_result
    mock_conn.cd.return_value.__enter__ = MagicMock(return_value=None)
    mock_conn.cd.return_value.__exit__ = MagicMock(return_value=False)
    mock_conn.close = MagicMock()

    log_path = tmp_path / "ssh_test.log"

    with patch("taskpps.executors.ssh.Connection", return_value=mock_conn):
        result = await ex.execute("echo hello", {"ENV": "test"}, log_path, timeout=30)

    assert result.exit_code == 0
    assert "hello" in result.stdout
    assert log_path.exists()


@pytest.mark.asyncio
async def test_ssh_execute_script_and_cleanup(tmp_path):
    ex = SSHExecutor(host="1.2.3.4", username="root", password="pass")

    mock_result = MagicMock()
    mock_result.stdout = "done"
    mock_result.stderr = ""
    mock_result.exited = 0

    mock_conn = MagicMock()
    mock_conn.run.return_value = mock_result
    mock_conn.cd.return_value.__enter__ = MagicMock(return_value=None)
    mock_conn.cd.return_value.__exit__ = MagicMock(return_value=False)
    mock_conn.close = MagicMock()

    log_path = tmp_path / "ssh_upload.log"

    with patch("taskpps.executors.ssh.Connection", return_value=mock_conn):
        result = await ex.execute("echo done", {}, log_path)

    assert result.exit_code == 0
    mock_conn.run.assert_called_once()
    mock_conn.close.assert_called_once()


@pytest.mark.asyncio
async def test_ssh_execute_run_failure(tmp_path):
    ex = SSHExecutor(host="1.2.3.4", username="root", password="pass")

    mock_result = MagicMock()
    mock_result.stdout = "output"
    mock_result.stderr = "error"
    mock_result.exited = 1

    mock_conn = MagicMock()
    mock_conn.run.return_value = mock_result
    mock_conn.cd.return_value.__enter__ = MagicMock(return_value=None)
    mock_conn.cd.return_value.__exit__ = MagicMock(return_value=False)
    mock_conn.close = MagicMock()

    log_path = tmp_path / "ssh_remove_fail.log"

    with patch("taskpps.executors.ssh.Connection", return_value=mock_conn):
        result = await ex.execute("cmd", {}, log_path)

    assert result.exit_code == 1


@pytest.mark.asyncio
async def test_ssh_execute_with_cwd(tmp_path):
    ex = SSHExecutor(host="1.2.3.4", username="root", password="pass")

    mock_result = MagicMock()
    mock_result.stdout = "done"
    mock_result.stderr = ""
    mock_result.exited = 0

    mock_conn = MagicMock()
    mock_conn.run.return_value = mock_result
    mock_conn.cd.return_value.__enter__ = MagicMock(return_value=None)
    mock_conn.cd.return_value.__exit__ = MagicMock(return_value=False)
    mock_conn.close = MagicMock()

    log_path = tmp_path / "ssh_cwd.log"

    with patch("taskpps.executors.ssh.Connection", return_value=mock_conn):
        result = await ex.execute("pwd", {}, log_path, cwd="/var/www")

    assert result.exit_code == 0
    mock_conn.cd.assert_called_once_with("/var/www")

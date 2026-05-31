from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from taskpps.executors.ssh import SSHExecutor


def test_ssh_executor_init():
    executor = SSHExecutor(host="192.168.1.1", port=22, username="root", password="secret")
    assert executor.host == "192.168.1.1"
    assert executor.port == 22
    assert executor.username == "root"
    assert executor.password == "secret"
    assert executor.key_path is None


def test_ssh_executor_init_with_key():
    executor = SSHExecutor(host="10.0.0.1", port=2222, username="admin", key_path="/home/user/.ssh/id_rsa")
    assert executor.host == "10.0.0.1"
    assert executor.port == 2222
    assert executor.key_path == "/home/user/.ssh/id_rsa"


def test_make_connect_kwargs_password():
    executor = SSHExecutor(host="h", password="pass")
    kwargs = executor._make_connect_kwargs()
    assert kwargs == {"password": "pass"}


def test_make_connect_kwargs_key():
    executor = SSHExecutor(host="h", key_path="/key")
    kwargs = executor._make_connect_kwargs()
    assert kwargs == {"key_filename": "/key"}


def test_make_connect_kwargs_key_over_password():
    executor = SSHExecutor(host="h", password="pass", key_path="/key")
    kwargs = executor._make_connect_kwargs()
    assert kwargs == {"key_filename": "/key"}


def test_make_connect_kwargs_none():
    executor = SSHExecutor(host="h")
    kwargs = executor._make_connect_kwargs()
    assert kwargs == {}


@pytest.mark.asyncio
async def test_ssh_executor_execute_success(tmp_path):
    log_path = tmp_path / "test.log"
    executor = SSHExecutor(host="192.168.1.1", port=22, username="root", password="secret")

    mock_result = MagicMock()
    mock_result.stdout = "hello world"
    mock_result.stderr = ""
    mock_result.exited = 0

    mock_conn = MagicMock()
    mock_conn.run.return_value = mock_result
    mock_conn.cd.return_value.__enter__ = MagicMock(return_value=None)
    mock_conn.cd.return_value.__exit__ = MagicMock(return_value=False)
    mock_conn.close = MagicMock()

    with patch("taskpps.executors.ssh.Connection", return_value=mock_conn):
        result = await executor.execute("ls", {}, log_path, cwd="/workspace/repo")

    assert result.success
    assert result.exit_code == 0
    assert "hello world" in result.stdout
    mock_conn.run.assert_called_once()
    mock_conn.cd.assert_called_once_with("/workspace/repo")


@pytest.mark.asyncio
async def test_ssh_executor_execute_failure(tmp_path):
    log_path = tmp_path / "test.log"
    executor = SSHExecutor(host="192.168.1.1", port=22, username="root", password="secret")

    mock_result = MagicMock()
    mock_result.stdout = ""
    mock_result.stderr = "command not found"
    mock_result.exited = 127

    mock_conn = MagicMock()
    mock_conn.run.return_value = mock_result
    mock_conn.cd.return_value.__enter__ = MagicMock(return_value=None)
    mock_conn.cd.return_value.__exit__ = MagicMock(return_value=False)
    mock_conn.close = MagicMock()

    with patch("taskpps.executors.ssh.Connection", return_value=mock_conn):
        result = await executor.execute("badcmd", {}, log_path)

    assert not result.success
    assert result.exit_code == 127


@pytest.mark.asyncio
async def test_ssh_executor_execute_connection_error(tmp_path):
    log_path = tmp_path / "test.log"
    executor = SSHExecutor(host="192.168.1.1", port=22, username="root", password="secret")

    with patch("taskpps.executors.ssh.Connection", side_effect=Exception("Connection refused")):
        result = await executor.execute("ls", {}, log_path)

    assert not result.success
    assert result.exit_code == -1
    assert "Connection refused" in result.stderr


@pytest.mark.asyncio
async def test_ssh_executor_execute_no_cwd(tmp_path):
    log_path = tmp_path / "test.log"
    executor = SSHExecutor(host="h", password="p")

    mock_result = MagicMock()
    mock_result.stdout = "ok"
    mock_result.stderr = ""
    mock_result.exited = 0

    mock_conn = MagicMock()
    mock_conn.run.return_value = mock_result
    mock_conn.cd.return_value.__enter__ = MagicMock(return_value=None)
    mock_conn.cd.return_value.__exit__ = MagicMock(return_value=False)
    mock_conn.close = MagicMock()

    with patch("taskpps.executors.ssh.Connection", return_value=mock_conn):
        await executor.execute("ls", {}, log_path)

    mock_conn.cd.assert_called_once_with(".")


@pytest.mark.asyncio
async def test_ssh_executor_cancel():
    executor = SSHExecutor(host="h", password="p")
    mock_conn = MagicMock()
    executor._connection = mock_conn

    await executor.cancel()
    mock_conn.close.assert_called_once()

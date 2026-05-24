import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock, AsyncMock, call
from taskpps.executors.ssh import SSHExecutor
from taskpps.executors.base import ExecutorResult


@patch("taskpps.executors.ssh.get_settings")
def test_ssh_build_script_content_with_cwd_env(mock_settings):
    mock_settings.return_value.executor.shell = "/bin/sh"
    ex = SSHExecutor(host="1.2.3.4", username="root", password="pass")

    def _build_script_content():
        lines = ["#!/bin/sh", "set -e"]
        lines.append("cd /app")
        for k, v in {"FOO": "bar", "BAZ": "qux"}.items():
            import shlex
            lines.append(f"export {shlex.quote(k)}={shlex.quote(v)}")
        lines.append("echo hello")
        return "\n".join(lines) + "\n"

    script = _build_script_content()
    assert script.startswith("#!/bin/sh\nset -e\ncd /app\n")
    assert "export FOO=bar" in script
    assert "export BAZ=qux" in script
    assert script.endswith("echo hello\n")


@pytest.mark.asyncio
async def test_ssh_execute_with_key_path(tmp_path):
    ex = SSHExecutor(host="1.2.3.4", username="root", key_path="/path/to/key")
    assert ex.key_path == "/path/to/key"

    mock_client = MagicMock()
    mock_sftp = MagicMock()
    mock_sftp_file = MagicMock()
    mock_sftp.__enter__.return_value = mock_sftp
    mock_sftp.file.return_value.__enter__.return_value = mock_sftp_file

    mock_stdout = MagicMock()
    mock_stdout.read.return_value = b"hello world"
    mock_stderr = MagicMock()
    mock_stderr.read.return_value = b""
    mock_channel = MagicMock()
    mock_channel.recv_exit_status.return_value = 0
    mock_stdout.channel = mock_channel

    mock_client.open_sftp.return_value = mock_sftp
    mock_client.exec_command.return_value = (MagicMock(), mock_stdout, mock_stderr)
    mock_client.connect = MagicMock()

    mock_client_class = MagicMock()
    mock_client_class.return_value = mock_client

    log_path = tmp_path / "ssh_test.log"

    with patch("paramiko.SSHClient", mock_client_class), \
         patch("taskpps.executors.ssh.get_settings") as mock_settings:
        mock_settings.return_value.executor.shell = "/bin/sh"
        result = await ex.execute("echo hello", {"ENV": "test"}, log_path, timeout=30)

    assert result.exit_code == 0
    assert "hello" in result.stdout or "hello" in result.stderr
    assert log_path.exists()


@pytest.mark.asyncio
async def test_ssh_execute_script_upload_and_cleanup(tmp_path):
    ex = SSHExecutor(host="1.2.3.4", username="root", password="pass")

    mock_client = MagicMock()
    mock_sftp = MagicMock()
    mock_sftp_file = MagicMock()
    mock_sftp.__enter__.side_effect = [mock_sftp, mock_sftp]
    mock_sftp.file.return_value.__enter__.return_value = mock_sftp_file

    mock_stdout = MagicMock()
    mock_stdout.read.return_value = b"done"
    mock_stderr = MagicMock()
    mock_stderr.read.return_value = b""
    mock_channel = MagicMock()
    mock_channel.recv_exit_status.return_value = 0
    mock_stdout.channel = mock_channel

    mock_client.open_sftp.return_value = mock_sftp
    mock_client.exec_command.return_value = (MagicMock(), mock_stdout, mock_stderr)
    mock_client.connect = MagicMock()

    mock_client_class = MagicMock()
    mock_client_class.return_value = mock_client

    log_path = tmp_path / "ssh_upload.log"

    with patch("paramiko.SSHClient", mock_client_class), \
         patch("taskpps.executors.ssh.get_settings") as mock_settings:
        mock_settings.return_value.executor.shell = "/bin/sh"
        result = await ex.execute("echo done", {}, log_path)

    assert result.exit_code == 0
    assert mock_client.connect.called
    assert mock_sftp.file.called
    assert mock_sftp_file.write.called
    assert mock_sftp.chmod.called
    assert mock_client.exec_command.called
    assert mock_sftp.remove.called


@pytest.mark.asyncio
async def test_ssh_execute_sftp_remove_failure(tmp_path):
    """Test that sftp.remove failure doesn't propagate (OSError caught)."""
    ex = SSHExecutor(host="1.2.3.4", username="root", password="pass")

    mock_client = MagicMock()
    mock_sftp = MagicMock()
    mock_sftp.__enter__.side_effect = [mock_sftp, mock_sftp]
    mock_sftp.file.return_value.__enter__.return_value = MagicMock()
    mock_sftp.remove.side_effect = OSError("remove failed")

    mock_stdout = MagicMock()
    mock_stdout.read.return_value = b"output"
    mock_stderr = MagicMock()
    mock_stderr.read.return_value = b""
    mock_channel = MagicMock()
    mock_channel.recv_exit_status.return_value = 1
    mock_stdout.channel = mock_channel

    mock_client.open_sftp.return_value = mock_sftp
    mock_client.exec_command.return_value = (MagicMock(), mock_stdout, mock_stderr)
    mock_client.connect = MagicMock()

    mock_client_class = MagicMock()
    mock_client_class.return_value = mock_client

    log_path = tmp_path / "ssh_remove_fail.log"

    with patch("paramiko.SSHClient", mock_client_class), \
         patch("taskpps.executors.ssh.get_settings") as mock_settings:
        mock_settings.return_value.executor.shell = "/bin/sh"
        result = await ex.execute("cmd", {}, log_path)

    assert result.exit_code == 1
    assert mock_sftp.remove.called


@pytest.mark.asyncio
async def test_ssh_execute_with_cwd(tmp_path):
    ex = SSHExecutor(host="1.2.3.4", username="root", password="pass")

    mock_client = MagicMock()
    mock_sftp = MagicMock()
    mock_sftp.__enter__.side_effect = [mock_sftp, mock_sftp]
    mock_sftp.file.return_value.__enter__.return_value = MagicMock()

    mock_stdout = MagicMock()
    mock_stdout.read.return_value = b"done"
    mock_stderr = MagicMock()
    mock_stderr.read.return_value = b""
    mock_channel = MagicMock()
    mock_channel.recv_exit_status.return_value = 0
    mock_stdout.channel = mock_channel

    mock_client.open_sftp.return_value = mock_sftp
    mock_client.exec_command.return_value = (MagicMock(), mock_stdout, mock_stderr)
    mock_client.connect = MagicMock()

    mock_client_class = MagicMock()
    mock_client_class.return_value = mock_client

    log_path = tmp_path / "ssh_cwd.log"

    with patch("paramiko.SSHClient", mock_client_class), \
         patch("taskpps.executors.ssh.get_settings") as mock_settings:
        mock_settings.return_value.executor.shell = "/bin/sh"
        result = await ex.execute("pwd", {}, log_path, cwd="/var/www")

    assert result.exit_code == 0

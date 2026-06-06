from __future__ import annotations

import asyncio
from unittest.mock import MagicMock, patch

import pytest

from taskpps.executors.ssh import SSHExecutor


class TestSSHExecutorExitCodeCoverage:
    def test_ssh_transport_none_raises(self, tmp_path):
        log_path = tmp_path / "ssh_trans.log"
        executor = SSHExecutor(host="1.2.3.4", password="p")

        mock_client = MagicMock()
        mock_client.get_transport.return_value = None

        with patch("taskpps.executors.ssh.paramiko") as mock_paramiko:
            mock_paramiko.SSHClient.return_value = mock_client
            result = asyncio.run(executor.execute("cmd", {}, log_path))
            assert not result.success
            assert result.exit_code == -1

    def test_ssh_client_none_during_read(self, tmp_path):
        log_path = tmp_path / "ssh_none.log"
        executor = SSHExecutor(host="1.2.3.4", password="p")

        mock_client = MagicMock()
        mock_client.get_transport.return_value = MagicMock()
        mock_channel = MagicMock()
        mock_client.get_transport().open_session.return_value = mock_channel
        mock_channel.recv.return_value = b"hello\n"
        mock_channel.recv_ready.return_value = False
        mock_channel.recv_stderr_ready.return_value = False
        mock_channel.exit_status_ready.return_value = False
        mock_channel.recv_exit_status.return_value = 0

        with patch("taskpps.executors.ssh.paramiko") as mock_paramiko:
            mock_paramiko.SSHClient.return_value = mock_client
            with patch("taskpps.executors.ssh.select") as mock_select:
                mock_select.select.return_value = ([mock_channel], [], [])

                def set_client_none(*args, **kwargs):
                    executor._client = None
                    return ([mock_channel], [], [])

                mock_select.select.side_effect = [
                    ([mock_channel], [], []),
                    set_client_none,
                    ([mock_channel], [], []),
                ]

                result = asyncio.run(executor.execute("cmd", {}, log_path))
                assert not result.success
                assert result.exit_code == -1

    def test_ssh_cancelled_error(self, tmp_path):
        log_path = tmp_path / "ssh_cancel.log"
        executor = SSHExecutor(host="1.2.3.4", password="p")

        with patch("taskpps.executors.ssh.paramiko") as mock_paramiko:
            mock_client = MagicMock()
            mock_client.connect.side_effect = asyncio.CancelledError()
            mock_paramiko.SSHClient.return_value = mock_client

            result = asyncio.run(executor.execute("cmd", {}, log_path))
            assert not result.success
            assert result.exit_code == -1

    def test_ssh_channel_close_exception(self, tmp_path):
        log_path = tmp_path / "ssh_chclose.log"
        executor = SSHExecutor(host="1.2.3.4", password="p")

        mock_client = MagicMock()
        mock_client.get_transport.return_value = MagicMock()
        mock_channel = MagicMock()
        mock_channel.close.side_effect = Exception("close failed")
        mock_client.get_transport().open_session.return_value = mock_channel
        mock_channel.recv.return_value = b""
        mock_channel.recv_ready.return_value = False
        mock_channel.recv_stderr_ready.return_value = False
        mock_channel.exit_status_ready.return_value = True
        mock_channel.recv_exit_status.return_value = 0

        with patch("taskpps.executors.ssh.paramiko") as mock_paramiko:
            mock_paramiko.SSHClient.return_value = mock_client
            with patch("taskpps.executors.ssh.select") as mock_select:
                mock_select.select.return_value = ([mock_channel], [], [])
                result = asyncio.run(executor.execute("cmd", {}, log_path))
                assert result.success
                assert result.exit_code == 0

    def test_ssh_client_close_exception(self, tmp_path):
        log_path = tmp_path / "ssh_clclose.log"
        executor = SSHExecutor(host="1.2.3.4", password="p")

        mock_client = MagicMock()
        mock_client.close.side_effect = Exception("client close failed")
        mock_client.get_transport.return_value = MagicMock()
        mock_channel = MagicMock()
        mock_client.get_transport().open_session.return_value = mock_channel
        mock_channel.recv.return_value = b""
        mock_channel.recv_ready.return_value = False
        mock_channel.recv_stderr_ready.return_value = False
        mock_channel.exit_status_ready.return_value = True
        mock_channel.recv_exit_status.return_value = 0

        with patch("taskpps.executors.ssh.paramiko") as mock_paramiko:
            mock_paramiko.SSHClient.return_value = mock_client
            with patch("taskpps.executors.ssh.select") as mock_select:
                mock_select.select.return_value = ([mock_channel], [], [])
                result = asyncio.run(executor.execute("cmd", {}, log_path))
                assert result.success
                assert result.exit_code == 0

    def test_ssh_cancel_handles_close_exception(self, tmp_path):
        executor = SSHExecutor(host="1.2.3.4", password="p")
        mock_client = MagicMock()
        mock_client.close.side_effect = Exception("close error")
        executor._client = mock_client
        executor._channel = MagicMock()
        asyncio.run(executor.cancel())
        assert executor._client is None

    def test_ssh_execute_with_stderr_reading(self, tmp_path):
        log_path = tmp_path / "ssh_stderr.log"
        executor = SSHExecutor(host="1.2.3.4", password="p")

        mock_client = MagicMock()
        mock_client.get_transport.return_value = MagicMock()
        mock_channel = MagicMock()
        mock_client.get_transport().open_session.return_value = mock_channel

        recv_results = [b"output1\n", b"", b""]
        recv_call_count = [0]

        def recv_side_effect(*args):
            idx = recv_call_count[0]
            recv_call_count[0] += 1
            return recv_results[idx] if idx < len(recv_results) else b""

        mock_channel.recv.side_effect = recv_side_effect
        mock_channel.recv_ready.side_effect = [True, False, False]
        mock_channel.recv_stderr_ready.side_effect = [True, False]
        mock_channel.exit_status_ready.side_effect = [False, True]
        mock_channel.recv_exit_status.return_value = 0

        mock_channel.recv_stderr.return_value = b"stderr_output\n"

        with patch("taskpps.executors.ssh.paramiko") as mock_paramiko:
            mock_paramiko.SSHClient.return_value = mock_client
            with patch("taskpps.executors.ssh.select") as mock_select:
                mock_select.select.return_value = ([mock_channel], [], [])
                result = asyncio.run(executor.execute("cmd", {}, log_path))
                assert result.success
                assert "stderr_output" in result.stdout


class TestSSHExecutor:
    def test_init(self):
        executor = SSHExecutor(host="192.168.1.1", port=22, username="root", password="secret")
        assert executor.host == "192.168.1.1"
        assert executor.port == 22
        assert executor.username == "root"
        assert executor.password == "secret"
        assert executor.key_path is None

    def test_init_with_key(self):
        executor = SSHExecutor(host="10.0.0.1", port=2222, username="admin", key_path="/home/user/.ssh/id_rsa")
        assert executor.host == "10.0.0.1"
        assert executor.port == 2222
        assert executor.key_path == "/home/user/.ssh/id_rsa"

    def test_make_connect_kwargs_password(self):
        executor = SSHExecutor(host="h", password="pass")
        kwargs = executor._make_connect_kwargs()
        assert kwargs == {"password": "pass"}

    def test_make_connect_kwargs_key(self):
        executor = SSHExecutor(host="h", key_path="/key")
        kwargs = executor._make_connect_kwargs()
        assert kwargs == {"key_filename": "/key"}

    def test_make_connect_kwargs_key_over_password(self):
        executor = SSHExecutor(host="h", password="pass", key_path="/key")
        kwargs = executor._make_connect_kwargs()
        assert kwargs == {"key_filename": "/key"}

    def test_make_connect_kwargs_none(self):
        executor = SSHExecutor(host="h")
        kwargs = executor._make_connect_kwargs()
        assert kwargs == {}

    @staticmethod
    def _build_mock_paramiko(output: str = "", exit_code: int = 0):
        mock_channel = MagicMock()
        encoded = output.encode("utf-8") if output else b""
        mock_channel.recv.side_effect = [encoded, b""]
        mock_channel.recv_stderr_ready.return_value = False
        mock_channel.recv_ready.return_value = False
        mock_channel.exit_status_ready.side_effect = [False, True]
        mock_channel.recv_exit_status.return_value = exit_code

        mock_transport = MagicMock()
        mock_transport.open_session.return_value = mock_channel

        mock_client = MagicMock()
        mock_client.get_transport.return_value = mock_transport

        return mock_client, mock_channel

    @pytest.mark.asyncio
    async def test_execute_success(self, tmp_path):
        log_path = tmp_path / "test.log"
        executor = SSHExecutor(host="192.168.1.1", port=22, username="root", password="secret")

        mock_client, mock_channel = self._build_mock_paramiko("hello world", 0)

        with (
            patch("taskpps.executors.ssh.paramiko") as mock_paramiko,
            patch("taskpps.executors.ssh.select") as mock_select,
        ):
            mock_paramiko.SSHClient.return_value = mock_client
            mock_paramiko.AutoAddPolicy.return_value = MagicMock()
            mock_select.select.return_value = ([mock_channel], [], [])
            result = await executor.execute("ls", {}, log_path, cwd="/workspace/repo")

        assert result.success
        assert result.exit_code == 0
        assert "hello world" in result.stdout
        mock_client.connect.assert_called_once()
        cmd_arg = mock_client.get_transport().open_session().exec_command.call_args[0][0]
        assert "/workspace/repo" in cmd_arg

    @pytest.mark.asyncio
    async def test_execute_failure(self, tmp_path):
        log_path = tmp_path / "test.log"
        executor = SSHExecutor(host="192.168.1.1", port=22, username="root", password="secret")

        mock_client, mock_channel = self._build_mock_paramiko("", 127)

        with (
            patch("taskpps.executors.ssh.paramiko") as mock_paramiko,
            patch("taskpps.executors.ssh.select") as mock_select,
        ):
            mock_paramiko.SSHClient.return_value = mock_client
            mock_paramiko.AutoAddPolicy.return_value = MagicMock()
            mock_select.select.return_value = ([mock_channel], [], [])
            result = await executor.execute("badcmd", {}, log_path)

        assert not result.success
        assert result.exit_code == 127

    @pytest.mark.asyncio
    async def test_execute_connection_error(self, tmp_path):
        log_path = tmp_path / "test.log"
        executor = SSHExecutor(host="192.168.1.1", port=22, username="root", password="secret")

        with patch("taskpps.executors.ssh.paramiko") as mock_paramiko:
            mock_client = MagicMock()
            mock_client.connect.side_effect = Exception("Connection refused")
            mock_paramiko.SSHClient.return_value = mock_client
            mock_paramiko.AutoAddPolicy.return_value = MagicMock()
            result = await executor.execute("ls", {}, log_path)

        assert not result.success
        assert result.exit_code == -1
        assert "Connection refused" in result.stderr

    @pytest.mark.asyncio
    async def test_execute_no_cwd(self, tmp_path):
        log_path = tmp_path / "test.log"
        executor = SSHExecutor(host="h", password="p")

        mock_client, mock_channel = self._build_mock_paramiko("ok", 0)

        with (
            patch("taskpps.executors.ssh.paramiko") as mock_paramiko,
            patch("taskpps.executors.ssh.select") as mock_select,
        ):
            mock_paramiko.SSHClient.return_value = mock_client
            mock_paramiko.AutoAddPolicy.return_value = MagicMock()
            mock_select.select.return_value = ([mock_channel], [], [])
            await executor.execute("ls", {}, log_path)

        cmd_arg = mock_client.get_transport().open_session().exec_command.call_args[0][0]
        assert "cd" in cmd_arg and "." in cmd_arg

    @pytest.mark.asyncio
    async def test_cancel_with_connection(self):
        executor = SSHExecutor(host="h", password="p")
        mock_client = MagicMock()
        executor._client = mock_client

        await executor.cancel()
        mock_client.close.assert_called_once()
        assert executor._client is None

    @pytest.mark.asyncio
    async def test_execute_with_key_path(self, tmp_path):
        ex = SSHExecutor(host="1.2.3.4", username="root", key_path="/path/to/key")
        assert ex.key_path == "/path/to/key"

        mock_client, mock_channel = self._build_mock_paramiko("hello world", 0)

        log_path = tmp_path / "ssh_test.log"

        with (
            patch("taskpps.executors.ssh.paramiko") as mock_paramiko,
            patch("taskpps.executors.ssh.select") as mock_select,
        ):
            mock_paramiko.SSHClient.return_value = mock_client
            mock_paramiko.AutoAddPolicy.return_value = MagicMock()
            mock_select.select.return_value = ([mock_channel], [], [])
            result = await ex.execute("echo hello", {"ENV": "test"}, log_path, timeout=30)

        assert result.exit_code == 0
        assert "hello" in result.stdout
        assert log_path.exists()

    @pytest.mark.asyncio
    async def test_execute_script_and_cleanup(self, tmp_path):
        ex = SSHExecutor(host="1.2.3.4", username="root", password="pass")

        mock_client, mock_channel = self._build_mock_paramiko("done", 0)

        log_path = tmp_path / "ssh_upload.log"

        with (
            patch("taskpps.executors.ssh.paramiko") as mock_paramiko,
            patch("taskpps.executors.ssh.select") as mock_select,
        ):
            mock_paramiko.SSHClient.return_value = mock_client
            mock_paramiko.AutoAddPolicy.return_value = MagicMock()
            mock_select.select.return_value = ([mock_channel], [], [])
            result = await ex.execute("echo done", {}, log_path)

        assert result.exit_code == 0
        mock_client.get_transport().open_session().exec_command.assert_called_once()
        mock_client.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_execute_run_failure(self, tmp_path):
        ex = SSHExecutor(host="1.2.3.4", username="root", password="pass")

        mock_client, mock_channel = self._build_mock_paramiko("output", 1)

        log_path = tmp_path / "ssh_remove_fail.log"

        with (
            patch("taskpps.executors.ssh.paramiko") as mock_paramiko,
            patch("taskpps.executors.ssh.select") as mock_select,
        ):
            mock_paramiko.SSHClient.return_value = mock_client
            mock_paramiko.AutoAddPolicy.return_value = MagicMock()
            mock_select.select.return_value = ([mock_channel], [], [])
            result = await ex.execute("cmd", {}, log_path)

        assert result.exit_code == 1

    @pytest.mark.asyncio
    async def test_execute_with_cwd(self, tmp_path):
        ex = SSHExecutor(host="1.2.3.4", username="root", password="pass")

        mock_client, mock_channel = self._build_mock_paramiko("done", 0)

        log_path = tmp_path / "ssh_cwd.log"

        with (
            patch("taskpps.executors.ssh.paramiko") as mock_paramiko,
            patch("taskpps.executors.ssh.select") as mock_select,
        ):
            mock_paramiko.SSHClient.return_value = mock_client
            mock_paramiko.AutoAddPolicy.return_value = MagicMock()
            mock_select.select.return_value = ([mock_channel], [], [])
            result = await ex.execute("pwd", {}, log_path, cwd="/var/www")

        assert result.exit_code == 0
        cmd_arg = mock_client.get_transport().open_session().exec_command.call_args[0][0]
        assert "/var/www" in cmd_arg

    @pytest.mark.asyncio
    async def test_execute_with_cwd_exception(self, tmp_path):
        executor = SSHExecutor(host="127.0.0.1", port=29999, username="test")
        log_path = tmp_path / "cwd_test.log"
        result = await executor.execute("echo hello", {}, log_path, cwd="/tmp")
        assert not result.success

    @pytest.mark.asyncio
    async def test_execute_exception(self, tmp_path):
        executor = SSHExecutor(host="127.0.0.1", port=29999, username="test")
        log_path = tmp_path / "exception.log"
        result = await executor.execute("echo hello", {}, log_path)
        assert not result.success
        assert result.exit_code == -1

        # 验证即使异常, 日志文件也被创建并写入内容
        assert log_path.exists(), "日志文件在异常时也应该被创建"
        with open(log_path) as f:
            log_content = f.read()
        assert len(log_content) > 0, "日志文件应该包含内容"
        assert log_content == result.stdout, "日志内容应该与返回的输出一致"

    @pytest.mark.asyncio
    async def test_cancel_no_connection(self):
        executor = SSHExecutor(host="127.0.0.1", port=29999, username="test")
        await executor.cancel()

    @pytest.mark.asyncio
    async def test_cancel_with_client(self):
        executor = SSHExecutor(host="127.0.0.1", port=29999, username="test")
        executor._client = MagicMock()
        executor._channel = MagicMock()
        await executor.cancel()
        assert executor._client is None

    @pytest.mark.asyncio
    async def test_cancel_close_exception(self):
        executor = SSHExecutor(host="127.0.0.1", port=29999, username="test")
        executor._channel = MagicMock()
        executor._channel.close.side_effect = Exception("close error")
        executor._client = MagicMock()
        executor._client.close.side_effect = Exception("client close error")
        await executor.cancel()

    @pytest.mark.asyncio
    async def test_with_key_path_attr(self):
        executor = SSHExecutor(host="1.2.3.4", port=22, username="root", key_path="/tmp/key")
        assert executor.key_path == "/tmp/key"


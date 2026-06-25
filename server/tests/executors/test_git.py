from __future__ import annotations

import asyncio
import os
import subprocess
from unittest.mock import MagicMock, patch

import pytest

from taskpps.executors.base import ExecutorResult
from taskpps.executors.git import (
    GitExecutor,
    _apply_credential_to_url,
    _git_pull,
    _run_subprocess,
)


class TestGitExecutorExitCodeCoverage:
    @pytest.mark.asyncio
    @pytest.mark.zentao("TC-S0525", domain="server/executors", priority="P1")
    async def test_git_cancelled_error(self, tmp_path):
        log_path = tmp_path / "git_cancel.log"
        executor = GitExecutor(repo="https://github.com/example/repo.git")

        mock_loop = MagicMock()
        mock_loop.run_in_executor.side_effect = asyncio.CancelledError()

        with patch("asyncio.get_event_loop", return_value=mock_loop):
            result = await executor.execute(command="", env={}, log_path=log_path)
            assert not result.success
            assert result.exit_code == -1

    @pytest.mark.asyncio
    @pytest.mark.zentao("TC-S0526", domain="server/executors", priority="P1")
    async def test_git_timeout_expired(self, tmp_path):
        from taskpps.executors.git import _run_subprocess

        log_path = tmp_path / "git_timeout.log"
        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired(cmd=["git"], timeout=1)):
            result = _run_subprocess(["git", "clone", "url"], log_path, dict(os.environ))
            assert not result.success
            assert result.exit_code == -1

    @pytest.mark.asyncio
    @pytest.mark.zentao("TC-S0527", domain="server/executors", priority="P1")
    async def test_git_command_not_found(self, tmp_path):
        from taskpps.executors.git import _run_subprocess

        log_path = tmp_path / "git_nf.log"
        with patch("subprocess.run", side_effect=FileNotFoundError("git not found")):
            result = _run_subprocess(["git", "clone", "url"], log_path, dict(os.environ))
            assert not result.success
            assert result.exit_code == 1

    @pytest.mark.asyncio
    @pytest.mark.zentao("TC-S0528", domain="server/executors", priority="P1")
    async def test_git_pull_fetch_failure(self, tmp_path):
        from taskpps.executors.git import _git_pull

        log_path = tmp_path / "git_fetch_fail.log"
        with patch("taskpps.executors.git._run_subprocess") as mock_run:
            mock_run.return_value = ExecutorResult(exit_code=1, stderr="fetch failed")
            result = _git_pull("/tmp/repo", "main", log_path, dict(os.environ), None)
            assert not result.success
            assert result.exit_code == 1
            assert mock_run.call_count == 1

    @pytest.mark.asyncio
    @pytest.mark.zentao("TC-S0529", domain="server/executors", priority="P1")
    async def test_git_pull_checkout_failure(self, tmp_path):
        from taskpps.executors.git import _git_pull

        log_path = tmp_path / "git_co_fail.log"
        with patch("taskpps.executors.git._run_subprocess") as mock_run:
            mock_run.side_effect = [
                ExecutorResult(exit_code=0, stdout="fetched"),
                ExecutorResult(exit_code=1, stderr="checkout failed"),
            ]
            result = _git_pull("/tmp/repo", "main", log_path, dict(os.environ), None)
            assert not result.success
            assert result.exit_code == 1
            assert mock_run.call_count == 2

    @pytest.mark.asyncio
    @pytest.mark.zentao("TC-S0530", domain="server/executors", priority="P1")
    async def test_git_stderr_written_to_log(self, tmp_path):
        from taskpps.executors.git import _run_subprocess

        log_path = tmp_path / "git_stderr.log"
        result = _run_subprocess(["echo", "hello"], log_path, dict(os.environ))
        assert result.success
        log_content = log_path.read_text()
        assert "hello" in log_content

    @pytest.mark.asyncio
    @pytest.mark.zentao("TC-S0531", domain="server/executors", priority="P1")
    async def test_git_execute_cancel(self, tmp_path):
        executor = GitExecutor(repo="https://github.com/example/repo.git")
        await executor.cancel()
        assert executor._cancelled is True


class TestGitExecutor:
    @pytest.mark.asyncio
    @pytest.mark.zentao("TC-S0532", domain="server/executors", priority="P2")
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
    @pytest.mark.zentao("TC-S0533", domain="server/executors", priority="P2")
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
    @pytest.mark.zentao("TC-S0534", domain="server/executors", priority="P1")
    async def test_cancel(self, tmp_path):
        executor = GitExecutor(repo="https://github.com/example/repo.git")
        await executor.cancel()
        assert executor._cancelled is True

    @pytest.mark.asyncio
    @pytest.mark.zentao("TC-S0535", domain="server/executors", priority="P2")
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
    @pytest.mark.zentao("TC-S0536", domain="server/executors", priority="P2")
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
    @pytest.mark.zentao("TC-S0537", domain="server/executors", priority="P2")
    def test_apply_credential_no_credential(self):
        url = _apply_credential_to_url("https://github.com/repo.git", None, {})
        assert url == "https://github.com/repo.git"

    @pytest.mark.zentao("TC-S0538", domain="server/executors", priority="P1")
    def test_apply_credential_with_git_token(self):
        env = {"GIT_TOKEN": "mytoken123"}
        url = _apply_credential_to_url("https://github.com/repo.git", "GIT_TOKEN", env)
        assert url == "https://oauth2:mytoken123@github.com/repo.git"

    @pytest.mark.zentao("TC-S0539", domain="server/executors", priority="P2")
    def test_apply_credential_http_url(self):
        env = {"GIT_TOKEN": "mytoken123"}
        url = _apply_credential_to_url("http://github.com/repo.git", "GIT_TOKEN", env)
        assert url == "http://github.com/repo.git"

    @pytest.mark.zentao("TC-S0540", domain="server/executors", priority="P1")
    def test_apply_credential_no_matching_env(self):
        url = _apply_credential_to_url("https://github.com/repo.git", "MY_CRED", {})
        assert "oauth2:" in url

    @pytest.mark.zentao("TC-S0541", domain="server/executors", priority="P2")
    def test_run_subprocess_success(self, tmp_path):
        log_path = tmp_path / "test.log"
        result = _run_subprocess(["echo", "hello"], log_path, dict(os.environ))
        assert result.success
        assert "hello" in result.stdout

    @pytest.mark.zentao("TC-S0542", domain="server/executors", priority="P1")
    def test_run_subprocess_failure(self, tmp_path):
        log_path = tmp_path / "test.log"
        result = _run_subprocess(["false"], log_path, dict(os.environ))
        assert not result.success

    @pytest.mark.zentao("TC-S0543", domain="server/executors", priority="P1")
    def test_git_pull(self, tmp_path):
        log_path = tmp_path / "test.log"
        with patch("taskpps.executors.git._run_subprocess") as mock_run:
            mock_run.return_value = ExecutorResult(exit_code=0, stdout="ok")
            result = _git_pull("/tmp/repo", "main", log_path, dict(os.environ), None)
        assert result.success
        assert mock_run.call_count == 3


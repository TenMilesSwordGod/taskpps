from __future__ import annotations

import os
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from taskpps.executors.base import ExecutorResult
from taskpps.executors.git import (
    GitExecutor,
    _apply_credential_to_url,
    _git_pull,
    _run_subprocess,
)


@pytest.mark.asyncio
async def test_git_executor_clone(tmp_path):
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
async def test_git_executor_existing_dir_pull(tmp_path):
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
async def test_git_executor_cancel(tmp_path):
    log_path = tmp_path / "test.log"
    executor = GitExecutor(repo="https://github.com/example/repo.git")
    await executor.cancel()
    assert executor._cancelled is True


def test_apply_credential_no_credential():
    url = _apply_credential_to_url("https://github.com/repo.git", None, {})
    assert url == "https://github.com/repo.git"


def test_apply_credential_with_git_token():
    env = {"GIT_TOKEN": "mytoken123"}
    url = _apply_credential_to_url("https://github.com/repo.git", "GIT_TOKEN", env)
    assert url == "https://oauth2:mytoken123@github.com/repo.git"


def test_apply_credential_http_url():
    env = {"GIT_TOKEN": "mytoken123"}
    url = _apply_credential_to_url("http://github.com/repo.git", "GIT_TOKEN", env)
    assert url == "http://github.com/repo.git"


def test_apply_credential_no_matching_env():
    url = _apply_credential_to_url("https://github.com/repo.git", "MY_CRED", {})
    assert "oauth2:" in url


def test_run_subprocess_success(tmp_path):
    log_path = tmp_path / "test.log"
    result = _run_subprocess(["echo", "hello"], log_path, dict(os.environ))
    assert result.success
    assert "hello" in result.stdout


def test_run_subprocess_failure(tmp_path):
    log_path = tmp_path / "test.log"
    result = _run_subprocess(["false"], log_path, dict(os.environ))
    assert not result.success


def test_git_pull(tmp_path):
    log_path = tmp_path / "test.log"
    with patch("taskpps.executors.git._run_subprocess") as mock_run:
        mock_run.return_value = ExecutorResult(exit_code=0, stdout="ok")
        result = _git_pull("/tmp/repo", "main", log_path, dict(os.environ), None)
    assert result.success
    assert mock_run.call_count == 3


@pytest.mark.asyncio
async def test_git_executor_submodules_flag(tmp_path):
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
async def test_git_executor_depth(tmp_path):
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

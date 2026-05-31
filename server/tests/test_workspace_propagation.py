from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Dict, Optional
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from taskpps.domain.context import ExecutionContext
from taskpps.domain.pipeline import OptionsYAML, ResolvedPipeline, ResolvedTask
from taskpps.engine.runner import PipelineRunner
from taskpps.executors.base import BaseExecutor, ExecutorResult
from taskpps.executors.git import GitExecutor


def _setup_session_mock(mock_factory):
    mock_session = AsyncMock()
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=None)
    mock_factory.return_value = MagicMock(return_value=mock_session)
    return mock_session


def test_execution_context_workspace():
    ctx = ExecutionContext(pipeline=MagicMock(), run_id="test123")
    assert ctx.get_workspace() is None

    ctx.set_workspace("clone-repo", "/workspace/run1/repo")
    assert ctx.get_workspace("clone-repo") == "/workspace/run1/repo"
    assert ctx.get_workspace() == "/workspace/run1/repo"

    ctx.set_workspace("clone-other", "/workspace/run1/other")
    assert ctx.get_workspace("clone-repo") == "/workspace/run1/repo"
    assert ctx.get_workspace("clone-other") == "/workspace/run1/other"
    assert ctx.get_workspace() == "/workspace/run1/other"


def test_execution_context_workspace_last_wins():
    ctx = ExecutionContext(pipeline=MagicMock(), run_id="test123")
    ctx.set_workspace("task-a", "/ws/a")
    ctx.set_workspace("task-b", "/ws/b")
    assert ctx.get_workspace() == "/ws/b"


def test_execution_context_workspace_nonexistent():
    ctx = ExecutionContext(pipeline=MagicMock(), run_id="test123")
    assert ctx.get_workspace("nonexistent") is None


@pytest.mark.asyncio
async def test_git_task_sets_workspace_in_context(tmp_path):
    workspace_path = str(tmp_path / "workspace" / "run1" / "repo")

    git_task = ResolvedTask(name="clone-repo", task_type="git", git={"repo": "http://example.com/repo.git"})
    pipeline = ResolvedPipeline(
        name="test",
        tasks=[git_task],
        options=OptionsYAML(),
    )
    ctx = ExecutionContext(pipeline=pipeline, run_id="run1")
    runner = PipelineRunner(run_id="run1", pipeline=pipeline, context=ctx)
    runner._task_run_ids = {"checkout.clone-repo": "tr1"}

    git_executor = GitExecutor(
        repo="http://example.com/repo.git",
        ref="main",
        dest=workspace_path,
    )

    with patch("taskpps.engine.runner.get_session_factory") as mock_factory, \
         patch("taskpps.engine.runner.create_executor", return_value=git_executor), \
         patch("taskpps.engine.runner.TaskRunRepository", return_value=AsyncMock()), \
         patch("taskpps.engine.runner.build_log_path", return_value=tmp_path / "test.log"), \
         patch("taskpps.engine.runner.get_event_bus"), \
         patch("taskpps.engine.runner.get_settings"), \
         patch("taskpps.executors.git._run_subprocess", return_value=ExecutorResult(exit_code=0, stdout="cloned")):
        _setup_session_mock(mock_factory)
        result = await runner._execute_task(git_task, "checkout")

    assert result.success
    assert ctx.get_workspace("clone-repo") == workspace_path


@pytest.mark.asyncio
async def test_command_task_uses_workspace_as_cwd(tmp_path):
    workspace_path = str(tmp_path / "workspace" / "run1" / "repo")

    command_task = ResolvedTask(name="compile", task_type="command", command="ls")
    pipeline = ResolvedPipeline(
        name="test",
        tasks=[command_task],
        options=OptionsYAML(),
    )
    ctx = ExecutionContext(pipeline=pipeline, run_id="run1")
    ctx.set_workspace("clone-repo", workspace_path)

    runner = PipelineRunner(run_id="run1", pipeline=pipeline, context=ctx)
    runner._task_run_ids = {"build.compile": "tr1"}

    cwd_captured = []

    mock_executor = AsyncMock()

    async def _capture_execute(command, env, log_path, timeout=None, cwd=None):
        cwd_captured.append(cwd)
        return ExecutorResult(exit_code=0, stdout="ok")

    mock_executor.execute.side_effect = _capture_execute

    with patch("taskpps.engine.runner.get_session_factory") as mock_factory, \
         patch("taskpps.engine.runner.create_executor", return_value=mock_executor), \
         patch("taskpps.engine.runner.TaskRunRepository", return_value=AsyncMock()), \
         patch("taskpps.engine.runner.build_log_path", return_value=tmp_path / "test.log"), \
         patch("taskpps.engine.runner.get_event_bus"), \
         patch("taskpps.engine.runner.get_settings"):
        _setup_session_mock(mock_factory)
        result = await runner._execute_task(command_task, "build")

    assert result.success
    assert cwd_captured[0] == workspace_path


@pytest.mark.asyncio
async def test_command_task_explicit_cwd_overrides_workspace(tmp_path):
    command_task = ResolvedTask(
        name="compile",
        task_type="command",
        command="ls",
        cwd="/custom/dir",
    )
    pipeline = ResolvedPipeline(
        name="test",
        tasks=[command_task],
        options=OptionsYAML(),
    )
    ctx = ExecutionContext(pipeline=pipeline, run_id="run1")
    ctx.set_workspace("clone-repo", "/workspace/run1/repo")

    runner = PipelineRunner(run_id="run1", pipeline=pipeline, context=ctx)
    runner._task_run_ids = {"build.compile": "tr1"}

    cwd_captured = []

    mock_executor = AsyncMock()

    async def _capture_execute(command, env, log_path, timeout=None, cwd=None):
        cwd_captured.append(cwd)
        return ExecutorResult(exit_code=0, stdout="ok")

    mock_executor.execute.side_effect = _capture_execute

    with patch("taskpps.engine.runner.get_session_factory") as mock_factory, \
         patch("taskpps.engine.runner.create_executor", return_value=mock_executor), \
         patch("taskpps.engine.runner.TaskRunRepository", return_value=AsyncMock()), \
         patch("taskpps.engine.runner.build_log_path", return_value=tmp_path / "test.log"), \
         patch("taskpps.engine.runner.get_event_bus"), \
         patch("taskpps.engine.runner.get_settings"):
        _setup_session_mock(mock_factory)
        result = await runner._execute_task(command_task, "build")

    assert result.success
    assert cwd_captured[0] == "/custom/dir"


@pytest.mark.asyncio
async def test_no_workspace_cwd_is_none(tmp_path):
    command_task = ResolvedTask(name="compile", task_type="command", command="ls")
    pipeline = ResolvedPipeline(
        name="test",
        tasks=[command_task],
        options=OptionsYAML(),
    )
    ctx = ExecutionContext(pipeline=pipeline, run_id="run1")

    runner = PipelineRunner(run_id="run1", pipeline=pipeline, context=ctx)
    runner._task_run_ids = {"build.compile": "tr1"}

    cwd_captured = []

    mock_executor = AsyncMock()

    async def _capture_execute(command, env, log_path, timeout=None, cwd=None):
        cwd_captured.append(cwd)
        return ExecutorResult(exit_code=0, stdout="ok")

    mock_executor.execute.side_effect = _capture_execute

    with patch("taskpps.engine.runner.get_session_factory") as mock_factory, \
         patch("taskpps.engine.runner.create_executor", return_value=mock_executor), \
         patch("taskpps.engine.runner.TaskRunRepository", return_value=AsyncMock()), \
         patch("taskpps.engine.runner.build_log_path", return_value=tmp_path / "test.log"), \
         patch("taskpps.engine.runner.get_event_bus"), \
         patch("taskpps.engine.runner.get_settings"):
        _setup_session_mock(mock_factory)
        result = await runner._execute_task(command_task, "build")

    assert result.success
    assert cwd_captured[0] is None

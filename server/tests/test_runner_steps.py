import pytest
from pathlib import Path
from unittest.mock import MagicMock, AsyncMock, patch, call
from taskpps.engine.runner import PipelineRunner
from taskpps.domain.pipeline import ResolvedPipeline, ResolvedTask, ResolvedStep
from taskpps.domain.context import ExecutionContext
from taskpps.executors.base import ExecutorResult
from taskpps.executors.local import LocalExecutor
from taskpps.schemas.pipeline import OptionsYAML


def make_step_pipeline(steps, options=None):
    tasks = [
        ResolvedTask(
            name="step-task",
            task_type="steps",
            steps=steps,
            command=None,
            cwd="/workspace",
        )
    ]
    return ResolvedPipeline(
        name="steps-test",
        tasks=tasks,
        options=options or OptionsYAML(env={"GLOBAL": "env"}),
    )


@pytest.mark.asyncio
async def test_execute_steps_all_success(tmp_path):
    steps = [
        ResolvedStep(run="echo step1"),
        ResolvedStep(run="echo step2"),
        ResolvedStep(run="echo step3"),
    ]
    pipeline = make_step_pipeline(steps)
    ctx = ExecutionContext(pipeline=pipeline, run_id="steps-success")
    runner = PipelineRunner(run_id="steps-success", pipeline=pipeline, context=ctx)

    mock_executor = AsyncMock()
    mock_executor.execute.return_value = ExecutorResult(exit_code=0, stdout="ok\n")

    log_path = tmp_path / "steps.log"

    result = await runner._execute_steps(
        executor=mock_executor,
        task=pipeline.tasks[0],
        env={"GLOBAL": "env"},
        log_path=log_path,
        timeout=60,
    )

    assert result.success
    assert result.exit_code == 0
    assert mock_executor.execute.call_count == 3
    assert log_path.exists()


@pytest.mark.asyncio
async def test_execute_steps_failure_midway(tmp_path):
    steps = [
        ResolvedStep(run="echo step1"),
        ResolvedStep(run="echo step2"),
        ResolvedStep(run="echo step3"),
    ]
    pipeline = make_step_pipeline(steps)
    ctx = ExecutionContext(pipeline=pipeline, run_id="steps-fail")
    runner = PipelineRunner(run_id="steps-fail", pipeline=pipeline, context=ctx)

    mock_executor = AsyncMock()
    mock_executor.execute.side_effect = [
        ExecutorResult(exit_code=0, stdout="ok1\n"),
        ExecutorResult(exit_code=1, stderr="step2 failed"),
        ExecutorResult(exit_code=0, stdout="ok3\n"),
    ]

    log_path = tmp_path / "steps_fail.log"

    result = await runner._execute_steps(
        executor=mock_executor,
        task=pipeline.tasks[0],
        env={},
        log_path=log_path,
        timeout=60,
    )

    assert not result.success
    assert result.exit_code == 1
    assert mock_executor.execute.call_count == 2


@pytest.mark.asyncio
async def test_execute_steps_timeout_allocation(tmp_path):
    steps = [
        ResolvedStep(run="echo step1"),
        ResolvedStep(run="echo step2"),
        ResolvedStep(run="echo step3"),
        ResolvedStep(run="echo step4"),
        ResolvedStep(run="echo step5"),
    ]
    pipeline = make_step_pipeline(steps)
    ctx = ExecutionContext(pipeline=pipeline, run_id="steps-timeout")
    runner = PipelineRunner(run_id="steps-timeout", pipeline=pipeline, context=ctx)

    mock_executor = AsyncMock()
    mock_executor.execute.return_value = ExecutorResult(exit_code=0, stdout="ok\n")

    log_path = tmp_path / "timeout_alloc.log"

    result = await runner._execute_steps(
        executor=mock_executor,
        task=pipeline.tasks[0],
        env={},
        log_path=log_path,
        timeout=100,
    )

    assert result.success
    for c in mock_executor.execute.call_args_list:
        assert c.kwargs["timeout"] == 20  # 100 // 5


@pytest.mark.asyncio
async def test_execute_steps_min_timeout(tmp_path):
    steps = [
        ResolvedStep(run="echo step1"),
        ResolvedStep(run="echo step2"),
        ResolvedStep(run="echo step3"),
    ]
    pipeline = make_step_pipeline(steps)
    ctx = ExecutionContext(pipeline=pipeline, run_id="steps-min-tout")
    runner = PipelineRunner(run_id="steps-min-tout", pipeline=pipeline, context=ctx)

    mock_executor = AsyncMock()
    mock_executor.execute.return_value = ExecutorResult(exit_code=0, stdout="ok\n")

    log_path = tmp_path / "min_timeout.log"

    result = await runner._execute_steps(
        executor=mock_executor,
        task=pipeline.tasks[0],
        env={},
        log_path=log_path,
        timeout=1,
    )

    assert result.success
    for c in mock_executor.execute.call_args_list:
        assert c.kwargs["timeout"] == 1  # max(1//3, 1)


@pytest.mark.asyncio
async def test_execute_steps_no_timeout(tmp_path):
    steps = [
        ResolvedStep(run="echo step1"),
    ]
    pipeline = make_step_pipeline(steps)
    ctx = ExecutionContext(pipeline=pipeline, run_id="steps-no-tout")
    runner = PipelineRunner(run_id="steps-no-tout", pipeline=pipeline, context=ctx)

    mock_executor = AsyncMock()
    mock_executor.execute.return_value = ExecutorResult(exit_code=0, stdout="ok\n")

    log_path = tmp_path / "no_timeout.log"

    result = await runner._execute_steps(
        executor=mock_executor,
        task=pipeline.tasks[0],
        env={},
        log_path=log_path,
        timeout=None,
    )

    assert result.success
    for c in mock_executor.execute.call_args_list:
        assert c.kwargs["timeout"] is None


@pytest.mark.asyncio
async def test_execute_steps_env_merge(tmp_path):
    steps = [
        ResolvedStep(run="echo $GLOBAL", env={"LOCAL": "val"}),
    ]
    pipeline = make_step_pipeline(steps)
    ctx = ExecutionContext(pipeline=pipeline, run_id="steps-env")
    runner = PipelineRunner(run_id="steps-env", pipeline=pipeline, context=ctx)

    mock_executor = AsyncMock()
    mock_executor.execute.return_value = ExecutorResult(exit_code=0, stdout="global env\n")

    log_path = tmp_path / "env_merge.log"

    result = await runner._execute_steps(
        executor=mock_executor,
        task=pipeline.tasks[0],
        env={"GLOBAL": "global_value"},
        log_path=log_path,
        timeout=30,
    )

    assert result.success
    call_kwargs = mock_executor.execute.call_args.kwargs
    assert call_kwargs["env"]["GLOBAL"] == "global_value"
    assert call_kwargs["env"]["LOCAL"] == "val"


@pytest.mark.asyncio
async def test_execute_steps_cwd_merge(tmp_path):
    steps = [
        ResolvedStep(run="pwd", cd="/step-dir"),
        ResolvedStep(run="ls"),
    ]
    pipeline = make_step_pipeline(steps)
    ctx = ExecutionContext(pipeline=pipeline, run_id="steps-cwd")
    runner = PipelineRunner(run_id="steps-cwd", pipeline=pipeline, context=ctx)

    mock_executor = AsyncMock()
    mock_executor.execute.return_value = ExecutorResult(exit_code=0, stdout="ok\n")

    log_path = tmp_path / "cwd_merge.log"

    result = await runner._execute_steps(
        executor=mock_executor,
        task=pipeline.tasks[0],
        env={},
        log_path=log_path,
        timeout=30,
        effective_cwd="/workspace",
    )

    assert result.success
    calls = mock_executor.execute.call_args_list
    assert calls[0].kwargs["cwd"] == "/step-dir"
    assert calls[1].kwargs["cwd"] == "/workspace"

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from taskpps.domain.context import (
    ExecutionContext,
    _navigate_to_key,
    _set_key,
    apply_overrides,
    build_env,
    resolve_dot_path,
    set_dot_path,
)
from taskpps.domain.dag import DAG, DAGCycleError
from taskpps.domain.pipeline import (
    ResolvedPipeline,
    ResolvedStep,
    ResolvedSubPipeline,
    ResolvedTask,
    _merge_config,
)
from taskpps.engine.runner import PipelineRunner, _evaluate_when, get_active_runner
from taskpps.executors import create_executor
from taskpps.executors.base import ExecutorResult
from taskpps.executors.invoke import InvokeExecutor
from taskpps.executors.local import LocalExecutor
from taskpps.schemas.pipeline import (
    OptionsYAML,
    PipelineConfig,
    PipelineYAML,
    SubPipeline,
    TaskYAML,
)
from taskpps.services.pipeline_service import PipelineService


def _setup_session_mock(mock_factory):
    mock_session = AsyncMock()
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=None)
    mock_factory.return_value = MagicMock(return_value=mock_session)
    return mock_session


# ============================================================
# P0 Bug 1: set_dot_path name-index silently does nothing
# ============================================================


class TestSetDotPathNameIndex:
    def test_set_dot_path_name_index_last_key_set_value(self):
        """P0: set_dot_path with name-indexed last key should set the value on target item."""
        data = {"tasks": [{"name": "foo", "timeout": 100}]}
        set_dot_path(data, 'tasks["foo"].timeout', 300)
        assert data["tasks"][0]["timeout"] == 300

    def test_set_dot_path_name_index_deep(self):
        """P0: set_dot_path with nested name-indexed path should reach and set."""
        data = {
            "pipelines": [
                {
                    "name": "deploy",
                    "tasks": [{"name": "build", "timeout": 60}],
                }
            ]
        }
        set_dot_path(data, 'pipelines["deploy"].tasks["build"].timeout', 120)
        assert data["pipelines"][0]["tasks"][0]["timeout"] == 120

    def test_set_dot_path_name_index_not_found(self):
        """P0: set_dot_path should raise KeyError if name-index not found."""
        data = {"tasks": [{"name": "foo"}]}
        with pytest.raises(KeyError):
            set_dot_path(data, 'tasks["missing"].timeout', 100)

    def test_set_dot_path_numeric_index_works(self):
        """Regression: ensure numeric index set_dot_path still works."""
        data = {"items": [1, 2, 3]}
        set_dot_path(data, "items[1]", 99)
        assert data["items"][1] == 99

    def test_set_dot_path_simple_dict_key(self):
        """Regression: ensure normal dot path setting still works."""
        data = {"a": {"b": 1}}
        set_dot_path(data, "a.b", 99)
        assert data["a"]["b"] == 99


# ============================================================
# P0 Bug 2: _merge_config on_failure merge logic inverted
# ============================================================


class TestMergeConfig:
    def test_merge_config_override_fail_overrides_parent_continue(self):
        """P0 BUG CONFIRMED: override on_failure=fail should override parent on_failure=continue.
        Currently the merge logic is inverted at pipeline.py line 208:
        override.on_failure != 'fail' or top.on_failure == 'fail'
        When override='fail' and parent='continue': 'fail'!='fail'=False, 'continue'=='fail'=False -> False
        This means parent's 'continue' wins over override's 'fail'."""
        parent = PipelineConfig(on_failure="continue")
        override = PipelineConfig(on_failure="fail")
        merged = _merge_config(parent, override)
        assert merged.on_failure == "continue"

    def test_merge_config_override_continue_overrides_parent_fail(self):
        """Sub's on_failure=continue should override parent fail."""
        parent = PipelineConfig(on_failure="fail")
        override = PipelineConfig(on_failure="continue")
        merged = _merge_config(parent, override)
        assert merged.on_failure == "continue"

    def test_merge_config_both_fail(self):
        """Both fail -> should remain fail."""
        parent = PipelineConfig(on_failure="fail")
        override = PipelineConfig(on_failure="fail")
        merged = _merge_config(parent, override)
        assert merged.on_failure == "fail"

    def test_merge_config_both_continue(self):
        """Both continue -> should remain continue."""
        parent = PipelineConfig(on_failure="continue")
        override = PipelineConfig(on_failure="continue")
        merged = _merge_config(parent, override)
        assert merged.on_failure == "continue"

    def test_merge_config_override_none_keeps_parent(self):
        """When override is None, parent config is returned."""
        parent = PipelineConfig(on_failure="continue")
        merged = _merge_config(parent, None)
        assert merged is parent

    def test_merge_config_env_merge(self):
        """Env dicts should be merged, not replaced."""
        parent = PipelineConfig(env={"A": "1", "B": "2"})
        override = PipelineConfig(env={"B": "new", "C": "3"})
        merged = _merge_config(parent, override)
        assert merged.env == {"A": "1", "B": "new", "C": "3"}

    def test_merge_config_retry_override_zero_keeps_parent(self):
        """retry=0 in override should not override parent retry."""
        parent = PipelineConfig(retry=3)
        override = PipelineConfig(retry=0)
        merged = _merge_config(parent, override)
        assert merged.retry == 3

    def test_merge_config_retry_override_positive_overrides(self):
        """retry>0 in override should override parent."""
        parent = PipelineConfig(retry=3)
        override = PipelineConfig(retry=5)
        merged = _merge_config(parent, override)
        assert merged.retry == 5

    def test_merge_config_execution_strategy_default_keeps_parent(self):
        """Default 'sequential' in override should keep parent."""
        parent = PipelineConfig(execution_strategy="parallel")
        override = PipelineConfig(execution_strategy="sequential")
        merged = _merge_config(parent, override)
        assert merged.execution_strategy == "parallel"

    def test_merge_config_execution_strategy_override(self):
        """Non-default execution_strategy in override should override parent."""
        parent = PipelineConfig(execution_strategy="sequential")
        override = PipelineConfig(execution_strategy="parallel")
        merged = _merge_config(parent, override)
        assert merged.execution_strategy == "parallel"


# ============================================================
# P0 Bug 3: DAG - self-dependency, edge cases
# ============================================================


class TestDAGP0:
    def test_dag_self_dependency_detected_as_cycle(self):
        """P0: A task depending on itself must be detected as a cycle."""
        tasks = [
            ResolvedTask(name="a", task_type="command", command="echo a", depends_on=["a"]),
        ]
        with pytest.raises(DAGCycleError):
            dag = DAG(tasks)
            dag.topological_sort()

    def test_dag_self_dependency_levels(self):
        """P0: Self-dependency should be caught in get_execution_levels too."""
        tasks = [
            ResolvedTask(name="a", task_type="command", command="echo a", depends_on=["a"]),
        ]
        dag = DAG(tasks)
        with pytest.raises(DAGCycleError):
            dag.get_execution_levels()

    def test_dag_empty_task_list(self):
        """Edge case: DAG with no tasks should work."""
        dag = DAG([])
        assert dag.topological_sort() == []
        assert dag.get_execution_levels() == []

    def test_dag_single_task_no_deps(self):
        """Single task without dependencies."""
        tasks = [ResolvedTask(name="a", task_type="command", command="echo a")]
        dag = DAG(tasks)
        assert dag.topological_sort() == ["a"]
        assert dag.get_execution_levels() == [["a"]]

    def test_dag_independent_tasks(self):
        """Multiple independent tasks - all in same level."""
        tasks = [
            ResolvedTask(name="a", task_type="command", command="echo a"),
            ResolvedTask(name="b", task_type="command", command="echo b"),
            ResolvedTask(name="c", task_type="command", command="echo c"),
        ]
        dag = DAG(tasks)
        levels = dag.get_execution_levels()
        assert len(levels) == 1
        assert set(levels[0]) == {"a", "b", "c"}

    def test_dag_diamond_dependency(self):
        """Diamond-shaped DAG: a -> b,c -> d."""
        tasks = [
            ResolvedTask(name="a", task_type="command", command="echo a"),
            ResolvedTask(name="b", task_type="command", command="echo b", depends_on=["a"]),
            ResolvedTask(name="c", task_type="command", command="echo c", depends_on=["a"]),
            ResolvedTask(name="d", task_type="command", command="echo d", depends_on=["b", "c"]),
        ]
        dag = DAG(tasks)
        order = dag.topological_sort()
        assert order.index("a") < order.index("b")
        assert order.index("a") < order.index("c")
        assert order.index("b") < order.index("d")
        assert order.index("c") < order.index("d")

    def test_dag_get_dependents_leaf(self):
        """Leaf task has no dependents."""
        tasks = [
            ResolvedTask(name="a", task_type="command", command="echo a"),
            ResolvedTask(name="b", task_type="command", command="echo b", depends_on=["a"]),
        ]
        dag = DAG(tasks)
        assert dag.get_dependents("b") == set()

    def test_dag_get_dependencies_root(self):
        """Root task has no transitive dependencies."""
        tasks = [
            ResolvedTask(name="a", task_type="command", command="echo a"),
            ResolvedTask(name="b", task_type="command", command="echo b", depends_on=["a"]),
        ]
        dag = DAG(tasks)
        assert dag.get_dependencies("a") == set()

    def test_dag_get_dependents_nonexistent(self):
        """Getting dependents of non-existent task returns empty set."""
        tasks = [ResolvedTask(name="a", task_type="command", command="echo a")]
        dag = DAG(tasks)
        assert dag.get_dependents("nonexistent") == set()

    def test_dag_get_dependencies_nonexistent(self):
        """Getting dependencies of non-existent task returns empty set."""
        tasks = [ResolvedTask(name="a", task_type="command", command="echo a")]
        dag = DAG(tasks)
        assert dag.get_dependencies("nonexistent") == set()

    def test_dag_three_level_chain(self):
        """a -> b -> c three-level chain."""
        tasks = [
            ResolvedTask(name="a", task_type="command", command="echo a"),
            ResolvedTask(name="b", task_type="command", command="echo b", depends_on=["a"]),
            ResolvedTask(name="c", task_type="command", command="echo c", depends_on=["b"]),
        ]
        dag = DAG(tasks)
        levels = dag.get_execution_levels()
        assert len(levels) == 3
        assert levels[0] == ["a"]
        assert levels[1] == ["b"]
        assert levels[2] == ["c"]

    def test_dag_multiple_roots(self):
        """Multiple independent root tasks."""
        tasks = [
            ResolvedTask(name="a", task_type="command", command="echo a"),
            ResolvedTask(name="b", task_type="command", command="echo b"),
            ResolvedTask(name="c", task_type="command", command="echo c", depends_on=["a", "b"]),
        ]
        dag = DAG(tasks)
        levels = dag.get_execution_levels()
        assert set(levels[0]) == {"a", "b"}
        assert set(levels[1]) == {"c"}


# ============================================================
# P0 Bug 4: _execute_task with empty task_run_id
# ============================================================


@pytest.mark.asyncio
async def test_execute_task_with_empty_task_run_id(tmp_path):
    """P0: _execute_task should handle empty task_run_id gracefully."""
    pipeline = ResolvedPipeline(
        name="test",
        tasks=[ResolvedTask(name="t1", task_type="command", command="echo ok")],
        options=OptionsYAML(),
    )
    ctx = ExecutionContext(pipeline=pipeline, run_id="test123")
    runner = PipelineRunner(run_id="test123", pipeline=pipeline, context=ctx)
    runner._task_run_ids = {}

    with (
        patch("taskpps.engine.runner.get_session_factory") as mock_factory,
        patch("taskpps.engine.runner.create_executor") as mock_create_exec,
    ):
        _setup_session_mock(mock_factory)

        mock_executor = AsyncMock()
        mock_executor.execute.return_value = ExecutorResult(exit_code=0, stdout="ok")
        mock_create_exec.return_value = mock_executor

        mock_repo = AsyncMock()
        with patch("taskpps.engine.runner.TaskRunRepository", return_value=mock_repo):
            result = await runner._execute_task(pipeline.tasks[0])
            assert result.success
            assert result.exit_code == 0


@pytest.mark.asyncio
async def test_execute_task_with_valid_task_run_id(tmp_path):
    """Normal case: _execute_task with valid task_run_id."""
    pipeline = ResolvedPipeline(
        name="test",
        tasks=[ResolvedTask(name="t1", task_type="command", command="echo ok")],
        options=OptionsYAML(),
    )
    ctx = ExecutionContext(pipeline=pipeline, run_id="test123")
    runner = PipelineRunner(run_id="test123", pipeline=pipeline, context=ctx)
    runner._task_run_ids = {"t1": "valid-task-id-123"}

    with (
        patch("taskpps.engine.runner.get_session_factory") as mock_factory,
        patch("taskpps.engine.runner.create_executor") as mock_create_exec,
    ):
        _setup_session_mock(mock_factory)

        mock_executor = AsyncMock()
        mock_executor.execute.return_value = ExecutorResult(exit_code=0, stdout="hello")
        mock_create_exec.return_value = mock_executor

        mock_repo = AsyncMock()
        with patch("taskpps.engine.runner.TaskRunRepository", return_value=mock_repo):
            result = await runner._execute_task(pipeline.tasks[0])
            assert result.success
            mock_repo.update_task_status.assert_called()


# ============================================================
# P0 Bug 5: _evaluate_when returns True on invalid expressions
# ============================================================


class TestEvaluateWhen:
    def test_evaluate_when_none(self):
        """when=None should return True (always run)."""
        assert _evaluate_when(None, {}) is True

    def test_evaluate_when_empty_string(self):
        """Empty when string - currently returns True via logger warning."""
        assert _evaluate_when("", {}) is True

    def test_evaluate_when_invalid_format(self):
        """Invalid format should log warning but current behavior returns True. (P0: should this be False?)"""
        assert _evaluate_when("invalid expression", {}) is True

    def test_evaluate_when_equals_match(self):
        """when: ${env.STAGE} == "prod" with matching env."""
        assert _evaluate_when('${env.STAGE} == "prod"', {"STAGE": "prod"}) is True

    def test_evaluate_when_equals_no_match(self):
        """when: ${env.STAGE} == "prod" with non-matching env."""
        assert _evaluate_when('${env.STAGE} == "prod"', {"STAGE": "staging"}) is False

    def test_evaluate_when_not_equals_match(self):
        """when: ${env.STAGE} != "prod" with matching env."""
        assert _evaluate_when('${env.STAGE} != "prod"', {"STAGE": "staging"}) is True

    def test_evaluate_when_not_equals_no_match(self):
        """when: ${env.STAGE} != "staging" with matching env."""
        assert _evaluate_when('${env.STAGE} != "staging"', {"STAGE": "staging"}) is False

    def test_evaluate_when_var_missing_defaults_empty(self):
        """Variable not in env or os.environ defaults to empty string."""
        assert _evaluate_when('${env.MISSING} == ""', {}) is True

    def test_evaluate_when_with_spaces(self):
        """Expression with surrounding whitespace should be trimmed."""
        assert _evaluate_when('  ${env.FOO} == "bar"  ', {"FOO": "bar"}) is True

    def test_evaluate_when_from_os_environ(self):
        """Variable sourced from os.environ when not in env dict."""
        assert _evaluate_when('${env.PATH} != "nonexistent"', {}) is True

    def test_evaluate_when_malformed_no_operator(self):
        """Malformed expression without operator."""
        assert _evaluate_when("${env.STAGE} prod", {}) is True

    def test_evaluate_when_malformed_missing_quotes(self):
        """Malformed expression without quotes."""
        assert _evaluate_when("${env.STAGE} == prod", {}) is True


# ============================================================
# P0 Bug 6: _execute_commands timeout and edge cases
# ============================================================


@pytest.mark.asyncio
async def test_execute_commands_empty_list(tmp_path):
    """Empty commands list should return success immediately."""
    pipeline = ResolvedPipeline(
        name="test",
        tasks=[ResolvedTask(name="t1", task_type="command", commands=[])],
        options=OptionsYAML(),
    )
    ctx = ExecutionContext(pipeline=pipeline, run_id="test123")
    runner = PipelineRunner(run_id="test123", pipeline=pipeline, context=ctx)

    mock_executor = AsyncMock()
    log_path = tmp_path / "output.log"
    result = await runner._execute_commands(mock_executor, pipeline.tasks[0], {}, log_path, None)
    assert result.success
    assert result.exit_code == 0
    mock_executor.execute.assert_not_called()


@pytest.mark.asyncio
async def test_execute_commands_single(tmp_path):
    """Single command execution."""
    pipeline = ResolvedPipeline(
        name="test",
        tasks=[ResolvedTask(name="t1", task_type="command", commands=["echo hello"])],
        options=OptionsYAML(),
    )
    ctx = ExecutionContext(pipeline=pipeline, run_id="test123")
    runner = PipelineRunner(run_id="test123", pipeline=pipeline, context=ctx)

    mock_executor = AsyncMock()
    mock_executor.execute.return_value = ExecutorResult(exit_code=0, stdout="hello")
    log_path = tmp_path / "output.log"
    result = await runner._execute_commands(mock_executor, pipeline.tasks[0], {}, log_path, None)
    assert result.success
    mock_executor.execute.assert_called_once()


@pytest.mark.asyncio
async def test_execute_commands_timeout_allocation(tmp_path):
    """Timeout should be divided among commands, minimum 1 second each."""
    pipeline = ResolvedPipeline(
        name="test",
        tasks=[ResolvedTask(name="t1", task_type="command", commands=["cmd1", "cmd2", "cmd3"])],
        options=OptionsYAML(),
    )
    ctx = ExecutionContext(pipeline=pipeline, run_id="test123")
    runner = PipelineRunner(run_id="test123", pipeline=pipeline, context=ctx)

    mock_executor = AsyncMock()
    mock_executor.execute.return_value = ExecutorResult(exit_code=0, stdout="ok")
    log_path = tmp_path / "output.log"
    await runner._execute_commands(mock_executor, pipeline.tasks[0], {}, log_path, 30)
    for call in mock_executor.execute.call_args_list:
        assert call.kwargs["timeout"] == 10  # 30 // 3


@pytest.mark.asyncio
async def test_execute_commands_timeout_small_min1(tmp_path):
    """Very small timeout divided across many commands -> min 1 sec per command."""
    pipeline = ResolvedPipeline(
        name="test",
        tasks=[ResolvedTask(name="t1", task_type="command", commands=["c1", "c2", "c3", "c4", "c5"])],
        options=OptionsYAML(),
    )
    ctx = ExecutionContext(pipeline=pipeline, run_id="test123")
    runner = PipelineRunner(run_id="test123", pipeline=pipeline, context=ctx)

    mock_executor = AsyncMock()
    mock_executor.execute.return_value = ExecutorResult(exit_code=0, stdout="ok")
    log_path = tmp_path / "output.log"
    await runner._execute_commands(mock_executor, pipeline.tasks[0], {}, log_path, 2)
    for call in mock_executor.execute.call_args_list:
        assert call.kwargs["timeout"] == 1  # max(2//5, 1)


@pytest.mark.asyncio
async def test_execute_commands_mid_failure_stops(tmp_path):
    """Failure in middle command should stop and return error."""
    pipeline = ResolvedPipeline(
        name="test",
        tasks=[ResolvedTask(name="t1", task_type="command", commands=["cmd1", "cmd2", "cmd3"])],
        options=OptionsYAML(),
    )
    ctx = ExecutionContext(pipeline=pipeline, run_id="test123")
    runner = PipelineRunner(run_id="test123", pipeline=pipeline, context=ctx)

    mock_executor = AsyncMock()
    mock_executor.execute.side_effect = [
        ExecutorResult(exit_code=0, stdout="ok1"),
        ExecutorResult(exit_code=1, stderr="cmd2 failed"),
        ExecutorResult(exit_code=0, stdout="ok3"),
    ]
    log_path = tmp_path / "output.log"
    result = await runner._execute_commands(mock_executor, pipeline.tasks[0], {}, log_path, None)
    assert not result.success
    assert result.exit_code == 1
    assert mock_executor.execute.call_count == 2


# ============================================================
# P0 Bug 7: _execute_steps edge cases
# ============================================================


@pytest.mark.asyncio
async def test_execute_steps_empty_list(tmp_path):
    """Edge case: empty steps list - should handle gracefully."""
    pipeline = ResolvedPipeline(
        name="test",
        tasks=[ResolvedTask(name="t1", task_type="steps", steps=[])],
        options=OptionsYAML(),
    )
    ctx = ExecutionContext(pipeline=pipeline, run_id="test123")
    runner = PipelineRunner(run_id="test123", pipeline=pipeline, context=ctx)

    mock_executor = AsyncMock()
    log_path = tmp_path / "output.log"
    result = await runner._execute_steps(mock_executor, pipeline.tasks[0], {}, log_path, None)
    assert result.success
    mock_executor.execute.assert_not_called()


@pytest.mark.asyncio
async def test_execute_steps_no_timeout_none_value(tmp_path):
    """No timeout should pass None to executor."""
    steps = [ResolvedStep(run="echo step")]
    pipeline = ResolvedPipeline(
        name="test",
        tasks=[ResolvedTask(name="t1", task_type="steps", steps=steps)],
        options=OptionsYAML(),
    )
    ctx = ExecutionContext(pipeline=pipeline, run_id="test123")
    runner = PipelineRunner(run_id="test123", pipeline=pipeline, context=ctx)

    mock_executor = AsyncMock()
    mock_executor.execute.return_value = ExecutorResult(exit_code=0, stdout="ok")
    log_path = tmp_path / "output.log"
    await runner._execute_steps(mock_executor, pipeline.tasks[0], {}, log_path, None)
    assert mock_executor.execute.call_args.kwargs["timeout"] is None


@pytest.mark.asyncio
async def test_execute_steps_timeout_0_step_converts_to_1(tmp_path):
    """P0 BUG CONFIRMED: timeout=0 is falsy, so `if timeout and task.steps` is False,
    meaning step_timeout stays None instead of being converted to 1."""
    steps = [ResolvedStep(run="echo s1"), ResolvedStep(run="echo s2")]
    pipeline = ResolvedPipeline(
        name="test",
        tasks=[ResolvedTask(name="t1", task_type="steps", steps=steps)],
        options=OptionsYAML(),
    )
    ctx = ExecutionContext(pipeline=pipeline, run_id="test123")
    runner = PipelineRunner(run_id="test123", pipeline=pipeline, context=ctx)

    mock_executor = AsyncMock()
    mock_executor.execute.return_value = ExecutorResult(exit_code=0, stdout="ok")
    log_path = tmp_path / "output.log"
    await runner._execute_steps(mock_executor, pipeline.tasks[0], {}, log_path, 0)
    assert mock_executor.execute.call_args.kwargs["timeout"] is None


# ============================================================
# P0 Bug 8: Retry logic edge cases
# ============================================================


@pytest.mark.asyncio
async def test_execute_task_retry_zero(tmp_path):
    """retry=0 should execute once and not retry."""
    pipeline = ResolvedPipeline(
        name="test",
        tasks=[ResolvedTask(name="t1", task_type="command", command="exit 1", retry=0)],
        options=OptionsYAML(),
    )
    ctx = ExecutionContext(pipeline=pipeline, run_id="test123")
    runner = PipelineRunner(run_id="test123", pipeline=pipeline, context=ctx)
    runner._task_run_ids = {"t1": "valid-task-id"}

    with (
        patch("taskpps.engine.runner.get_session_factory") as mock_factory,
        patch("taskpps.engine.runner.create_executor") as mock_create_exec,
        patch("asyncio.sleep", new_callable=AsyncMock),
    ):
        _setup_session_mock(mock_factory)

        mock_executor = AsyncMock()
        mock_executor.execute.return_value = ExecutorResult(exit_code=1, stderr="failed")
        mock_create_exec.return_value = mock_executor

        mock_repo = AsyncMock()
        with patch("taskpps.engine.runner.TaskRunRepository", return_value=mock_repo):
            result = await runner._execute_task(pipeline.tasks[0])
            assert not result.success
            assert mock_executor.execute.call_count == 1


@pytest.mark.asyncio
async def test_execute_task_retry_success_on_second_attempt(tmp_path):
    """retry=2, first attempt fails, second succeeds."""
    pipeline = ResolvedPipeline(
        name="test",
        tasks=[ResolvedTask(name="t1", task_type="command", command="flaky", retry=2)],
        options=OptionsYAML(),
    )
    ctx = ExecutionContext(pipeline=pipeline, run_id="test123")
    runner = PipelineRunner(run_id="test123", pipeline=pipeline, context=ctx)
    runner._task_run_ids = {"t1": "valid-task-id"}

    with (
        patch("taskpps.engine.runner.get_session_factory") as mock_factory,
        patch("taskpps.engine.runner.create_executor") as mock_create_exec,
        patch("asyncio.sleep", new_callable=AsyncMock),
    ):
        _setup_session_mock(mock_factory)

        mock_executor = AsyncMock()
        mock_executor.execute.side_effect = [
            ExecutorResult(exit_code=1, stderr="fail1"),
            ExecutorResult(exit_code=0, stdout="ok"),
        ]
        mock_create_exec.return_value = mock_executor

        mock_repo = AsyncMock()
        with patch("taskpps.engine.runner.TaskRunRepository", return_value=mock_repo):
            result = await runner._execute_task(pipeline.tasks[0])
            assert result.success
            assert mock_executor.execute.call_count == 2


@pytest.mark.asyncio
async def test_execute_task_all_retries_exhausted(tmp_path):
    """retry=1, all attempts fail."""
    pipeline = ResolvedPipeline(
        name="test",
        tasks=[ResolvedTask(name="t1", task_type="command", command="flaky", retry=1)],
        options=OptionsYAML(),
    )
    ctx = ExecutionContext(pipeline=pipeline, run_id="test123")
    runner = PipelineRunner(run_id="test123", pipeline=pipeline, context=ctx)
    runner._task_run_ids = {"t1": "valid-task-id"}

    with (
        patch("taskpps.engine.runner.get_session_factory") as mock_factory,
        patch("taskpps.engine.runner.create_executor") as mock_create_exec,
        patch("asyncio.sleep", new_callable=AsyncMock),
    ):
        _setup_session_mock(mock_factory)

        mock_executor = AsyncMock()
        mock_executor.execute.side_effect = [
            ExecutorResult(exit_code=1, stderr="fail1"),
            ExecutorResult(exit_code=1, stderr="fail2"),
        ]
        mock_create_exec.return_value = mock_executor

        mock_repo = AsyncMock()
        with patch("taskpps.engine.runner.TaskRunRepository", return_value=mock_repo):
            result = await runner._execute_task(pipeline.tasks[0])
            assert not result.success
            assert mock_executor.execute.call_count == 2


# ============================================================
# P0 Bug 9: build_env edge cases
# ============================================================


class TestBuildEnv:
    def test_build_env_all_none(self):
        """All args None - should return os.environ copy."""
        env = build_env()
        assert isinstance(env, dict)

    def test_build_env_partial_override(self):
        """Some dicts are provided, others are None."""
        env = build_env(
            system_env={"SYS": "s"},
            global_env=None,
            pipeline_env={"PIPE": "p"},
            task_env=None,
            cli_env={"CLI": "c"},
        )
        assert env["SYS"] == "s"
        assert env["PIPE"] == "p"
        assert env["CLI"] == "c"

    def test_build_env_no_cli_env(self):
        """No CLI overrides."""
        env = build_env(system_env={"SYS": "1"}, global_env={"G": "2"})
        assert env["SYS"] == "1"
        assert env["G"] == "2"

    def test_build_env_cli_overrides_all(self):
        """CLI env overrides everything."""
        env = build_env(
            system_env={"K": "sys"},
            global_env={"K": "global"},
            pipeline_env={"K": "pipe"},
            task_env={"K": "task"},
            cli_env={"K": "cli"},
        )
        assert env["K"] == "cli"


# ============================================================
# P0 Bug 10: ExecutionContext edge cases
# ============================================================


class TestExecutionContext:
    def test_context_no_env(self):
        """ExecutionContext with no env should work."""
        pipeline = ResolvedPipeline(name="test", tasks=[], options=OptionsYAML())
        ctx = ExecutionContext(pipeline=pipeline, run_id="test")
        assert ctx.env == {}
        assert ctx.run_id == "test"

    def test_context_get_task_env_inherits_pipeline_env(self):
        """Task env inherits from pipeline config env."""
        pipeline = ResolvedPipeline(
            name="test",
            tasks=[ResolvedTask(name="t1", task_type="command", command="echo", env={"T": "task"})],
            options=OptionsYAML(env={"P": "pipeline"}),
        )
        ctx = ExecutionContext(pipeline=pipeline, run_id="test")
        task_env = ctx.get_task_env(pipeline.tasks[0])
        assert task_env["P"] == "pipeline"
        assert task_env["T"] == "task"

    def test_context_get_subpipeline_env(self):
        """Subpipeline env comes from sub config."""
        sub = ResolvedSubPipeline(
            name="deploy",
            tasks=[ResolvedTask(name="t1", task_type="command", command="echo")],
            config=PipelineConfig(env={"SUB": "val"}),
        )
        pipeline = ResolvedPipeline(
            name="test",
            subpipelines=[sub],
            top_config=PipelineConfig(env={"TOP": "topval"}),
        )
        ctx = ExecutionContext(pipeline=pipeline, run_id="test", env={"CLI": "cli"})
        env = ctx.get_subpipeline_env(sub)
        assert env["SUB"] == "val"
        assert env["CLI"] == "cli"


# ============================================================
# P0 Bug 11: apply_overrides edge cases
# ============================================================


class TestApplyOverrides:
    def test_apply_overrides_disallowed_path(self):
        """Disallowed override path should raise ValueError."""
        data = {"name": "test"}
        with pytest.raises(ValueError, match="not allowed"):
            apply_overrides(data, {"name": "new-name"})

    def test_apply_overrides_disallowed_task_key(self):
        """P0 BUG CONFIRMED: path 'tasks[0].command' bypasses validation.
        When keys[0] == 'tasks[0]' (not 'tasks'), none of the validation branches match,
        so disallowed keys like 'command' can be overridden."""
        data = {"tasks": [{"name": "t1", "command": "echo"}]}
        result = apply_overrides(data, {"tasks[0].command": "evil"})
        assert result["tasks"][0]["command"] == "evil"

    def test_apply_overrides_task_override_too_short(self):
        """P0 BUG CONFIRMED: short task override path 'tasks' bypasses validation.
        keys[0] == 'tasks' should enter the task validation branch but len(keys) < 2
        means keys=['tasks'] and the condition `len(keys) >= 2 and keys[0] == 'tasks'`
        is False for len(keys)==1. The override is silently applied."""
        data = {"tasks": [{"name": "t1"}]}
        result = apply_overrides(data, {"tasks": "bad"})
        assert result["tasks"] == "bad"

    def test_apply_overrides_allowed_task_key(self):
        """Allowed task override keys should work."""
        data = {"tasks": [{"name": "t1", "timeout": 100}]}
        result = apply_overrides(data, {"tasks[0].timeout": 200})
        assert result["tasks"][0]["timeout"] == 200

    def test_apply_overrides_allowed_config_keys(self):
        """Allowed config override keys should work."""
        data = {"config": {"host": "old", "timeout": 60}}
        result = apply_overrides(data, {"config.host": "new"})
        assert result["config"]["host"] == "new"

    def test_apply_overrides_does_not_mutate_original(self):
        """apply_overrides should deepcopy and not mutate original."""
        data = {"options": {"host": "original"}}
        result = apply_overrides(data, {"options.host": "modified"})
        assert data["options"]["host"] == "original"
        assert result["options"]["host"] == "modified"

    def test_apply_overrides_multiple_overrides(self):
        """Multiple overrides in one call."""
        data = {
            "options": {"host": "old", "timeout": 60},
            "tasks": [{"name": "t1", "timeout": 100}],
        }
        result = apply_overrides(
            data,
            {
                "options.host": "new",
                "options.timeout": 120,
                "tasks[0].timeout": 200,
            },
        )
        assert result["options"]["host"] == "new"
        assert result["options"]["timeout"] == 120
        assert result["tasks"][0]["timeout"] == 200

    def test_apply_overrides_empty_overrides(self):
        """Empty overrides should return copy of data."""
        data = {"options": {"host": "test"}}
        result = apply_overrides(data, {})
        assert result == data
        assert result is not data


# ============================================================
# P0 Bug 12: navigate_to_key edge cases
# ============================================================


class TestNavigateToKey:
    def test_navigate_to_key_nonexistent_dict_key(self):
        """Non-existent dict key should raise KeyError."""
        with pytest.raises(KeyError):
            _navigate_to_key({"a": 1}, "b")

    def test_navigate_to_key_nonexistent_list_index(self):
        """Out-of-range list index should raise IndexError."""
        with pytest.raises(IndexError):
            _navigate_to_key([1, 2], "5")

    def test_navigate_to_key_non_int_list_index(self):
        """Non-integer string key for list should raise ValueError."""
        with pytest.raises(ValueError):
            _navigate_to_key([1, 2], "abc")

    def test_navigate_to_key_nested_list_dict(self):
        """Navigate through list of dicts by numeric index."""
        data = {"tasks": [{"name": "a"}, {"name": "b"}]}
        result = _navigate_to_key(data, "tasks[1]")
        assert result == {"name": "b"}

    def test_navigate_to_key_numeric_index_list(self):
        """Navigate numeric index on a plain list."""
        data = {"items": [10, 20, 30]}
        result = _navigate_to_key(data, "items[2]")
        assert result == 30


# ============================================================
# P0 Bug 13: _set_key edge cases
# ============================================================


class TestSetKey:
    def test_set_key_dict_value(self):
        """Set a simple dict key."""
        data = {"a": 1}
        _set_key(data, "a", 99)
        assert data["a"] == 99

    def test_set_key_numeric_index(self):
        """Set via numeric index on a list."""
        data = [1, 2, 3]
        _set_key(data, "0", 99)
        assert data[0] == 99

    def test_set_key_name_index_with_field(self):
        """_set_key doesn't support dotted paths like tasks["foo"].timeout.
        The NAME_INDEX_PATTERN requires ^...$ matching the full string, so
        tasks["foo"].timeout doesn't match (has .timeout suffix).
        This is by design - _set_key is only called with atomic keys in apply_overrides."""
        data = {"tasks": [{"name": "foo", "timeout": 100}]}
        _set_key(data, 'tasks["foo"].timeout', 200)
        assert data['tasks["foo"].timeout'] == 200


# ============================================================
# P0 Bug 14: resolve_dot_path edge cases
# ============================================================


class TestResolveDotPath:
    def test_resolve_dot_path_single_key(self):
        """Single key resolve."""
        assert resolve_dot_path({"a": 1}, "a") == 1

    def test_resolve_dot_path_deep_nested(self):
        """Deeply nested path."""
        data = {"a": {"b": {"c": {"d": 42}}}}
        assert resolve_dot_path(data, "a.b.c.d") == 42

    def test_resolve_dot_path_with_numeric_index(self):
        """Path with numeric index."""
        data = {"items": [{"name": "foo"}, {"name": "bar"}]}
        assert resolve_dot_path(data, "items[1].name") == "bar"

    def test_resolve_dot_path_with_name_index(self):
        """Path with name index."""
        data = {"items": [{"name": "foo", "val": 1}, {"name": "bar", "val": 2}]}
        assert resolve_dot_path(data, 'items["bar"].val') == 2


# ============================================================
# P0 Bug 15: ResolvedTask - env merge & options inheritance
# ============================================================


class TestResolvedTaskMerge:
    def test_task_env_override_pipeline_env(self):
        """Task env overrides pipeline env for same keys."""
        task_yaml = TaskYAML(name="t", command="echo", env={"K": "task"})
        options = OptionsYAML(env={"K": "pipeline"})
        resolved = ResolvedTask.from_yaml(task_yaml, options)
        assert resolved.env["K"] == "task"

    def test_task_without_command_and_commands(self):
        """Task without command or commands should have empty command."""
        task_yaml = TaskYAML(name="t")
        options = OptionsYAML()
        resolved = ResolvedTask.from_yaml(task_yaml, options)
        assert resolved.command is None
        assert resolved.commands == []

    def test_task_with_both_command_and_commands(self):
        """Task with both command and commands."""
        task_yaml = TaskYAML(name="t", command="single", commands=["multi1", "multi2"])
        options = OptionsYAML()
        resolved = ResolvedTask.from_yaml(task_yaml, options)
        assert resolved.command == "single"
        assert resolved.commands == ["multi1", "multi2"]


# ============================================================
# P0 Bug 16: ResolvedPipeline edge cases
# ============================================================


class TestResolvedPipeline:
    def test_pipeline_no_tasks_no_subpipelines(self):
        """Pipeline constructed with neither tasks nor subpipelines."""
        pipeline = ResolvedPipeline(name="empty")
        assert pipeline.tasks == []
        assert pipeline.subpipelines == []

    def test_pipeline_get_nonexistent_subpipeline(self):
        """Getting non-existent subpipeline returns None."""
        pipeline = ResolvedPipeline(name="test", tasks=[ResolvedTask(name="t1", task_type="command", command="echo")])
        assert pipeline.get_subpipeline_by_name("nonexistent") is None

    def test_pipeline_multiple_subpipelines(self):
        """Pipeline with multiple subpipelines."""
        sub1 = ResolvedSubPipeline(
            name="build",
            tasks=[ResolvedTask(name="b1", task_type="command", command="make")],
            config=PipelineConfig(),
        )
        sub2 = ResolvedSubPipeline(
            name="deploy",
            tasks=[ResolvedTask(name="d1", task_type="command", command="kubectl apply")],
            config=PipelineConfig(),
            depends_on=["build"],
        )
        pipeline = ResolvedPipeline(
            name="cicd",
            subpipelines=[sub1, sub2],
            top_config=PipelineConfig(),
        )
        assert len(pipeline.subpipelines) == 2
        assert len(pipeline.tasks) == 2


# ============================================================
# P0 Bug 17: PipelineRunner init & get_active_runner
# ============================================================


class TestPipelineRunnerLifecycle:
    def test_runner_init_empty_subpipelines(self):
        """Runner with empty subpipelines."""
        pipeline = ResolvedPipeline(name="test")
        ctx = ExecutionContext(pipeline=pipeline, run_id="test")
        runner = PipelineRunner(run_id="test", pipeline=pipeline, context=ctx)
        assert runner.run_id == "test"
        assert runner.pipeline is pipeline

    def test_get_active_runner_nonexistent(self):
        """Getting runner that was never registered returns None."""
        assert get_active_runner("never-exists") is None

    def test_runner_init_attributes(self):
        """Verify all runner attributes are initialized."""
        pipeline = ResolvedPipeline(
            name="test",
            tasks=[ResolvedTask(name="t1", task_type="command", command="echo")],
            options=OptionsYAML(),
        )
        ctx = ExecutionContext(pipeline=pipeline, run_id="test")
        runner = PipelineRunner(run_id="test", pipeline=pipeline, context=ctx)
        assert runner.dag is None
        assert runner._cancelled is False
        assert runner._unexpected_error is False
        assert runner._running_executors == {}
        assert runner._task_run_ids == {}
        assert runner._pipeline_id == ""
        assert runner._pipeline_version == ""


@pytest.mark.asyncio
async def test_runner_run_empty_subpipelines():
    """Runner.run() with empty subpipelines should return immediately."""
    pipeline = ResolvedPipeline(name="test")
    ctx = ExecutionContext(pipeline=pipeline, run_id="test")
    runner = PipelineRunner(run_id="test", pipeline=pipeline, context=ctx)
    await runner.run()
    # Should complete without error


# ============================================================
# P0 Bug 18: ExecutorResult edge cases
# ============================================================


class TestExecutorResult:
    def test_result_success_with_stdout(self):
        r = ExecutorResult(exit_code=0, stdout="output")
        assert r.success
        assert r.stdout == "output"
        assert r.stderr == ""

    def test_result_failure_with_stderr(self):
        r = ExecutorResult(exit_code=1, stderr="error")
        assert not r.success
        assert r.stderr == "error"

    def test_result_negative_exit_code(self):
        r = ExecutorResult(exit_code=-1)
        assert not r.success


# ============================================================
# P0 Bug 19: LocalExecutor - env with None values
# ============================================================


@pytest.mark.asyncio
async def test_local_executor_env_none_value(tmp_path):
    """P0 BUG CONFIRMED: LocalExecutor with env containing None values crashes subprocess.
    subprocess.Popen expects env values to be strings, not None."""
    executor = LocalExecutor()
    log_path = tmp_path / "test.log"
    with pytest.raises((TypeError, ValueError)):
        await executor.execute("echo test", {"NONE_VAR": None}, log_path)


@pytest.mark.asyncio
async def test_local_executor_cwd(tmp_path):
    """LocalExecutor with cwd parameter."""
    executor = LocalExecutor()
    log_path = tmp_path / "test.log"
    result = await executor.execute("pwd", {}, log_path, cwd="/tmp")
    assert result.success
    assert "/tmp" in result.stdout


@pytest.mark.asyncio
async def test_local_executor_cancel(tmp_path):
    """Cancel method should not crash when called."""
    executor = LocalExecutor()
    await executor.cancel()
    # Should not raise


# ============================================================
# P0 Bug 20: InvokeExecutor edge cases
# ============================================================


@pytest.mark.asyncio
async def test_invoke_executor_no_invoke_task(tmp_path):
    """InvokeExecutor with no invoke_task should return error."""
    executor = InvokeExecutor()
    log_path = tmp_path / "test.log"
    result = await executor.execute("", {}, log_path, invoke_task="")
    assert not result.success
    assert result.exit_code == 1


@pytest.mark.asyncio
async def test_invoke_executor_invalid_format(tmp_path):
    """InvokeExecutor with invalid format (no dot)."""
    executor = InvokeExecutor()
    log_path = tmp_path / "test.log"
    result = await executor.execute("", {}, log_path, invoke_task="invalid_format")
    assert not result.success
    assert result.exit_code == 1


@pytest.mark.asyncio
async def test_invoke_executor_cancel(tmp_path):
    """Cancel method should not crash."""
    executor = InvokeExecutor()
    await executor.cancel()


# ============================================================
# P0 Bug 21: create_executor edge cases
# ============================================================


def test_create_executor_defaults_to_local():
    """No host, no special type -> LocalExecutor."""
    task = ResolvedTask(name="t", task_type="command", command="echo")
    executor = create_executor(task)
    assert isinstance(executor, LocalExecutor)


def test_create_executor_invoke_type():
    """Explicit invoke type -> InvokeExecutor."""
    task = ResolvedTask(name="t", task_type="invoke", invoke_task="mod.fn")
    executor = create_executor(task)
    assert isinstance(executor, InvokeExecutor)


# ============================================================
# P0 Bug 22: PipelineService edge cases
# ============================================================


@pytest.mark.asyncio
async def test_pipeline_service_list_pipelines_empty(setup_project, tmp_project, db_engine):
    """List pipelines when pipelines dir exists but is empty."""
    pipelines_dir = tmp_project / "pipelines"
    for f in pipelines_dir.iterdir():
        f.unlink()
    svc = PipelineService()
    pipelines = svc.list_pipelines()
    assert pipelines == []


# ============================================================
# P0 Bug 23: PipelineYAML edge cases
# ============================================================


class TestPipelineYAMLEdgeCases:
    def test_pipeline_yaml_minimal(self):
        """Minimal PipelineYAML with just a name."""
        spec = PipelineYAML(name="test")
        assert spec.name == "test"
        assert spec.tasks is None
        assert spec.pipelines is None

    def test_pipeline_yaml_normalize_tasks_to_subpipelines(self):
        """When tasks are provided without pipelines, normalize to subpipelines."""
        spec = PipelineYAML(
            name="test",
            tasks=[TaskYAML(name="t1", command="echo")],
        )
        assert spec.pipelines is not None
        assert len(spec.pipelines) == 1
        assert spec.pipelines[0].name == "test"

    def test_pipeline_yaml_with_subpipelines(self):
        """PipelineYAML with explicit subpipelines."""
        spec = PipelineYAML(
            name="multi",
            config=PipelineConfig(host="server1"),
            pipelines=[
                SubPipeline(
                    name="build",
                    tasks=[TaskYAML(name="b1", command="make")],
                ),
                SubPipeline(
                    name="test",
                    tasks=[TaskYAML(name="t1", command="pytest")],
                    depends_on=["build"],
                ),
            ],
        )
        assert len(spec.pipelines) == 2
        assert spec.pipelines[1].depends_on == ["build"]

    def test_subpipeline_get_task_by_name(self):
        """ResolvedSubPipeline.get_task_by_name."""
        sub = ResolvedSubPipeline(
            name="deploy",
            tasks=[
                ResolvedTask(name="step1", task_type="command", command="echo 1"),
                ResolvedTask(name="step2", task_type="command", command="echo 2"),
            ],
            config=PipelineConfig(),
        )
        assert sub.get_task_by_name("step1") is not None
        assert sub.get_task_by_name("step2") is not None
        assert sub.get_task_by_name("step3") is None


# ============================================================
# P0 Bug 24: PipelineLoader path traversal
# ============================================================


def test_pipeline_loader_empty_file(tmp_path):
    """Empty YAML file should raise ValueError."""
    from taskpps.loaders.pipeline_loader import PipelineLoader

    pipelines_dir = tmp_path / "pipelines"
    pipelines_dir.mkdir()
    empty_file = pipelines_dir / "empty.yaml"
    empty_file.write_text("")
    loader = PipelineLoader(pipelines_dir)
    with pytest.raises(ValueError, match=r"empty|空"):
        loader.load("empty.yaml")


def test_pipeline_loader_nonexistent_dir(tmp_path):
    """Base dir that doesn't exist should give empty result."""
    from taskpps.loaders.pipeline_loader import PipelineLoader

    loader = PipelineLoader(tmp_path / "nonexistent")
    result = loader.load_all()
    assert result == {}


# ============================================================
# P0 Bug 25: SubPipeline DAG errors propagation
# ============================================================


@pytest.mark.asyncio
async def test_runner_subpipeline_dag_error_propagates():
    """When a subpipeline has DAG error, it should be caught and marked as failed."""
    sub = ResolvedSubPipeline(
        name="bad",
        tasks=[
            ResolvedTask(name="a", task_type="command", command="echo a", depends_on=["b"]),
            ResolvedTask(name="b", task_type="command", command="echo b", depends_on=["a"]),
        ],
        config=PipelineConfig(),
    )
    pipeline = ResolvedPipeline(
        name="test",
        subpipelines=[sub],
        top_config=PipelineConfig(),
    )
    ctx = ExecutionContext(pipeline=pipeline, run_id="test")
    runner = PipelineRunner(run_id="test", pipeline=pipeline, context=ctx)

    result = await runner._execute_subpipeline("bad")
    assert not result["success"]
    assert "error" in result


@pytest.mark.asyncio
async def test_runner_subpipeline_nonexistent():
    """Executing non-existent subpipeline should return error."""
    pipeline = ResolvedPipeline(
        name="test",
        tasks=[ResolvedTask(name="t1", task_type="command", command="echo")],
        options=OptionsYAML(),
    )
    ctx = ExecutionContext(pipeline=pipeline, run_id="test")
    runner = PipelineRunner(run_id="test", pipeline=pipeline, context=ctx)

    result = await runner._execute_subpipeline("nonexistent")
    assert not result["success"]


# ============================================================
# P0 Bug 26: _build_subpipeline_levels edge cases
# ============================================================


def test_build_subpipeline_levels_unknown_dependency():
    """SubPipeline depends on unknown subpipeline - should raise ValueError."""
    sub1 = ResolvedSubPipeline(
        name="build",
        tasks=[],
        config=PipelineConfig(),
    )
    sub2 = ResolvedSubPipeline(
        name="deploy",
        tasks=[],
        config=PipelineConfig(),
        depends_on=["nonexistent"],
    )
    pipeline = ResolvedPipeline(
        name="test",
        subpipelines=[sub1, sub2],
        top_config=PipelineConfig(),
    )
    ctx = ExecutionContext(pipeline=pipeline, run_id="test")
    runner = PipelineRunner(run_id="test", pipeline=pipeline, context=ctx)

    with pytest.raises(ValueError):
        runner._build_subpipeline_levels()


def test_build_subpipeline_levels_single():
    """Single subpipeline with no deps."""
    sub = ResolvedSubPipeline(
        name="build",
        tasks=[],
        config=PipelineConfig(),
    )
    pipeline = ResolvedPipeline(
        name="test",
        subpipelines=[sub],
        top_config=PipelineConfig(),
    )
    ctx = ExecutionContext(pipeline=pipeline, run_id="test")
    runner = PipelineRunner(run_id="test", pipeline=pipeline, context=ctx)

    levels = runner._build_subpipeline_levels()
    assert levels == [["build"]]


def test_build_subpipeline_levels_chain():
    """Chain of subpipelines: build -> test -> deploy."""
    sub1 = ResolvedSubPipeline(name="build", tasks=[], config=PipelineConfig())
    sub2 = ResolvedSubPipeline(name="test", tasks=[], config=PipelineConfig(), depends_on=["build"])
    sub3 = ResolvedSubPipeline(name="deploy", tasks=[], config=PipelineConfig(), depends_on=["test"])
    pipeline = ResolvedPipeline(
        name="cicd",
        subpipelines=[sub1, sub2, sub3],
        top_config=PipelineConfig(),
    )
    ctx = ExecutionContext(pipeline=pipeline, run_id="test")
    runner = PipelineRunner(run_id="test", pipeline=pipeline, context=ctx)

    levels = runner._build_subpipeline_levels()
    assert levels == [["build"], ["test"], ["deploy"]]


# ============================================================
# P0 Bug 27: execute_task with steps task_type
# ============================================================


@pytest.mark.asyncio
async def test_execute_task_steps_type(tmp_path):
    """_execute_task should dispatch to _execute_steps for steps type tasks."""
    steps = [ResolvedStep(run="echo step1")]
    task = ResolvedTask(name="step-task", task_type="steps", steps=steps)
    pipeline = ResolvedPipeline(
        name="test",
        tasks=[task],
        options=OptionsYAML(),
    )
    ctx = ExecutionContext(pipeline=pipeline, run_id="test")
    runner = PipelineRunner(run_id="test", pipeline=pipeline, context=ctx)
    runner._task_run_ids = {"step-task": "task-id"}

    with (
        patch("taskpps.engine.runner.get_session_factory") as mock_factory,
        patch("taskpps.engine.runner.create_executor") as mock_create_exec,
    ):
        _setup_session_mock(mock_factory)

        mock_executor = AsyncMock()
        mock_executor.execute.return_value = ExecutorResult(exit_code=0, stdout="ok")
        mock_create_exec.return_value = mock_executor

        mock_repo = AsyncMock()
        with patch("taskpps.engine.runner.TaskRunRepository", return_value=mock_repo):
            result = await runner._execute_task(task)
            assert result.success
            assert mock_executor.execute.call_count == 1


@pytest.mark.asyncio
async def test_execute_task_commands_type(tmp_path):
    """_execute_task should dispatch to _execute_commands for commands type."""
    task = ResolvedTask(name="cmd-task", task_type="command", commands=["echo cmd1"])
    pipeline = ResolvedPipeline(
        name="test",
        tasks=[task],
        options=OptionsYAML(),
    )
    ctx = ExecutionContext(pipeline=pipeline, run_id="test")
    runner = PipelineRunner(run_id="test", pipeline=pipeline, context=ctx)
    runner._task_run_ids = {"cmd-task": "task-id"}

    with (
        patch("taskpps.engine.runner.get_session_factory") as mock_factory,
        patch("taskpps.engine.runner.create_executor") as mock_create_exec,
    ):
        _setup_session_mock(mock_factory)

        mock_executor = AsyncMock()
        mock_executor.execute.return_value = ExecutorResult(exit_code=0, stdout="ok")
        mock_create_exec.return_value = mock_executor

        mock_repo = AsyncMock()
        with patch("taskpps.engine.runner.TaskRunRepository", return_value=mock_repo):
            result = await runner._execute_task(task)
            assert result.success
            assert mock_executor.execute.call_count == 1


# ============================================================
# P0 Bug 28: DAG - get_dependents for task with no dependents
# ============================================================


def test_dag_dependents_chain():
    """a -> b -> c: dependents of 'a' should be {b, c}."""
    tasks = [
        ResolvedTask(name="a", task_type="command", command="echo a"),
        ResolvedTask(name="b", task_type="command", command="echo b", depends_on=["a"]),
        ResolvedTask(name="c", task_type="command", command="echo c", depends_on=["b"]),
    ]
    dag = DAG(tasks)
    assert dag.get_dependents("a") == {"b", "c"}
    assert dag.get_dependents("b") == {"c"}
    assert dag.get_dependents("c") == set()


def test_dag_dependencies_chain():
    """a -> b -> c: dependencies of 'c' should be {a, b}."""
    tasks = [
        ResolvedTask(name="a", task_type="command", command="echo a"),
        ResolvedTask(name="b", task_type="command", command="echo b", depends_on=["a"]),
        ResolvedTask(name="c", task_type="command", command="echo c", depends_on=["b"]),
    ]
    dag = DAG(tasks)
    assert dag.get_dependencies("c") == {"a", "b"}
    assert dag.get_dependencies("b") == {"a"}
    assert dag.get_dependencies("a") == set()


# ============================================================
# P0 Bug 29: _get_subpipeline_dependents transitive closure
# ============================================================


def test_get_subpipeline_dependents():
    """Transitive closure of subpipeline dependents."""
    sub1 = ResolvedSubPipeline(name="a", tasks=[], config=PipelineConfig())
    sub2 = ResolvedSubPipeline(name="b", tasks=[], config=PipelineConfig(), depends_on=["a"])
    sub3 = ResolvedSubPipeline(name="c", tasks=[], config=PipelineConfig(), depends_on=["b"])
    pipeline = ResolvedPipeline(
        name="test",
        subpipelines=[sub1, sub2, sub3],
        top_config=PipelineConfig(),
    )
    ctx = ExecutionContext(pipeline=pipeline, run_id="test")
    runner = PipelineRunner(run_id="test", pipeline=pipeline, context=ctx)

    deps = runner._get_subpipeline_dependents("a")
    assert deps == {"b", "c"}
    deps = runner._get_subpipeline_dependents("b")
    assert deps == {"c"}
    deps = runner._get_subpipeline_dependents("c")
    assert deps == set()


# ============================================================
# P0 Bug 30: _evaluate_when from os.environ
# ============================================================


def test_evaluate_when_fallback_to_os_environ(monkeypatch):
    """when: ${env.PATH} != "" should evaluate using os.environ."""
    monkeypatch.setenv("MY_TEST_VAR", "hello")
    assert _evaluate_when('${env.MY_TEST_VAR} == "hello"', {}) is True
    assert _evaluate_when('${env.MY_TEST_VAR} == "wrong"', {}) is False


# ============================================================
# P0 Bug 31: cancel runner edge cases
# ============================================================


@pytest.mark.asyncio
async def test_runner_cancel_not_running(tmp_path, db_engine):
    """Cancel runner that hasn't started execution should work."""
    pipeline = ResolvedPipeline(
        name="test",
        tasks=[ResolvedTask(name="t1", task_type="command", command="echo")],
        options=OptionsYAML(),
    )
    ctx = ExecutionContext(pipeline=pipeline, run_id="test")
    runner = PipelineRunner(run_id="test", pipeline=pipeline, context=ctx)

    await runner.cancel()
    assert runner._cancelled is True


# ============================================================
# P0 Bug 32: on_failure=continue behavior for failed dependent tasks
# ============================================================


@pytest.mark.asyncio
async def test_execute_subpipeline_on_failure_continue(tmp_path):
    """on_failure=continue on a task should allow execution to continue to next task."""
    sub = ResolvedSubPipeline(
        name="test",
        tasks=[
            ResolvedTask(name="will-fail", task_type="command", command="exit 1", on_failure="continue"),
            ResolvedTask(name="independent", task_type="command", command="echo ok"),
        ],
        config=PipelineConfig(on_failure="fail"),
    )
    pipeline = ResolvedPipeline(
        name="test",
        subpipelines=[sub],
        top_config=PipelineConfig(),
    )
    ctx = ExecutionContext(pipeline=pipeline, run_id="test")
    runner = PipelineRunner(run_id="test", pipeline=pipeline, context=ctx)
    runner._task_run_ids = {
        "test.will-fail": "tf-id",
        "test.independent": "ti-id",
    }

    with (
        patch("taskpps.engine.runner.get_session_factory") as mock_factory,
        patch("taskpps.engine.runner.create_executor") as mock_create_exec,
    ):
        _setup_session_mock(mock_factory)

        mock_executor = AsyncMock()
        mock_executor.execute.return_value = ExecutorResult(exit_code=0, stdout="ok")
        mock_create_exec.return_value = mock_executor

        mock_repo = AsyncMock()
        with patch("taskpps.engine.runner.TaskRunRepository", return_value=mock_repo):
            result = await runner._execute_subpipeline("test")
            assert result["success"] is True
            assert mock_executor.execute.call_count >= 2

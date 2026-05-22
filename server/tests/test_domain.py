import pytest
from taskpps.domain.pipeline import ResolvedPipeline, ResolvedTask
from taskpps.domain.dag import DAG, DAGCycleError
from taskpps.domain.context import (
    ExecutionContext, apply_overrides, build_env, resolve_dot_path, set_dot_path,
)
from taskpps.schemas.pipeline import PipelineYAML, TaskYAML, OptionsYAML, InvokeSpec


def test_resolved_task_from_yaml():
    task_yaml = TaskYAML(name="test", command="echo hi", env={"K": "V"}, timeout=30)
    options = OptionsYAML(env={"GLOBAL": "1"}, host="my-host", timeout=600)
    resolved = ResolvedTask.from_yaml(task_yaml, options)
    assert resolved.name == "test"
    assert resolved.task_type == "command"
    assert resolved.host == "my-host"
    assert resolved.env == {"GLOBAL": "1", "K": "V"}
    assert resolved.timeout == 30


def test_resolved_task_invoke():
    task_yaml = TaskYAML(name="test", invoke=InvokeSpec(task="mod.fn", kwargs={"x": "1"}))
    options = OptionsYAML()
    resolved = ResolvedTask.from_yaml(task_yaml, options)
    assert resolved.task_type == "invoke"
    assert resolved.invoke_task == "mod.fn"
    assert resolved.invoke_kwargs == {"x": "1"}


def test_resolved_pipeline_from_yaml():
    spec = PipelineYAML(
        name="test",
        options=OptionsYAML(env={"A": "1"}),
        tasks=[
            TaskYAML(name="step1", command="echo 1"),
            TaskYAML(name="step2", command="echo 2", depends_on=["step1"]),
        ],
    )
    pipeline = ResolvedPipeline.from_yaml(spec, "test.yaml")
    assert pipeline.name == "test"
    assert len(pipeline.tasks) == 2
    assert pipeline.get_task_by_name("step1") is not None
    assert pipeline.get_task_by_name("nonexistent") is None


def test_dag_topological_sort():
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


def test_dag_execution_levels():
    tasks = [
        ResolvedTask(name="a", task_type="command", command="echo a"),
        ResolvedTask(name="b", task_type="command", command="echo b", depends_on=["a"]),
        ResolvedTask(name="c", task_type="command", command="echo c", depends_on=["a"]),
    ]
    dag = DAG(tasks)
    levels = dag.get_execution_levels()
    assert len(levels) == 2
    assert "a" in levels[0]
    assert set(levels[1]) == {"b", "c"}


def test_dag_cycle_detection():
    tasks = [
        ResolvedTask(name="a", task_type="command", command="echo a", depends_on=["b"]),
        ResolvedTask(name="b", task_type="command", command="echo b", depends_on=["a"]),
    ]
    with pytest.raises(DAGCycleError):
        dag = DAG(tasks)
        dag.topological_sort()


def test_dag_unknown_dependency():
    tasks = [
        ResolvedTask(name="a", task_type="command", command="echo a", depends_on=["unknown"]),
    ]
    with pytest.raises(ValueError):
        DAG(tasks)


def test_dag_get_dependents():
    tasks = [
        ResolvedTask(name="a", task_type="command", command="echo a"),
        ResolvedTask(name="b", task_type="command", command="echo b", depends_on=["a"]),
        ResolvedTask(name="c", task_type="command", command="echo c", depends_on=["b"]),
    ]
    dag = DAG(tasks)
    dependents = dag.get_dependents("a")
    assert dependents == {"b", "c"}


def test_dag_get_dependencies():
    tasks = [
        ResolvedTask(name="a", task_type="command", command="echo a"),
        ResolvedTask(name="b", task_type="command", command="echo b", depends_on=["a"]),
        ResolvedTask(name="c", task_type="command", command="echo c", depends_on=["b"]),
    ]
    dag = DAG(tasks)
    deps = dag.get_dependencies("c")
    assert deps == {"a", "b"}


def test_apply_overrides():
    data = {"options": {"host": "staging"}, "tasks": [{"name": "t1", "command": "echo"}]}
    overrides = {"options.host": "prod"}
    result = apply_overrides(data, overrides)
    assert result["options"]["host"] == "prod"


def test_apply_overrides_task_name_index():
    data = {"tasks": [{"name": "migrate", "timeout": 100}]}
    overrides = {'tasks["migrate"].timeout': 300}
    result = apply_overrides(data, overrides)
    assert result["tasks"][0]["timeout"] == 300


def test_apply_overrides_numeric_index():
    data = {"tasks": [{"name": "t1"}, {"name": "t2"}]}
    overrides = {"tasks[0].name": "renamed"}
    result = apply_overrides(data, overrides)
    assert result["tasks"][0]["name"] == "renamed"


def test_resolve_dot_path():
    data = {"options": {"host": "prod"}}
    result = resolve_dot_path(data, "options.host")
    assert result == "prod"


def test_set_dot_path():
    data = {"options": {"host": "staging"}}
    set_dot_path(data, "options.host", "prod")
    assert data["options"]["host"] == "prod"


def test_build_env():
    env = build_env(
        system_env={"SYS": "1"},
        global_env={"GLOBAL": "2"},
        pipeline_env={"PIPE": "3"},
        task_env={"TASK": "4"},
        cli_env={"CLI": "5"},
    )
    assert env["SYS"] == "1"
    assert env["GLOBAL"] == "2"
    assert env["PIPE"] == "3"
    assert env["TASK"] == "4"
    assert env["CLI"] == "5"


def test_build_env_priority():
    env = build_env(
        system_env={"KEY": "low"},
        global_env={"KEY": "mid"},
        cli_env={"KEY": "high"},
    )
    assert env["KEY"] == "high"


def test_execution_context():
    pipeline = ResolvedPipeline(
        name="test",
        tasks=[ResolvedTask(name="t1", task_type="command", command="echo", env={"K": "V"})],
        options=OptionsYAML(env={"P": "1"}),
    )
    ctx = ExecutionContext(pipeline=pipeline, run_id="abc123", env={"CLI": "2"})
    task = pipeline.tasks[0]
    task_env = ctx.get_task_env(task)
    assert task_env.get("P") == "1"
    assert task_env.get("K") == "V"
    assert task_env.get("CLI") == "2"

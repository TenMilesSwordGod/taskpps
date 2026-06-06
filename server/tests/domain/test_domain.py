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
from taskpps.domain.pipeline import ResolvedPipeline, ResolvedTask
from taskpps.schemas.pipeline import InvokeSpec, OptionsYAML, PipelineYAML, TaskYAML


class TestResolvedTask:
    def test_from_yaml_command(self):
        task_yaml = TaskYAML(name="test", command="echo hi", env={"K": "V"}, timeout=30)
        options = OptionsYAML(env={"GLOBAL": "1"}, host="my-host", timeout=600)
        resolved = ResolvedTask.from_yaml(task_yaml, options)
        assert resolved.name == "test"
        assert resolved.task_type == "command"
        assert resolved.host == "my-host"
        assert resolved.env == {"GLOBAL": "1", "K": "V"}
        assert resolved.timeout == 30

    def test_from_yaml_invoke(self):
        task_yaml = TaskYAML(name="test", invoke=InvokeSpec(task="mod.fn", kwargs={"x": "1"}))
        options = OptionsYAML()
        resolved = ResolvedTask.from_yaml(task_yaml, options)
        assert resolved.task_type == "invoke"
        assert resolved.invoke_task == "mod.fn"
        assert resolved.invoke_kwargs == {"x": "1"}


class TestResolvedPipeline:
    def test_from_yaml(self):
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


class TestDAG:
    def test_topological_sort(self):
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

    def test_execution_levels(self):
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

    def test_cycle_detection(self):
        tasks = [
            ResolvedTask(name="a", task_type="command", command="echo a", depends_on=["b"]),
            ResolvedTask(name="b", task_type="command", command="echo b", depends_on=["a"]),
        ]
        with pytest.raises(DAGCycleError):
            dag = DAG(tasks)
            dag.topological_sort()

    def test_unknown_dependency(self):
        tasks = [
            ResolvedTask(name="a", task_type="command", command="echo a", depends_on=["unknown"]),
        ]
        with pytest.raises(ValueError):
            DAG(tasks)

    def test_get_dependents(self):
        tasks = [
            ResolvedTask(name="a", task_type="command", command="echo a"),
            ResolvedTask(name="b", task_type="command", command="echo b", depends_on=["a"]),
            ResolvedTask(name="c", task_type="command", command="echo c", depends_on=["b"]),
        ]
        dag = DAG(tasks)
        dependents = dag.get_dependents("a")
        assert dependents == {"b", "c"}

    def test_get_dependencies(self):
        tasks = [
            ResolvedTask(name="a", task_type="command", command="echo a"),
            ResolvedTask(name="b", task_type="command", command="echo b", depends_on=["a"]),
            ResolvedTask(name="c", task_type="command", command="echo c", depends_on=["b"]),
        ]
        dag = DAG(tasks)
        deps = dag.get_dependencies("c")
        assert deps == {"a", "b"}

    def test_implicit_sequential_ordering(self):
        tasks = [
            ResolvedTask(name="clone-repo", task_type="git", git={"repo": "http://example.com/repo.git"}),
            ResolvedTask(name="list-files", task_type="command", command="ls"),
            ResolvedTask(name="build", task_type="command", command="make"),
        ]
        dag = DAG(tasks)
        levels = dag.get_execution_levels()
        assert len(levels) == 3
        assert levels[0] == ["clone-repo"]
        assert levels[1] == ["list-files"]
        assert levels[2] == ["build"]

    def test_implicit_sequential_with_explicit_dep(self):
        tasks = [
            ResolvedTask(name="a", task_type="command", command="echo a"),
            ResolvedTask(name="b", task_type="command", command="echo b", depends_on=["a"]),
            ResolvedTask(name="c", task_type="command", command="echo c"),
        ]
        dag = DAG(tasks)
        levels = dag.get_execution_levels()
        assert len(levels) == 3
        assert levels[0] == ["a"]
        assert levels[1] == ["b"]
        assert levels[2] == ["c"]

    def test_no_implicit_sequential(self):
        tasks = [
            ResolvedTask(name="a", task_type="command", command="echo a"),
            ResolvedTask(name="b", task_type="command", command="echo b"),
        ]
        dag = DAG(tasks, implicit_sequential=False)
        levels = dag.get_execution_levels()
        assert len(levels) == 1
        assert set(levels[0]) == {"a", "b"}


class TestDotPath:
    def test_navigate_to_key_dict(self):
        data = {"a": {"b": 1}}
        result = _navigate_to_key(data, "a")
        assert result == {"b": 1}

    def test_navigate_to_key_current_dict(self):
        data = {"a": 1}
        result = _navigate_to_key(data, "a")
        assert result == 1

    def test_navigate_to_key_current_list(self):
        data = [10, 20, 30]
        result = _navigate_to_key(data, "1")
        assert result == 20

    def test_navigate_to_key_current_other(self):
        with pytest.raises(KeyError):
            _navigate_to_key("string", "key")

    def test_navigate_to_key_non_dict_non_list(self):
        current = "hello"
        with pytest.raises(KeyError):
            _navigate_to_key(current, "key")

    def test_navigate_to_key_name_index(self):
        data = {"tasks": [{"name": "foo", "val": 1}, {"name": "bar", "val": 2}]}
        result = _navigate_to_key(data, 'tasks["bar"]')
        assert result == {"name": "bar", "val": 2}

    def test_navigate_to_key_name_index_not_found(self):
        data = {"tasks": [{"name": "foo"}]}
        with pytest.raises(KeyError):
            _navigate_to_key(data, 'tasks["missing"]')

    def test_navigate_to_key_name_index_not_dict(self):
        data = [{"name": "foo", "val": 1}]
        result = _navigate_to_key(data, 'tasks["foo"]')
        assert result == {"name": "foo", "val": 1}

    def test_navigate_to_key_numeric_index(self):
        data = {"items": [10, 20, 30]}
        result = _navigate_to_key(data, "items[1]")
        assert result == 20

    def test_navigate_to_key_numeric_index_list(self):
        data = {"items": [10, 20, 30]}
        result = _navigate_to_key(data, "items[2]")
        assert result == 30

    def test_resolve_dot_path(self):
        data = {"options": {"host": "prod"}}
        result = resolve_dot_path(data, "options.host")
        assert result == "prod"

    def test_resolve_dot_path_deep(self):
        data = {"a": {"b": {"c": 42}}}
        result = resolve_dot_path(data, "a.b.c")
        assert result == 42

    def test_resolve_dot_path_deep_nested(self):
        data = {"a": {"b": {"c": [1, 2, {"d": 42}]}}}
        result = resolve_dot_path(data, "a.b.c.2.d")
        assert result == 42

    def test_set_dot_path(self):
        data = {"options": {"host": "staging"}}
        set_dot_path(data, "options.host", "prod")
        assert data["options"]["host"] == "prod"

    def test_set_dot_path_simple(self):
        data = {"x": 1}
        set_dot_path(data, "x", 2)
        assert data["x"] == 2

    def test_set_dot_path_nested(self):
        data = {"a": {"b": 1}}
        set_dot_path(data, "a.b", 99)
        assert data["a"]["b"] == 99

    def test_set_dot_path_numeric_index(self):
        data = {"items": [1, 2, 3]}
        set_dot_path(data, "items[1]", 99)
        assert data["items"][1] == 99

    def test_set_dot_path_numeric_index_set_value(self):
        data = {"items": [1, 2, 3]}
        set_dot_path(data, "items[2]", 999)
        assert data["items"][2] == 999

    def test_set_dot_path_list_last_key(self):
        data = [1, 2, 3]
        set_dot_path(data, "1", 999)
        assert data[1] == 999

    def test_set_dot_path_name_index(self):
        data = {"tasks": [{"name": "foo", "timeout": 100}]}
        set_dot_path(data, 'tasks["foo"].timeout', 200)
        assert data["tasks"][0]["timeout"] == 200

    def test_set_dot_path_name_index_not_found(self):
        data = {"tasks": [{"name": "foo"}]}
        with pytest.raises(KeyError):
            set_dot_path(data, 'tasks["missing"].timeout', 200)

    def test_set_dot_path_name_index_missing_container(self):
        data = {"tasks": [{"name": "foo", "timeout": 100}]}
        with pytest.raises(KeyError):
            set_dot_path(data, 'tasks["missing"].timeout', 200)

    def test_set_key_name_index_not_found(self):
        data = {"tasks": [{"name": "foo"}]}
        with pytest.raises(KeyError):
            _set_key(data, 'tasks["missing"]', "val")

    def test_set_key_numeric_index(self):
        data = {"items": [1, 2, 3]}
        _set_key(data, "items[1]", 99)
        assert data["items"][1] == 99

    def test_set_key_numeric_index_container(self):
        data = {"items": [{"name": "a"}, {"name": "b"}]}
        _set_key(data, "items[0]", {"name": "modified"})
        assert data["items"][0]["name"] == "modified"

    def test_set_key_current_dict(self):
        data = {}
        _set_key(data, "x", 1)
        assert data["x"] == 1

    def test_set_key_current_list(self):
        data = [0, 0, 0]
        _set_key(data, "1", 99)
        assert data[1] == 99


class TestApplyOverrides:
    def test_simple(self):
        data = {"options": {"host": "staging"}, "tasks": [{"name": "t1", "command": "echo"}]}
        overrides = {"options.host": "prod"}
        result = apply_overrides(data, overrides)
        assert result["options"]["host"] == "prod"

    def test_task_name_index(self):
        data = {"tasks": [{"name": "migrate", "timeout": 100}]}
        overrides = {'tasks["migrate"].timeout': 300}
        result = apply_overrides(data, overrides)
        assert result["tasks"][0]["timeout"] == 300

    def test_numeric_index(self):
        data = {"tasks": [{"name": "t1"}, {"name": "t2"}]}
        overrides = {"tasks[0].name": "renamed"}
        result = apply_overrides(data, overrides)
        assert result["tasks"][0]["name"] == "renamed"

    def test_deep(self):
        data = {"a": {"b": 1, "c": 2}}
        result = apply_overrides(data, {"a.b": 99})
        assert result["a"]["b"] == 99
        assert result["a"]["c"] == 2

    def test_does_not_mutate(self):
        data = {"x": 1}
        result = apply_overrides(data, {"x": 2})
        assert data["x"] == 1
        assert result["x"] == 2

    def test_with_name_index(self):
        data = {"tasks": [{"name": "migrate", "timeout": 100, "command": "echo"}]}
        result = apply_overrides(data, {'tasks["migrate"].timeout': 300})
        assert result["tasks"][0]["timeout"] == 300

    def test_with_numeric_index(self):
        data = {"tasks": [{"name": "t1"}, {"name": "t2"}]}
        result = apply_overrides(data, {"tasks[0].name": "renamed"})
        assert result["tasks"][0]["name"] == "renamed"

    def test_list_current(self):
        data = [{"name": "t1"}, {"name": "t2"}]
        result = apply_overrides(data, {"0.name": "renamed"})
        assert result[0]["name"] == "renamed"


class TestBuildEnv:
    def test_all_sources(self):
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

    def test_priority(self):
        env = build_env(
            system_env={"KEY": "low"},
            global_env={"KEY": "mid"},
            cli_env={"KEY": "high"},
        )
        assert env["KEY"] == "high"

    def test_none_defaults(self):
        result = build_env()
        assert result == {}

    def test_all_none(self):
        result = build_env(system_env={"X": "1"}, global_env=None, pipeline_env=None, task_env=None, cli_env=None)
        assert result["X"] == "1"


class TestExecutionContext:
    def test_basic(self):
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

    def test_get_task_env_with_global(self, setup_project, tmp_project):
        import taskpps.config as cfg

        old_settings = cfg._settings
        old_root = cfg._project_root
        cfg._settings = None
        try:
            cfg.set_project_root(tmp_project)
            s = cfg.load_settings(str(tmp_project / "taskpps.yaml"))
            pipeline = ResolvedPipeline(
                name="test",
                tasks=[ResolvedTask(name="t1", task_type="command", command="echo")],
                options=OptionsYAML(env={"PIPELINE_VAR": "pv"}),
            )
            ctx = ExecutionContext(pipeline=pipeline, run_id="abc", env={"CLI_VAR": "cv"})
            task = pipeline.tasks[0]
            env = ctx.get_task_env(task)
            assert env.get("PIPELINE_VAR") == "pv"
            assert env.get("CLI_VAR") == "cv"
            if "GLOBAL_VAR" in s.env:
                assert env.get("GLOBAL_VAR") == "global_value"
        finally:
            cfg._settings = old_settings
            cfg._project_root = old_root


class TestDomainExports:
    def test_task_exports(self):
        from taskpps.domain import task as domain_task_module

        assert hasattr(domain_task_module, "ResolvedPipeline")
        assert hasattr(domain_task_module, "ResolvedTask")
        assert "__all__" in dir(domain_task_module)
        assert "ResolvedPipeline" in domain_task_module.__all__
        assert "ResolvedTask" in domain_task_module.__all__

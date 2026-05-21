import pytest
from taskpps.domain.context import (
    _navigate_to_key,
    _set_key,
    set_dot_path,
    apply_overrides,
    resolve_dot_path,
    build_env,
    ExecutionContext,
)
from taskpps.domain.pipeline import ResolvedPipeline, ResolvedTask
from taskpps.schemas.pipeline import OptionsYAML


def test_navigate_to_key_current_dict():
    data = {"a": 1}
    result = _navigate_to_key(data, "a")
    assert result == 1


def test_navigate_to_key_current_list():
    data = [10, 20, 30]
    result = _navigate_to_key(data, "1")
    assert result == 20


def test_navigate_to_key_current_other():
    with pytest.raises(KeyError):
        _navigate_to_key("string", "key")


def test_navigate_to_key_numeric_index_list():
    data = {"items": [10, 20, 30]}
    result = _navigate_to_key(data, "items[2]")
    assert result == 30


def test_navigate_to_key_name_index_not_dict():
    data = [{"name": "foo", "val": 1}]
    result = _navigate_to_key(data, 'tasks["foo"]')
    assert result == {"name": "foo", "val": 1}


def test_set_key_name_index_not_found():
    data = {"tasks": [{"name": "foo"}]}
    with pytest.raises(KeyError):
        _set_key(data, 'tasks["missing"]', "val")


def test_set_key_numeric_index():
    data = {"items": [1, 2, 3]}
    _set_key(data, "items[1]", 99)
    assert data["items"][1] == 99


def test_set_key_numeric_index_container():
    data = {"items": [{"name": "a"}, {"name": "b"}]}
    _set_key(data, "items[0]", {"name": "modified"})
    assert data["items"][0]["name"] == "modified"


def test_set_key_current_dict():
    data = {}
    _set_key(data, "x", 1)
    assert data["x"] == 1


def test_set_key_current_list():
    data = [0, 0, 0]
    _set_key(data, "1", 99)
    assert data[1] == 99


def test_set_dot_path_name_index_not_found():
    data = {"tasks": [{"name": "foo"}]}

    with pytest.raises(KeyError):
        set_dot_path(data, 'tasks["missing"].timeout', 200)


def test_set_dot_path_numeric_index_set_value():
    data = {"items": [1, 2, 3]}
    set_dot_path(data, "items[2]", 999)
    assert data["items"][2] == 999


def test_set_dot_path_list_last_key():
    data = [1, 2, 3]
    set_dot_path(data, "1", 999)
    assert data[1] == 999


def test_apply_overrides_with_name_index():
    data = {"tasks": [{"name": "migrate", "timeout": 100, "command": "echo"}]}
    result = apply_overrides(data, {'tasks["migrate"].timeout': 300})
    assert result["tasks"][0]["timeout"] == 300


def test_apply_overrides_with_numeric_index():
    data = {"tasks": [{"name": "t1"}, {"name": "t2"}]}
    result = apply_overrides(data, {"tasks[0].name": "renamed"})
    assert result["tasks"][0]["name"] == "renamed"


def test_apply_overrides_list_current():
    data = [{"name": "t1"}, {"name": "t2"}]
    result = apply_overrides(data, {"0.name": "renamed"})
    assert result[0]["name"] == "renamed"


def test_resolve_dot_path_deep_nested():
    data = {"a": {"b": {"c": [1, 2, {"d": 42}]}}}
    result = resolve_dot_path(data, "a.b.c.2.d")
    assert result == 42


def test_build_env_none_defaults():
    result = build_env()
    assert "PATH" in result


def test_build_env_all_none():
    result = build_env(system_env={"X": "1"}, global_env=None, pipeline_env=None, task_env=None, cli_env=None)
    assert result["X"] == "1"


def test_execution_context_get_task_env_with_global(setup_project):
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
    assert env.get("GLOBAL_VAR") == "global_value"


def test_navigate_to_key_non_dict_non_list():
    current = "hello"
    with pytest.raises(KeyError):
        _navigate_to_key(current, "key")


def test_set_dot_path_name_index_missing_container():
    data = {"tasks": [{"name": "foo", "timeout": 100}]}
    with pytest.raises(KeyError):
        set_dot_path(data, 'tasks["missing"].timeout', 200)

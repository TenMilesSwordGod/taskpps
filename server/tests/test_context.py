import pytest

from taskpps.domain.context import _navigate_to_key, apply_overrides, resolve_dot_path, set_dot_path


def test_navigate_to_key_dict():
    data = {"a": {"b": 1}}
    result = _navigate_to_key(data, "a")
    assert result == {"b": 1}


def test_navigate_to_key_name_index():
    data = {"tasks": [{"name": "foo", "val": 1}, {"name": "bar", "val": 2}]}
    result = _navigate_to_key(data, 'tasks["bar"]')
    assert result == {"name": "bar", "val": 2}


def test_navigate_to_key_name_index_not_found():
    data = {"tasks": [{"name": "foo"}]}
    with pytest.raises(KeyError):
        _navigate_to_key(data, 'tasks["missing"]')


def test_navigate_to_key_numeric_index():
    data = {"items": [10, 20, 30]}
    result = _navigate_to_key(data, "items[1]")
    assert result == 20


def test_resolve_dot_path_deep():
    data = {"a": {"b": {"c": 42}}}
    result = resolve_dot_path(data, "a.b.c")
    assert result == 42


def test_apply_overrides_deep():
    data = {"a": {"b": 1, "c": 2}}
    result = apply_overrides(data, {"a.b": 99})
    assert result["a"]["b"] == 99
    assert result["a"]["c"] == 2


def test_apply_overrides_does_not_mutate():
    data = {"x": 1}
    result = apply_overrides(data, {"x": 2})
    assert data["x"] == 1
    assert result["x"] == 2


def test_set_dot_path_simple():
    data = {"x": 1}
    set_dot_path(data, "x", 2)
    assert data["x"] == 2


def test_set_dot_path_nested():
    data = {"a": {"b": 1}}
    set_dot_path(data, "a.b", 99)
    assert data["a"]["b"] == 99


def test_set_dot_path_numeric_index():
    data = {"items": [1, 2, 3]}
    set_dot_path(data, "items[1]", 99)
    assert data["items"][1] == 99


def test_set_dot_path_name_index():
    data = {"tasks": [{"name": "foo", "timeout": 100}]}
    set_dot_path(data, 'tasks["foo"].timeout', 200)
    assert data["tasks"][0]["timeout"] == 200

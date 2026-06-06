from __future__ import annotations

import pytest

from taskpps.domain.context import (
    ExecutionContext,
    apply_overrides,
    build_env,
    resolve_dot_path,
)
from taskpps.domain.pipeline import ResolvedPipeline, ResolvedTask
from taskpps.schemas.pipeline import PipelineConfig


def _make_pipeline(name: str = "test", env: dict | None = None) -> ResolvedPipeline:
    return ResolvedPipeline(
        name=name,
        tasks=[],
        options=PipelineConfig(env=env or {}),
    )


class TestBuildEnv:
    def test_empty(self):
        result = build_env()
        assert result == {}

    def test_system_env(self):
        result = build_env(system_env={"PATH": "/usr/bin"})
        assert result["PATH"] == "/usr/bin"

    def test_global_env(self):
        result = build_env(global_env={"GLOBAL": "val"})
        assert result["GLOBAL"] == "val"

    def test_pipeline_env(self):
        result = build_env(pipeline_env={"PIPE": "val"})
        assert result["PIPE"] == "val"

    def test_task_env(self):
        result = build_env(task_env={"TASK": "val"})
        assert result["TASK"] == "val"

    def test_cli_env(self):
        result = build_env(cli_env={"CLI": "val"})
        assert result["CLI"] == "val"

    def test_priority(self):
        result = build_env(
            system_env={"KEY": "system"},
            global_env={"KEY": "global"},
            pipeline_env={"KEY": "pipeline"},
            task_env={"KEY": "task"},
            cli_env={"KEY": "cli"},
        )
        assert result["KEY"] == "cli"

    def test_merge_all(self):
        result = build_env(
            system_env={"A": "1"},
            global_env={"B": "2"},
            pipeline_env={"C": "3"},
            task_env={"D": "4"},
            cli_env={"E": "5"},
        )
        assert len(result) == 5
        assert result["A"] == "1"
        assert result["E"] == "5"


class TestExecutionContext:
    def test_defaults(self):
        pipeline = _make_pipeline("test")
        ctx = ExecutionContext(pipeline=pipeline, run_id="run-1")
        assert ctx.pipeline == pipeline
        assert ctx.run_id == "run-1"
        assert ctx.env == {}

    def test_with_env(self):
        pipeline = _make_pipeline("test")
        ctx = ExecutionContext(pipeline=pipeline, run_id="run-1", env={"KEY": "VAL"})
        assert ctx.env == {"KEY": "VAL"}

    def test_set_and_get_workspace(self):
        pipeline = _make_pipeline("test")
        ctx = ExecutionContext(pipeline=pipeline, run_id="run-1")
        ctx.set_workspace("task1", "/tmp/ws1")
        assert ctx.get_workspace("task1") == "/tmp/ws1"

    def test_get_workspace_nonexistent(self):
        pipeline = _make_pipeline("test")
        ctx = ExecutionContext(pipeline=pipeline, run_id="run-1")
        assert ctx.get_workspace("nonexistent") is None

    def test_get_workspace_no_args(self):
        pipeline = _make_pipeline("test")
        ctx = ExecutionContext(pipeline=pipeline, run_id="run-1")
        ctx.set_workspace("task1", "/tmp/ws1")
        ctx.set_workspace("task2", "/tmp/ws2")
        assert ctx.get_workspace() == "/tmp/ws2"

    def test_get_workspace_no_args_empty(self):
        pipeline = _make_pipeline("test")
        ctx = ExecutionContext(pipeline=pipeline, run_id="run-1")
        assert ctx.get_workspace() is None

    def test_get_task_env(self, setup_project, tmp_project):
        import taskpps.config as cfg

        config_file = tmp_project / "taskpps.yaml"
        config_file.write_text("server:\n  host: 127.0.0.1\n  port: 26521\n")

        cfg.set_project_root(tmp_project)
        cfg._settings = None
        cfg.load_settings(str(config_file))

        pipeline = _make_pipeline("test", env={"PIPE": "pipe_val"})
        ctx = ExecutionContext(pipeline=pipeline, run_id="run-1", env={"CLI": "cli_val"})
        task = ResolvedTask(
            name="step1",
            task_type="command",
            command="echo",
            env={"TASK": "task_val"},
        )
        task_env = ctx.get_task_env(task)
        assert task_env["PIPE"] == "pipe_val"
        assert task_env["CLI"] == "cli_val"
        assert task_env["TASK"] == "task_val"


class TestResolveDotPath:
    def test_simple_key(self):
        data = {"key": "value"}
        assert resolve_dot_path(data, "key") == "value"

    def test_nested_key(self):
        data = {"a": {"b": "c"}}
        assert resolve_dot_path(data, "a.b") == "c"

    def test_deep_nested(self):
        data = {"a": {"b": {"c": {"d": "value"}}}}
        assert resolve_dot_path(data, "a.b.c.d") == "value"

    def test_list_index(self):
        data = {"items": ["a", "b", "c"]}
        assert resolve_dot_path(data, "items.1") == "b"

    def test_key_error(self):
        data = {"key": "value"}
        with pytest.raises(KeyError):
            resolve_dot_path(data, "missing")


class TestApplyOverrides:
    def test_empty_overrides(self):
        from copy import deepcopy
        data = {"name": "test", "tasks": []}
        original = deepcopy(data)
        result = apply_overrides(data, {})
        assert result == original

    def test_options_override(self):
        data = {
            "name": "test",
            "options": {"timeout": 60, "on_failure": "fail"},
            "tasks": [],
        }
        result = apply_overrides(data, {"options.timeout": 120})
        assert result["options"]["timeout"] == 120

    def test_config_override(self):
        data = {
            "name": "test",
            "config": {"retry": 0, "on_failure": "fail"},
            "tasks": [],
        }
        result = apply_overrides(data, {"config.retry": 3})
        assert result["config"]["retry"] == 3

    def test_invalid_override_path(self):
        data = {"name": "test", "tasks": []}
        with pytest.raises(ValueError):
            apply_overrides(data, {"name": "new_name"})

    def test_task_override(self):
        data = {
            "name": "test",
            "tasks": [
                {"name": "step1", "command": "echo", "timeout": 60},
            ],
        }
        result = apply_overrides(data, {'tasks["step1"].timeout': 120})
        assert result["tasks"][0]["timeout"] == 120

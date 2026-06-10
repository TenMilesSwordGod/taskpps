from __future__ import annotations

import re
from typing import Any

from taskpps.config import get_settings
from taskpps.domain.pipeline import ResolvedPipeline, ResolvedSubPipeline, ResolvedTask

_NAME_INDEX_PATTERN = re.compile(r'^(\w+)\["([^"]+)"\]$')
_NUMERIC_INDEX_PATTERN = re.compile(r"^(\w+)\[(\d+)\]$")


def _navigate_to_key(current: Any, key: str) -> Any:
    m = _NAME_INDEX_PATTERN.match(key)
    m2 = _NUMERIC_INDEX_PATTERN.match(key)
    if m:
        field = m.group(1)
        name = m.group(2)
        container = current[field] if isinstance(current, dict) else current
        if isinstance(container, list):
            for item in container:
                if isinstance(item, dict) and item.get("name") == name:
                    return item
            raise KeyError(f"Item with name '{name}' not found in '{field}'")
        return container
    elif m2:
        field = m2.group(1)
        idx = int(m2.group(2))
        container = current[field] if isinstance(current, dict) else current
        if isinstance(container, list):
            return container[idx]
        return container
    elif isinstance(current, dict):
        return current[key]
    elif isinstance(current, list):
        return current[int(key)]
    else:
        raise KeyError(f"Cannot resolve key '{key}'")


def _set_key(current: Any, key: str, value: Any) -> None:
    m = _NAME_INDEX_PATTERN.match(key)
    m2 = _NUMERIC_INDEX_PATTERN.match(key)
    if m:
        field = m.group(1)
        name = m.group(2)
        container = current[field] if isinstance(current, dict) else current
        if isinstance(container, list):
            for item in container:
                if isinstance(item, dict) and item.get("name") == name:
                    item[key.split(".")[-1] if "." in key else list(item.keys())[-1]] = value
                    return
            raise KeyError(f"Item with name '{name}' not found in '{field}'")
    elif m2:
        field = m2.group(1)
        idx = int(m2.group(2))
        container = current[field] if isinstance(current, dict) else current
        if isinstance(container, list):
            container[idx] = value
            return
    if isinstance(current, dict):
        current[key] = value
    elif isinstance(current, list):
        current[int(key)] = value


def resolve_dot_path(data: dict, path: str) -> Any:
    keys = path.split(".")
    current = data
    for key in keys:
        current = _navigate_to_key(current, key)
    return current


def set_dot_path(data: dict, path: str, value: Any) -> None:
    keys = path.split(".")
    current = data
    for key in keys[:-1]:
        current = _navigate_to_key(current, key)
    last_key = keys[-1]
    m = _NAME_INDEX_PATTERN.match(last_key)
    m2 = _NUMERIC_INDEX_PATTERN.match(last_key)

    if m:
        field = m.group(1)
        name = m.group(2)
        container = current.get(field) if isinstance(current, dict) else current
        if isinstance(container, list):
            for item in container:
                if isinstance(item, dict) and item.get("name") == name:
                    return
            raise KeyError(f"Item with name '{name}' not found in '{field}'")
    elif m2:
        field = m2.group(1)
        idx = int(m2.group(2))
        container = current.get(field) if isinstance(current, dict) else current
        if isinstance(container, list):
            container[idx] = value
            return

    if isinstance(current, dict):
        current[last_key] = value
    elif isinstance(current, list):
        current[int(last_key)] = value


_ALLOWED_OVERRIDE_PATHS = {
    "options.host",
    "options.credential",
    "options.timeout",
    "options.on_failure",
    "options.env",
    "config.host",
    "config.credential",
    "config.timeout",
    "config.on_failure",
    "config.env",
    "config.retry",
    "config.execution_strategy",
}

_ALLOWED_TASK_OVERRIDE_KEYS = {
    "timeout",
    "on_failure",
    "env",
    "cwd",
    "host",
    "credential",
    "retry",
    "when",
}


def apply_overrides(pipeline_data: dict, overrides: dict[str, Any]) -> dict:
    import copy

    data = copy.deepcopy(pipeline_data)
    for path, value in overrides.items():
        keys = path.split(".")
        if len(keys) >= 2 and keys[0] in ("options", "config"):
            if path not in _ALLOWED_OVERRIDE_PATHS:
                raise ValueError(f"Override path not allowed: {path}")
        elif len(keys) >= 2 and keys[0] == "tasks":
            if len(keys) < 3:
                raise ValueError(f"Task override must specify a field: {path}")
            last_key = keys[-1]
            if last_key not in _ALLOWED_TASK_OVERRIDE_KEYS:
                raise ValueError(f"Task override key not allowed: {last_key}")
        elif keys[0] in ("name",):
            raise ValueError(f"Override path not allowed: {path}")

        current = data
        for key in keys[:-1]:
            current = _navigate_to_key(current, key)
        last_key = keys[-1]
        if isinstance(current, dict):
            current[last_key] = value
        elif isinstance(current, list):
            current[int(last_key)] = value
    return data


def build_env(
    system_env: dict[str, str] | None = None,
    global_env: dict[str, str] | None = None,
    pipeline_env: dict[str, str] | None = None,
    task_env: dict[str, str] | None = None,
    cli_env: dict[str, str] | None = None,
) -> dict[str, str]:
    result = dict(system_env) if system_env is not None else {}
    if global_env:
        result.update(global_env)
    if pipeline_env:
        result.update(pipeline_env)
    if task_env:
        result.update(task_env)
    if cli_env:
        result.update(cli_env)
    return result


class ExecutionContext:
    def __init__(
        self,
        pipeline: ResolvedPipeline,
        run_id: str,
        env: dict[str, str] | None = None,
        project_workdir: str | None = None,
    ):
        self.pipeline = pipeline
        self.run_id = run_id
        self.env = env or {}
        self.project_workdir = project_workdir
        self._workspaces: dict[str, str] = {}

    def set_workspace(self, task_name: str, path: str) -> None:
        self._workspaces[task_name] = path

    def get_workspace(self, task_name: str | None = None) -> str | None:
        if task_name:
            return self._workspaces.get(task_name)
        if self._workspaces:
            return next(reversed(self._workspaces.values()))
        return None

    def get_task_env(self, task: ResolvedTask) -> dict[str, str]:
        settings = get_settings()
        return build_env(
            global_env=settings.env,
            pipeline_env=self.pipeline.top_config.env,
            task_env=task.env,
            cli_env=self.env,
        )

    def get_subpipeline_env(self, sub: ResolvedSubPipeline) -> dict[str, str]:
        settings = get_settings()
        return build_env(
            global_env=settings.env,
            pipeline_env=sub.config.env,
            cli_env=self.env,
        )

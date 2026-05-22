from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml
from pydantic import BaseModel, Field


class ServerConfig(BaseModel):
    host: str = "127.0.0.1"
    port: int = 26521
    api_key: Optional[str] = None


class ExecutorConfig(BaseModel):
    default_timeout: int = 3600
    max_workers: int = 10
    shell: str = "/bin/bash"


class PluginsConfig(BaseModel):
    paths: List[str] = Field(default_factory=lambda: ["plugins"])


class TriggerConfig(BaseModel):
    type: str
    schedule: Optional[str] = None
    pipeline: str


class Settings(BaseModel):
    server: ServerConfig = Field(default_factory=ServerConfig)
    executor: ExecutorConfig = Field(default_factory=ExecutorConfig)
    env: Dict[str, str] = Field(default_factory=dict)
    plugins: PluginsConfig = Field(default_factory=PluginsConfig)
    triggers: List[TriggerConfig] = Field(default_factory=list)

    model_config = {"extra": "allow"}


_settings: Optional[Settings] = None
_project_root: Optional[Path] = None


def find_project_root() -> Path:
    global _project_root
    if _project_root is not None:
        return _project_root
    current = Path.cwd()
    for _ in range(10):
        # Check both .taskpps/taskpps.yaml (new) and taskpps.yaml (old for backwards compatibility)
        if (current / ".taskpps" / "taskpps.yaml").exists() or (current / "taskpps.yaml").exists():
            _project_root = current
            return current
        parent = current.parent
        if parent == current:
            break
        current = parent
    _project_root = Path.cwd()
    return _project_root


def set_project_root(path: Path) -> None:
    global _project_root
    _project_root = path.resolve()


def load_settings(config_path: Optional[str] = None) -> Settings:
    global _settings
    if config_path is not None:
        p = Path(config_path)
    else:
        root = find_project_root()
        # Prefer .taskpps/taskpps.yaml, fall back to taskpps.yaml
        p = root / ".taskpps" / "taskpps.yaml"
        if not p.exists():
            p = root / "taskpps.yaml"

    if p.exists():
        with open(p) as f:
            data = yaml.safe_load(f) or {}
        _settings = Settings(**data)
    else:
        _settings = Settings()
    return _settings


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = load_settings()
    return _settings


def get_data_dir() -> Path:
    root = find_project_root()
    data_dir = root / ".taskpps"
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir


def get_db_path() -> Path:
    return get_data_dir() / "state.db"


def get_logs_dir() -> Path:
    logs = get_data_dir() / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    return logs


def get_pipelines_dir() -> Path:
    return find_project_root() / "pipelines"


def get_agents_dir() -> Path:
    return find_project_root() / "agents"


def get_credentials_dir() -> Path:
    return find_project_root() / "credentials"


def get_tasks_dir() -> Path:
    return find_project_root() / "tasks"


def get_plugins_dir() -> Path:
    return find_project_root() / "plugins"

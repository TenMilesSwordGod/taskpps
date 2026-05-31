from __future__ import annotations

import hashlib
from pathlib import Path

import yaml
from pydantic import BaseModel, Field


class ServerConfig(BaseModel):
    host: str = "127.0.0.1"
    port: int = 26521
    api_key: str | None = None


class ExecutorConfig(BaseModel):
    default_timeout: int = 3600
    max_workers: int = 10
    shell: str = "/bin/bash"


class PluginsConfig(BaseModel):
    paths: list[str] = Field(default_factory=lambda: ["plugins"])


class TriggerConfig(BaseModel):
    type: str
    schedule: str | None = None
    pipeline: str


class Settings(BaseModel):
    locale: str = "zh"
    server: ServerConfig = Field(default_factory=ServerConfig)
    executor: ExecutorConfig = Field(default_factory=ExecutorConfig)
    env: dict[str, str] = Field(default_factory=dict)
    plugins: PluginsConfig = Field(default_factory=PluginsConfig)
    triggers: list[TriggerConfig] = Field(default_factory=list)

    model_config = {"extra": "allow"}


_settings: Settings | None = None
_project_root: Path | None = None


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


def load_settings(config_path: str | None = None) -> Settings:
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


def get_workspaces_dir() -> Path:
    workspaces = get_data_dir() / "workspaces"
    workspaces.mkdir(parents=True, exist_ok=True)
    return workspaces


def compute_pipeline_id(pipeline_file: str) -> str:
    return Path(pipeline_file).with_suffix("").as_posix().replace("/", "_")


def compute_pipeline_version(pipeline_file: str) -> str:
    pipelines_dir = get_pipelines_dir()
    p = Path(pipeline_file)
    if len(p.parts) > 0 and p.parts[0] == pipelines_dir.name:
        p = Path(*p.parts[1:])
        pipeline_file = str(p)
    path = pipelines_dir / pipeline_file
    if not path.exists():
        return ""
    content = path.read_bytes()
    return hashlib.sha256(content).hexdigest()[:8]


def build_log_path(pipeline_id: str, pipeline_version: str, run_id: str, task_name: str) -> Path:
    logs_dir = get_logs_dir()
    log_dir = logs_dir / pipeline_id / f"v_{pipeline_version}" / "builds" / run_id / task_name
    log_dir.mkdir(parents=True, exist_ok=True)
    return log_dir / "output.log"


def build_legacy_log_path(pipeline_file: str, run_id: str, task_run_id: str) -> Path:
    logs_dir = get_logs_dir()
    log_rel_dir = Path(pipeline_file).with_suffix("") if pipeline_file else Path("unknown")
    log_dir = logs_dir / log_rel_dir / run_id / task_run_id
    log_dir.mkdir(parents=True, exist_ok=True)
    return log_dir / "output.log"

from __future__ import annotations

import hashlib
import os
from pathlib import Path

import yaml
from pydantic import BaseModel, Field


class ServerConfig(BaseModel):
    host: str = "127.0.0.1"
    port: int = 26521
    api_key: str | None = None


class JWTConfig(BaseModel):
    """JWT 认证配置。

    设计决策：
    - secret 不在此配置，由 security.py 持久化到 .taskpps/jwt_secret.key（避免明文落 yaml）。
    - expire_hours 默认 24h，平衡安全性与用户体验（太短频繁登录，太长泄漏风险高）。
    - seed_admin_password 默认 user@123（issue #204 评论1要求），首次登录后应立即修改。
    """

    expire_hours: int = 24
    seed_admin_password: str = "user@123"
    seed_admin_username: str = "admin"


class AgentConfig(BaseModel):
    enabled: bool = True
    ws_host: str = "0.0.0.0"
    ws_port: int = 28765
    ws_tls: bool = False
    ws_cert_file: str = ""
    ws_key_file: str = ""
    heartbeat_interval: int = 15
    heartbeat_timeout: int = 45
    reconnect_max_interval: int = 60
    bootstrap_timeout: int = 30


class ExecutorConfig(BaseModel):
    default_timeout: int = 3600
    max_workers: int = 10
    shell: str = "/bin/bash"
    # Issue #78: agent 占用排队超时（秒），0 表示不等待直接失败
    # Issue #101: 默认排队超时从 300s 优化为 6 小时
    agent_queue_timeout: int = 21600
    # Issue #78: agent 断连等待重连超时（秒），0 表示不等待直接失败
    agent_offline_timeout: int = 300
    # Issue #106: 全局并发限制（0 表示无限制）
    global_max_concurrent: int = 0


class PluginsConfig(BaseModel):
    paths: list[str] = Field(default_factory=lambda: ["plugins"])


class TriggerConfig(BaseModel):
    type: str
    schedule: str | None = None
    pipeline: str


class Settings(BaseModel):
    locale: str = "zh"
    workdir: str | None = None
    server_home: str | None = None
    server: ServerConfig = Field(default_factory=ServerConfig)
    executor: ExecutorConfig = Field(default_factory=ExecutorConfig)
    agent: AgentConfig = Field(default_factory=AgentConfig)
    env: dict[str, str] = Field(default_factory=dict)
    plugins: PluginsConfig = Field(default_factory=PluginsConfig)
    triggers: list[TriggerConfig] = Field(default_factory=list)
    # Issue #204: JWT 认证配置（用户管理系统）
    jwt: JWTConfig = Field(default_factory=JWTConfig)

    model_config = {"extra": "allow"}


_settings: Settings | None = None
_project_root: Path | None = None
_server_home: Path | None = None
_project_workdir: Path | None = None


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
    global _project_root, _server_home, _project_workdir
    _project_root = path.resolve()
    _server_home = path.resolve()
    _project_workdir = path.resolve()


def set_server_home(path: Path) -> None:
    global _server_home
    _server_home = path.resolve()


def set_project_workdir(path: Path) -> None:
    global _project_workdir
    _project_workdir = path.resolve()


def load_settings(config_path: str | None = None) -> Settings:
    global _settings
    if config_path is not None:
        p = Path(config_path)
    else:
        # 优先使用 TASKPPS_CONFIG 环境变量，避免 import 阶段触发 find_project_root()
        env_config = os.environ.get("TASKPPS_CONFIG")
        if env_config:
            p = Path(env_config)
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


def get_project_workdir() -> Path:
    """获取默认项目工作目录。

    优先级: 全局缓存 > TASKPPS_WORKDIR 环境变量(混合期兼容) > settings.workdir > find_project_root()
    """
    global _project_workdir
    if _project_workdir is not None:
        return _project_workdir
    env_workdir = os.environ.get("TASKPPS_WORKDIR")
    if env_workdir:
        import logging

        logging.getLogger("taskpps").warning("TASKPPS_WORKDIR is deprecated, use project registration instead")
        return Path(env_workdir)
    settings = get_settings()
    if settings.workdir:
        return Path(settings.workdir)
    return find_project_root()


def get_project_workdir_by_id(project_id: str | None) -> Path | None:
    """根据 project_id 从 DB 查询项目工作目录。

    project_id 为 None 时返回 None（由调用方决定回退行为）。
    """
    if project_id is None:
        return None
    try:
        import asyncio

        from taskpps.db.engine import get_session_factory
        from taskpps.db.repository import ProjectRepository

        async def _query():
            async with get_session_factory()() as session:
                repo = ProjectRepository(session)
                project = await repo.get_project(project_id)
                if project:
                    return Path(project.workdir)
                return None

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None
        if loop and loop.is_running():
            # 在已有 event loop 中无法直接 await，用线程安全方式
            import concurrent.futures

            with concurrent.futures.ThreadPoolExecutor() as pool:
                future = pool.submit(asyncio.run, _query())
                return future.result()
        else:
            return asyncio.run(_query())
    except Exception:
        return None


def get_server_home() -> Path:
    global _server_home
    if _server_home is not None:
        return _server_home
    env_server = os.environ.get("TASKPPS_SERVER_HOME")
    if env_server:
        return Path(env_server)
    # import 阶段不调用 get_settings() 以避免触发 find_project_root()
    # 直接使用代码路径推导
    return Path(__file__).resolve().parent.parent.parent


def get_data_dir() -> Path:
    """返回部署根目录下的数据目录（如 state.db），与项目 workdir 解耦。"""
    data_dir = get_server_home() / ".taskpps"
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir


def get_db_path() -> Path:
    return get_data_dir() / "state.db"


def get_logs_dir() -> Path:
    """返回部署根目录下的日志目录，与项目 workdir 解耦。"""
    logs = get_server_home() / ".taskpps" / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    return logs


def _ensure_path(p: Path | str | None) -> Path | None:
    if p is None or isinstance(p, Path):
        return p
    return Path(p)


def get_pipelines_dir(project_workdir: Path | str | None = None) -> Path:
    return (_ensure_path(project_workdir) or get_project_workdir()) / "pipelines"


def get_agents_dir(project_workdir: Path | str | None = None) -> Path:
    return (_ensure_path(project_workdir) or get_project_workdir()) / "agents"


def get_credentials_dir(project_workdir: Path | str | None = None) -> Path:
    return (_ensure_path(project_workdir) or get_project_workdir()) / "credentials"


def get_tasks_dir(project_workdir: Path | str | None = None) -> Path:
    return (_ensure_path(project_workdir) or get_project_workdir()) / "tasks"


def get_plugins_dir(project_workdir: Path | str | None = None) -> Path:
    return (_ensure_path(project_workdir) or get_project_workdir()) / "plugins"


def get_workspaces_dir(project_workdir: Path | str | None = None) -> Path:
    workspaces = (_ensure_path(project_workdir) or get_project_workdir()) / ".taskpps" / "workspaces"
    workspaces.mkdir(parents=True, exist_ok=True)
    return workspaces


def compute_pipeline_id(pipeline_file: str) -> str:
    return Path(pipeline_file).with_suffix("").as_posix().replace("/", "_")


def compute_pipeline_version(pipeline_file: str, pipelines_dir: Path | None = None) -> str:
    pd = pipelines_dir or get_pipelines_dir()
    p = Path(pipeline_file)
    if len(p.parts) > 0 and p.parts[0] == pd.name:
        p = Path(*p.parts[1:])
        pipeline_file = str(p)
    path = pd / pipeline_file
    if not path.exists():
        return ""
    content = path.read_bytes()
    return hashlib.sha256(content).hexdigest()[:8]


def build_log_path(pipeline_id: str, pipeline_version: str, run_id: str, task_name: str) -> Path:
    logs_dir = get_logs_dir()
    log_dir = logs_dir / pipeline_id / f"v_{pipeline_version}" / "builds" / run_id / task_name
    log_dir.mkdir(parents=True, exist_ok=True)
    return log_dir / "task.log"


def build_pipeline_log_path(pipeline_id: str, pipeline_version: str, run_id: str) -> Path:
    logs_dir = get_logs_dir()
    log_dir = logs_dir / pipeline_id / f"v_{pipeline_version}" / "builds" / run_id
    log_dir.mkdir(parents=True, exist_ok=True)
    return log_dir / "console.log"


def build_legacy_log_path(pipeline_file: str, run_id: str, task_run_id: str) -> Path:
    logs_dir = get_logs_dir()
    log_rel_dir = Path(pipeline_file).with_suffix("") if pipeline_file else Path("unknown")
    log_dir = logs_dir / log_rel_dir / run_id / task_run_id
    log_dir.mkdir(parents=True, exist_ok=True)
    return log_dir / "task.log"


def build_retry_log_path(
    pipeline_id: str, pipeline_version: str, run_id: str, task_name: str, retry_version: int
) -> Path:
    base = get_logs_dir() / pipeline_id / f"v_{pipeline_version}" / "builds" / run_id
    retry_dir = base / "retries"
    retry_dir.mkdir(parents=True, exist_ok=True)
    return retry_dir / f"{task_name}.retry-{retry_version}.log"

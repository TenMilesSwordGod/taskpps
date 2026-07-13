import logging
import os
import re
from pathlib import Path
from typing import Any

import yaml

from taskpps.config import get_agents_dir, get_pipelines_dir, get_settings
from taskpps.i18n import t
from taskpps.schemas.pipeline import PipelineYAML

log = logging.getLogger(__name__)

_VAR_PATTERN = re.compile(r"\$\{([^}]+)\}")

_credential_loader = None
_agent_loader = None


def _get_credential_loader(project_workdir: Path | None = None):
    global _credential_loader
    if project_workdir is not None:
        from taskpps.loaders.credential_loader import CredentialLoader

        return CredentialLoader(project_workdir / "credentials")
    if _credential_loader is None:
        from taskpps.loaders.credential_loader import CredentialLoader

        _credential_loader = CredentialLoader()
    return _credential_loader


def _get_agent_loader(project_workdir: Path | None = None):
    global _agent_loader
    if project_workdir is not None:
        from taskpps.loaders.agent_loader import AgentLoader

        return AgentLoader(get_agents_dir(project_workdir))
    if _agent_loader is None:
        from taskpps.loaders.agent_loader import AgentLoader

        _agent_loader = AgentLoader()
    return _agent_loader


# AgentConnection 字段名 → 属性名的映射（用于 WebSocket 连接 fallback）
_AGENT_CONNECTION_FIELD_MAP = {
    "host": ("hostname", "ip"),
    "hostname": ("hostname",),
    "ip": ("ip",),
    "platform": ("platform",),
    "system": ("system",),
    "arch": ("arch",),
    "agent_version": ("agent_version",),
    "id": ("agent_id",),
}


def _resolve_agent_field_from_connection(agent_id: str, field: str) -> str | None:
    """配置文件中找不到 agent 时，尝试从 AgentManager 的 WebSocket 连接解析字段。

    与 create_executor 的 fallback 逻辑保持一致：execution-agent 可能没有
    agents/ 配置文件，仅通过 WebSocket 连接注册。
    """
    try:
        from taskpps.services.agent_manager import AgentManager

        conn = AgentManager.instance().get_connection(agent_id)
        if conn is None:
            return None
        attr_names = _AGENT_CONNECTION_FIELD_MAP.get(field)
        if attr_names is None:
            return None
        for attr in attr_names:
            value = getattr(conn, attr, "")
            if value:
                return str(value)
        return ""
    except Exception:
        return None


def _resolve_variable_match(match, env: dict[str, str], project_workdir: Path | None = None) -> str:
    ref = match.group(1)

    if ref.startswith("credential:"):
        try:
            rest = ref.split(":", 1)[1]
            cred_id, field = rest.split(".", 1)
            cred_loader = _get_credential_loader(project_workdir)
            return str(cred_loader.get_field(cred_id, field))
        except (ValueError, KeyError) as e:
            import logging

            logging.getLogger("taskpps.pipelines").warning(
                t("Failed to resolve variable '{ref}': {error}", ref=ref, error=str(e))
            )
            return match.group(0)

    elif ref.startswith("agent:"):
        try:
            rest = ref.split(":", 1)[1]
            agent_id, field = rest.split(".", 1)
            agent_loader = _get_agent_loader(project_workdir)
            try:
                return str(agent_loader.get_field(agent_id, field))
            except KeyError:
                # 配置文件中未找到 agent，尝试从 WebSocket 连接解析
                # 与 create_executor 的 fallback 逻辑保持一致（executors/__init__.py:72-80）
                resolved = _resolve_agent_field_from_connection(agent_id, field)
                if resolved is not None:
                    return resolved
                raise
        except (ValueError, KeyError) as e:
            import logging

            logging.getLogger("taskpps.pipelines").warning(
                t("Failed to resolve variable '{ref}': {error}", ref=ref, error=str(e))
            )
            return match.group(0)

    elif ref.startswith("env."):
        key = ref[4:]
        # 按优先级查找: 传入的 env > settings.env > os.environ
        if key in env:
            return env[key]
        settings = get_settings()
        if key in settings.env:
            return settings.env[key]
        return os.environ.get(key, match.group(0))

    else:
        # 按优先级查找: 传入的 env > settings.env > os.environ
        if ref in env:
            return env[ref]
        settings = get_settings()
        if ref in settings.env:
            return settings.env[ref]
        if ref in os.environ:
            return os.environ[ref]
        return match.group(0)


def substitute_env_vars(value: Any, env: dict[str, str], project_workdir: Path | None = None) -> Any:
    if isinstance(value, str):
        result = value
        for _ in range(10):
            new_result = _VAR_PATTERN.sub(lambda m: _resolve_variable_match(m, env, project_workdir), result)
            if new_result == result:
                break
            result = new_result
        return result
    if isinstance(value, dict):
        return {k: substitute_env_vars(v, env, project_workdir) for k, v in value.items()}
    if isinstance(value, list):
        return [substitute_env_vars(item, env, project_workdir) for item in value]
    return value


class PipelineLoader:
    def __init__(self, base_dir: Path | None = None):
        self._base_dir = base_dir

    @property
    def base_dir(self) -> Path:
        return self._base_dir or get_pipelines_dir()

    def load(self, pipeline_file: str, env: dict[str, str] | None = None, project_workdir: Path | None = None) -> PipelineYAML:
        p = Path(pipeline_file)
        if len(p.parts) > 0 and p.parts[0] == self.base_dir.name:
            p = Path(*p.parts[1:])
            pipeline_file = str(p)
        path = self.base_dir / pipeline_file
        try:
            resolved = path.resolve()
            if not str(resolved).startswith(str(self.base_dir.resolve())):
                raise FileNotFoundError(t("Path traversal not allowed: {path}", path=pipeline_file))
        except (OSError, ValueError):
            raise FileNotFoundError(t("Invalid pipeline file path: {path}", path=pipeline_file)) from None

        if not path.exists():
            raise FileNotFoundError(t("Pipeline file not found: {path}", path=pipeline_file))

        with open(path) as f:
            data = yaml.safe_load(f)

        if data is None:
            raise ValueError(t("Pipeline file is empty: {path}", path=pipeline_file))

        # 提取 pipeline 自身的 config.env，合并到 env 中，使这些变量在替换时可用
        # 解决 config.env 中定义的变量无法在命令中通过 ${env.X} 引用的问题
        # 优先级: 传入的 env (params) > config.env
        config_env = (data.get("config") or {}).get("env") or {}
        if isinstance(config_env, dict) and config_env:
            merged = dict(config_env)
            merged.update(env or {})
            env = merged

        # 始终执行变量替换, 即使 env 为空也支持 settings.env 和 os.environ
        # 传递项目工作目录, 使 agent/credential 变量替换能找到项目目录下的配置
        # 优先使用显式传入的 project_workdir, 其次从 base_dir 推导
        effective_workdir = project_workdir or (self.base_dir.parent if self._base_dir is not None else None)
        data = substitute_env_vars(data, env or {}, effective_workdir)

        return PipelineYAML(**data)

    def load_all(self) -> dict[str, PipelineYAML]:
        result = {}
        base = self.base_dir
        if not base.exists():
            return result
        for path in sorted(base.glob("**/*.yaml")):
            try:
                rel = path.relative_to(base)
                spec = self.load(str(rel))
                result[spec.name] = spec
            except Exception as e:
                log.warning("跳过无效 pipeline 文件 %s: %s", path, e)
                continue
        for path in sorted(base.glob("**/*.yml")):
            try:
                rel = path.relative_to(base)
                spec = self.load(str(rel))
                result[spec.name] = spec
            except Exception as e:
                log.warning("跳过无效 pipeline 文件 %s: %s", path, e)
                continue
        return result

    def load_all_with_files(self) -> dict[str, PipelineYAML]:
        """加载所有流水线，返回以文件相对路径为 key 的映射"""
        result = {}
        base = self.base_dir
        if not base.exists():
            return result
        for path in sorted(base.glob("**/*.yaml")):
            try:
                rel = path.relative_to(base)
                spec = self.load(str(rel))
                result[str(rel)] = spec
            except Exception as e:
                log.warning("跳过无效 pipeline 文件 %s: %s", path, e)
                continue
        for path in sorted(base.glob("**/*.yml")):
            try:
                rel = path.relative_to(base)
                spec = self.load(str(rel))
                result[str(rel)] = spec
            except Exception as e:
                log.warning("跳过无效 pipeline 文件 %s: %s", path, e)
                continue
        return result

    def parse_dict(self, data: dict, env: dict[str, str] | None = None, project_workdir: Path | None = None) -> PipelineYAML:
        if env is None:
            env = {}

        config_env = (data.get("config") or {}).get("env") or {}
        if isinstance(config_env, dict) and config_env:
            merged = dict(config_env)
            merged.update(env)
            env = merged

        effective_workdir = project_workdir or (self.base_dir.parent if self._base_dir is not None else None)
        data = substitute_env_vars(data, env, effective_workdir)

        return PipelineYAML(**data)

import os
import re
from pathlib import Path
from typing import Any, Dict, Optional

import yaml

from taskpps.config import get_pipelines_dir
from taskpps.i18n import t
from taskpps.schemas.pipeline import PipelineYAML


_VAR_PATTERN = re.compile(r"\$\{([^}]+)\}")

_credential_loader = None
_agent_loader = None


def _get_credential_loader():
    global _credential_loader
    if _credential_loader is None:
        from taskpps.loaders.credential_loader import CredentialLoader
        _credential_loader = CredentialLoader()
    return _credential_loader


def _get_agent_loader():
    global _agent_loader
    if _agent_loader is None:
        from taskpps.loaders.agent_loader import AgentLoader
        _agent_loader = AgentLoader()
    return _agent_loader


def _resolve_variable_match(match, env: Dict[str, str]) -> str:
    ref = match.group(1)

    if ref.startswith("credential:"):
        try:
            rest = ref.split(":", 1)[1]
            cred_id, field = rest.split(".", 1)
            cred_loader = _get_credential_loader()
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
            agent_loader = _get_agent_loader()
            return str(agent_loader.get_field(agent_id, field))
        except (ValueError, KeyError) as e:
            import logging
            logging.getLogger("taskpps.pipelines").warning(
                t("Failed to resolve variable '{ref}': {error}", ref=ref, error=str(e))
            )
            return match.group(0)

    elif ref.startswith("env."):
        key = ref[4:]
        return os.environ.get(key, env.get(key, match.group(0)))

    else:
        if ref in env:
            return env[ref]
        if ref in os.environ:
            return os.environ[ref]
        return match.group(0)


def substitute_env_vars(value: Any, env: Dict[str, str]) -> Any:
    if isinstance(value, str):
        return _VAR_PATTERN.sub(lambda m: _resolve_variable_match(m, env), value)
    if isinstance(value, dict):
        return {k: substitute_env_vars(v, env) for k, v in value.items()}
    if isinstance(value, list):
        return [substitute_env_vars(item, env) for item in value]
    return value


class PipelineLoader:
    def __init__(self, base_dir: Optional[Path] = None):
        self._base_dir = base_dir

    @property
    def base_dir(self) -> Path:
        return self._base_dir or get_pipelines_dir()

    def load(self, pipeline_file: str, env: Optional[Dict[str, str]] = None) -> PipelineYAML:
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
            raise FileNotFoundError(t("Invalid pipeline file path: {path}", path=pipeline_file))

        if not path.exists():
            raise FileNotFoundError(t("Pipeline file not found: {path}", path=pipeline_file))

        with open(path) as f:
            data = yaml.safe_load(f)

        if data is None:
            raise ValueError(t("Pipeline file is empty: {path}", path=pipeline_file))

        if env:
            data = substitute_env_vars(data, env)

        return PipelineYAML(**data)

    def load_all(self) -> Dict[str, PipelineYAML]:
        result = {}
        base = self.base_dir
        if not base.exists():
            return result
        for path in sorted(base.glob("**/*.yaml")):
            try:
                rel = path.relative_to(base)
                spec = self.load(str(rel))
                result[spec.name] = spec
            except Exception:
                continue
        for path in sorted(base.glob("**/*.yml")):
            try:
                rel = path.relative_to(base)
                spec = self.load(str(rel))
                result[spec.name] = spec
            except Exception:
                continue
        return result
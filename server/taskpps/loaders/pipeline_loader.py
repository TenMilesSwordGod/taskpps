import os
import re
from pathlib import Path
from typing import Any, Dict, Optional

import yaml

from taskpps.config import get_pipelines_dir
from taskpps.i18n import t
from taskpps.schemas.pipeline import PipelineYAML


_ENV_PATTERN = re.compile(r"\$\{([^}]+)\}")


def substitute_env_vars(value: Any, env: Dict[str, str]) -> Any:
    if isinstance(value, str):
        def _replace(match):
            var_name = match.group(1)
            if var_name in env:
                return env[var_name]
            if var_name in os.environ:
                return os.environ[var_name]
            return match.group(0)
        return _ENV_PATTERN.sub(_replace, value)
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

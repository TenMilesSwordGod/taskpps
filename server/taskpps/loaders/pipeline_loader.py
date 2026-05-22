import os
import re
from pathlib import Path
from typing import Any, Dict, Optional

import yaml

from taskpps.config import get_pipelines_dir
from taskpps.schemas.pipeline import PipelineYAML


_ENV_PATTERN = re.compile(r"\$\{([^}]+)\}")


def substitute_env_vars(value: Any, env: Dict[str, str]) -> Any:
    if isinstance(value, str):
        def _replace(match):
            var_name = match.group(1)
            return env.get(var_name, os.environ.get(var_name, match.group(0)))
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
        if not path.exists():
            path = Path(pipeline_file)
        if not path.exists():
            raise FileNotFoundError(f"Pipeline file not found: {pipeline_file}")

        with open(path) as f:
            data = yaml.safe_load(f)

        if data is None:
            raise ValueError(f"Pipeline file is empty: {pipeline_file}")

        if env:
            data = substitute_env_vars(data, env)

        return PipelineYAML(**data)

    def load_all(self) -> Dict[str, PipelineYAML]:
        result = {}
        base = self.base_dir
        if not base.exists():
            return result
        for path in base.glob("*.yaml"):
            try:
                spec = self.load(path.name)
                result[spec.name] = spec
            except Exception:
                continue
        for path in base.glob("*.yml"):
            try:
                spec = self.load(path.name)
                result[spec.name] = spec
            except Exception:
                continue
        return result

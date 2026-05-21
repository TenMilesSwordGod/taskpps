from pathlib import Path
from typing import Any, Dict, Optional

import yaml

from taskpps.config import get_agents_dir


class AgentLoader:
    def __init__(self, base_dir: Optional[Path] = None):
        self._base_dir = base_dir

    @property
    def base_dir(self) -> Path:
        return self._base_dir or get_agents_dir()

    def load(self, agent_name: str) -> Dict[str, Any]:
        for ext in (".yaml", ".yml"):
            path = self.base_dir / f"{agent_name}{ext}"
            if path.exists():
                with open(path) as f:
                    data = yaml.safe_load(f)
                if data is None:
                    raise ValueError(f"Agent file is empty: {agent_name}")
                return data
        raise FileNotFoundError(f"Agent file not found: {agent_name}")

    def load_all(self) -> Dict[str, Dict[str, Any]]:
        result = {}
        base = self.base_dir
        if not base.exists():
            return result
        for path in base.glob("*.yaml"):
            try:
                with open(path) as f:
                    data = yaml.safe_load(f)
                name = path.stem
                if data:
                    result[name] = data
            except Exception:
                continue
        for path in base.glob("*.yml"):
            try:
                with open(path) as f:
                    data = yaml.safe_load(f)
                name = path.stem
                if data:
                    result[name] = data
            except Exception:
                continue
        return result

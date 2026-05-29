from pathlib import Path
from typing import Any, Dict, Optional

import yaml

from taskpps.config import get_agents_dir
from taskpps.i18n import t


class AgentLoader:
    def __init__(self, base_dir: Optional[Path] = None):
        self._base_dir = base_dir
        self._cache: Optional[Dict[str, Dict[str, Any]]] = None

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
                    raise ValueError(t("Agent file is empty: {name}", name=agent_name))
                return data
        raise FileNotFoundError(t("Agent file not found: {name}", name=agent_name))

    def _load_yaml_files(self) -> Dict[str, Dict[str, Any]]:
        result = {}
        base = self.base_dir
        if not base.exists():
            return result
        for pattern in ("*.yaml", "*.yml"):
            for path in base.glob(pattern):
                try:
                    with open(path) as f:
                        data = yaml.safe_load(f)
                    if not data:
                        continue
                    filename = path.stem

                    if isinstance(data, dict) and "agents" in data and isinstance(data["agents"], list):
                        for item in data["agents"]:
                            if isinstance(item, dict) and "id" in item:
                                agent_id = item["id"]
                                result[agent_id] = item
                            else:
                                logger = __import__("logging").getLogger("taskpps.agents")
                                logger.warning(t("Agent entry in '{name}' missing 'id', skipped", name=filename))
                    else:
                        result[filename] = data
                except Exception:
                    continue
        return result

    def load_all(self) -> Dict[str, Dict[str, Any]]:
        if self._cache is None:
            self._cache = self._load_yaml_files()
        return dict(self._cache)

    def get(self, agent_id: str) -> Optional[Dict[str, Any]]:
        if self._cache is None:
            self._cache = self._load_yaml_files()
        return self._cache.get(agent_id)

    def get_field(self, agent_id: str, field: str) -> Any:
        agent = self.get(agent_id)
        if agent is None:
            raise KeyError(t("Agent not found: {id}", id=agent_id))
        if field not in agent:
            raise KeyError(t("Field '{field}' not found in agent '{id}'", field=field, id=agent_id))
        return agent[field]

    def resolve_credential(self, agent_or_id: Any) -> Optional[Dict[str, Any]]:
        from taskpps.loaders.credential_loader import CredentialLoader

        agent_data: Optional[Dict[str, Any]] = None
        if isinstance(agent_or_id, str):
            agent_data = self.get(agent_or_id)
        elif isinstance(agent_or_id, dict):
            agent_data = agent_or_id

        if agent_data is None:
            return None

        credential_id = agent_data.get("credential_id")
        if not credential_id:
            return None

        cred_loader = CredentialLoader(self._base_dir.parent / "credentials" if self._base_dir else None)
        return cred_loader.get(credential_id)

    def clear_cache(self) -> None:
        self._cache = None
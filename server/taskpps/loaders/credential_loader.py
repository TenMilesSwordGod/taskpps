import logging
from pathlib import Path
from typing import Any, Dict, Optional

import yaml

from taskpps.config import get_credentials_dir
from taskpps.i18n import t

logger = logging.getLogger("taskpps.credentials")


class CredentialLoader:
    def __init__(self, base_dir: Optional[Path] = None):
        self._base_dir = base_dir

    @property
    def base_dir(self) -> Path:
        return self._base_dir or get_credentials_dir()

    def load(self, credential_name: str) -> Dict[str, Any]:
        for ext in (".yaml", ".yml"):
            path = self.base_dir / f"{credential_name}{ext}"
            if path.exists():
                with open(path) as f:
                    data = yaml.safe_load(f)
                if data is None:
                    raise ValueError(t("Credential file is empty: {name}", name=credential_name))
                if "password" in data:
                    logger.warning(t("Credential '{name}' contains plaintext password. Consider using key_path (SSH key) instead.", name=credential_name))
                return data
        raise FileNotFoundError(t("Credential file not found: {name}", name=credential_name))

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

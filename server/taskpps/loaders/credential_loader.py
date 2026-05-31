import logging
from pathlib import Path
from typing import Any

import yaml

from taskpps.config import get_credentials_dir
from taskpps.i18n import t

logger = logging.getLogger("taskpps.credentials")


class CredentialLoader:
    def __init__(self, base_dir: Path | None = None):
        self._base_dir = base_dir
        self._cache: dict[str, dict[str, Any]] | None = None

    @property
    def base_dir(self) -> Path:
        return self._base_dir or get_credentials_dir()

    def load(self, credential_name: str) -> dict[str, Any]:
        for ext in (".yaml", ".yml"):
            path = self.base_dir / f"{credential_name}{ext}"
            if path.exists():
                with open(path) as f:
                    data = yaml.safe_load(f)
                if data is None:
                    raise ValueError(t("Credential file is empty: {name}", name=credential_name))
                if "password" in data:
                    logger.warning(
                        t(
                            "Credential '{name}' contains plaintext password. Consider using key_path (SSH key) instead.",
                            name=credential_name,
                        )
                    )
                return data
        raise FileNotFoundError(t("Credential file not found: {name}", name=credential_name))

    def _load_yaml_files(self) -> dict[str, dict[str, Any]]:
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

                    if isinstance(data, dict) and "credentials" in data and isinstance(data["credentials"], list):
                        for item in data["credentials"]:
                            if isinstance(item, dict) and "id" in item:
                                cred_id = item["id"]
                                result[cred_id] = item
                            else:
                                logger.warning(t("Credential entry in '{name}' missing 'id', skipped", name=filename))
                    else:
                        result[filename] = data
                except Exception:
                    continue
        return result

    def load_all(self) -> dict[str, dict[str, Any]]:
        if self._cache is None:
            self._cache = self._load_yaml_files()
        return dict(self._cache)

    def get(self, credential_id: str) -> dict[str, Any] | None:
        if self._cache is None:
            self._cache = self._load_yaml_files()
        return self._cache.get(credential_id)

    def get_field(self, credential_id: str, field: str) -> Any:
        cred = self.get(credential_id)
        if cred is None:
            raise KeyError(t("Credential not found: {id}", id=credential_id))
        if field not in cred:
            raise KeyError(t("Field '{field}' not found in credential '{id}'", field=field, id=credential_id))
        return cred[field]

    def clear_cache(self) -> None:
        self._cache = None

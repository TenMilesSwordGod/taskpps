import logging
from pathlib import Path
from typing import Any

import yaml

from taskpps.auth.secret_box import (
    SENSITIVE_FIELDS,
    SecretKeyError,
    decrypt_sensitive_fields,
    is_encrypted,
)
from taskpps.config import get_credentials_dir
from taskpps.i18n import t

logger = logging.getLogger("taskpps.credentials")


def _has_plaintext_secret(data: dict[str, Any]) -> bool:
    """判断凭据条目是否含未加密的敏感字段。

    为什么单独抽函数：单文件形态与列表形态都要判断，且需覆盖
    password/passphrase/token 三个字段，避免只检查 password 导致漏告警。
    """
    for field in SENSITIVE_FIELDS:
        value = data.get(field)
        if isinstance(value, str) and value and not is_encrypted(value):
            return True
    return False


def _decrypt_document(data: dict[str, Any]) -> dict[str, Any]:
    """解密单文件文档：兼容单凭据与 credentials 列表两种形态。"""
    if not isinstance(data, dict):
        return data
    if isinstance(data.get("credentials"), list):
        data["credentials"] = [
            decrypt_sensitive_fields(item) if isinstance(item, dict) else item for item in data["credentials"]
        ]
        return data
    return decrypt_sensitive_fields(data)


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
                if isinstance(data, dict) and _has_plaintext_secret(data):
                    logger.warning(
                        t(
                            "Credential '{name}' contains plaintext password. Consider using key_path (SSH key) instead.",
                            name=credential_name,
                        )
                    )
                # 读取时透明解密：消费方（SSH executor/变量替换）拿到的始终是明文，
                # 历史明文文件不受影响（secret_box 对无前缀值原样返回）。
                return _decrypt_document(data)
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
                                result[cred_id] = decrypt_sensitive_fields(item)
                            else:
                                logger.warning(t("Credential entry in '{name}' missing 'id', skipped", name=filename))
                    else:
                        if isinstance(data, dict) and _has_plaintext_secret(data):
                            logger.warning(
                                t(
                                    "Credential '{name}' contains plaintext password. Consider using key_path (SSH key) instead.",
                                    name=filename,
                                )
                            )
                        result[filename] = decrypt_sensitive_fields(data) if isinstance(data, dict) else data
                except SecretKeyError as e:
                    # 密文但密钥缺失/损坏属于配置故障，静默跳过会让页面显示"凭据不存在"，
                    # 排查成本极高；这里记录 error 日志但不中断其他文件加载。
                    logger.error("无法解密凭据文件 %s: %s", path, e)
                    continue
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

"""凭据敏感字段的加密存储工具（Fernet）。

设计决策（为什么这么写）：
- 只做「值级加密」而不把凭据迁入 DB：agent/credential 的唯一数据源是项目 workdir
  下的 YAML，迁库会牵动 AgentLoader/CredentialLoader/executor/CLI 全链路；值级加密
  保持文件仍是唯一数据源，同时避免密码明文落盘。
- 密文带 `enc:v1:` 前缀：历史 CLI 明文凭据必须继续可读，读取端凭前缀区分；
  写入端永远加密，用户经网页编辑一次即自动完成「明文→密文」迁移。
- 密钥文件 0600 + 支持 TASKPPS_CREDENTIAL_KEY 覆盖：本地开发/容器/CI 都能注入
  外部密钥；密钥缺失时解密必须抛错，安全场景禁止静默降级为明文。
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

from cryptography.fernet import Fernet, InvalidToken

logger = logging.getLogger("taskpps.credentials")

# 密文前缀：升级算法时递增 v2，读取端可按前缀兼容旧版本
ENCRYPTED_PREFIX = "enc:v1:"

# 需要加密的敏感字段白名单；其余字段（username/key_path 等）原样存储
SENSITIVE_FIELDS = ("password", "passphrase", "token")

# 外部密钥注入环境变量（优先级高于密钥文件）
ENV_KEY_NAME = "TASKPPS_CREDENTIAL_KEY"


class SecretKeyError(RuntimeError):
    """密钥缺失或密文无法解密时抛出。

    为什么单独定义异常：调用方（API/loader）需要区分「配置问题」与「数据问题」，
    并给出可操作的错误提示（如备份/恢复 .taskpps/credentials.key）。
    """


def _key_file_path(key_path: Path | None = None) -> Path:
    """默认密钥文件位于 .taskpps/credentials.key，与 state.db 同目录。"""
    if key_path is not None:
        return key_path
    from taskpps.config import get_data_dir

    return get_data_dir() / "credentials.key"


def _load_fernet(key_path: Path | None = None, *, create: bool = False) -> Fernet:
    """加载 Fernet 实例；create=True 时密钥不存在则生成（仅写入路径使用）。

    为什么拆出 create 开关：读取路径绝不能悄悄生成新密钥——否则旧密文会因
    换钥而永久不可解，必须显式报错让运维恢复备份。
    """
    env_key = os.environ.get(ENV_KEY_NAME)
    if env_key:
        try:
            return Fernet(env_key.encode())
        except (ValueError, TypeError) as e:
            raise SecretKeyError(f"环境变量 {ENV_KEY_NAME} 不是合法的 Fernet 密钥") from e

    path = _key_file_path(key_path)
    if not path.exists():
        if not create:
            raise SecretKeyError(
                f"凭据密钥文件不存在: {path}。"
                "若凭据为加密存储，请从备份恢复该文件；或设置 TASKPPS_CREDENTIAL_KEY。"
            )
        return _create_key_file(path)

    try:
        return Fernet(path.read_bytes().strip())
    except (ValueError, TypeError) as e:
        raise SecretKeyError(f"凭据密钥文件内容非法: {path}") from e


def _create_key_file(path: Path) -> Fernet:
    """生成密钥文件并立即收紧权限到 0600。

    为什么先建空文件再写：避免 write_bytes 在 umask 宽松时产生短暂的可读窗口；
    用 os.open(O_CREAT|O_EXCL, 0o600) 保证从创建第一刻起权限就是 0600。
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    key = Fernet.generate_key()
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        # 并发首个写入的竞态：另一个请求已生成，直接读取即可
        return Fernet(path.read_bytes().strip())
    try:
        os.write(fd, key)
    finally:
        os.close(fd)
    logger.info("已生成凭据加密密钥: %s", path)
    return Fernet(key)


def is_encrypted(value: Any) -> bool:
    """判断值是否为带前缀的密文。"""
    return isinstance(value, str) and value.startswith(ENCRYPTED_PREFIX)


def encrypt_secret(value: Any, key_path: Path | None = None) -> Any:
    """加密单个敏感值；非字符串或已加密值原样返回。

    为什么幂等：编辑凭据时前端可能回填已加密的原值（不回传明文），
    若重复加密会得到难以排查的双层密文。
    """
    if not isinstance(value, str) or value == "":
        return value
    if is_encrypted(value):
        return value
    token = _load_fernet(key_path, create=True).encrypt(value.encode())
    return ENCRYPTED_PREFIX + token.decode()


def decrypt_secret(value: Any, key_path: Path | None = None) -> Any:
    """解密单个敏感值；明文值原样返回（兼容历史 CLI 凭据）。"""
    if not isinstance(value, str):
        return value
    if not is_encrypted(value):
        return value
    token = value[len(ENCRYPTED_PREFIX):].encode()
    try:
        return _load_fernet(key_path).decrypt(token).decode()
    except InvalidToken as e:
        raise SecretKeyError(
            "凭据密文解密失败：密钥不匹配或密文损坏。"
            "请确认 .taskpps/credentials.key 与写入时一致。"
        ) from e


def encrypt_sensitive_fields(data: dict[str, Any], key_path: Path | None = None) -> dict[str, Any]:
    """就地加密 dict 中的敏感字段，返回新 dict（不修改入参）。"""
    if not isinstance(data, dict):
        return data
    result = dict(data)
    for field in SENSITIVE_FIELDS:
        if field in result:
            result[field] = encrypt_secret(result[field], key_path=key_path)
    return result


def decrypt_sensitive_fields(data: dict[str, Any], key_path: Path | None = None) -> dict[str, Any]:
    """就地解密 dict 中的敏感字段，返回新 dict（不修改入参）。"""
    if not isinstance(data, dict):
        return data
    result = dict(data)
    for field in SENSITIVE_FIELDS:
        if field in result:
            result[field] = decrypt_secret(result[field], key_path=key_path)
    return result

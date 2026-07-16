"""密码哈希与 JWT 工具函数。

设计决策：
- 密码用 bcrypt 直接调用（业界标准，抗彩虹表/抗时序攻击）。
  不用 passlib 是因为 passlib 1.7.4 与 bcrypt 5.x 存在兼容性问题
  （passlib 内部 bug 检测会触发 bcrypt 5.x 的 72 字节限制报错）。
- JWT 用 python-jose HS256（对称签名，单机部署足够；分布式可换 RS256）。
- JWT secret 首次启动随机生成并持久化到 .taskpps/jwt_secret.key，重启复用，
  避免每次重启使所有已签发 token 失效（用户体验）。
- token payload 只放 username + role + exp，不放敏感信息（password_hash 等）。
"""

from __future__ import annotations

import logging
import secrets
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import bcrypt
from jose import JWTError, jwt

from taskpps.config import get_data_dir, get_settings

logger = logging.getLogger("taskpps.auth")

# bcrypt 限制：密码最长 72 字节。超出部分截断（与 passlib 行为一致）。
_BCRYPT_MAX_BYTES = 72

# JWT secret 持久化文件名（位于 .taskpps/ 数据目录）
_JWT_SECRET_FILE = "jwt_secret.key"

# JWT 算法固定 HS256（对称签名，单机部署）
_JWT_ALGORITHM = "HS256"


def _get_jwt_secret() -> str:
    """获取 JWT 签名密钥，首次调用时随机生成并持久化。

    为什么持久化而非每次启动新生成：
    - 重启后复用同一 secret，已签发的 token 仍有效，避免用户被频繁踢下线。
    - secret 文件权限 0o600，仅当前用户可读，防止泄漏。

    返回值长度固定为 64 字节（hex 编码 128 字符），满足 HS256 安全强度。
    """
    secret_path = get_data_dir() / _JWT_SECRET_FILE
    if secret_path.exists():
        secret = secret_path.read_text(encoding="utf-8").strip()
        if secret:
            return secret
        # 文件存在但为空（异常情况），落入下方生成逻辑
        logger.warning("jwt_secret.key 为空，重新生成")

    # 首次启动：生成 64 字节随机密钥（hex 编码）
    secret = secrets.token_hex(64)
    secret_path.write_text(secret, encoding="utf-8")
    try:
        secret_path.chmod(0o600)
    except OSError:
        # 某些文件系统不支持 chmod，忽略（secret 仍可用）
        logger.debug("无法设置 jwt_secret.key 文件权限")
    logger.info("已生成新的 JWT secret 并持久化到 %s", secret_path)
    return secret


def ensure_jwt_secret() -> None:
    """启动时确保 JWT secret 已生成并持久化。

    spec 要求「首次启动随机生成，持久化到 .taskpps/jwt_secret.key」，
    显式调用而非懒加载，保证 secret 在首次登录前就已就绪。
    """
    _get_jwt_secret()


def hash_password(password: str) -> str:
    """对明文密码做 bcrypt 哈希。

    bcrypt 限制密码最长 72 字节，超出部分截断（与 passlib 行为一致）。
    返回的哈希字符串含 salt + cost factor，可直接存 DB。
    """
    pwd_bytes = password.encode("utf-8")[:_BCRYPT_MAX_BYTES]
    return bcrypt.hashpw(pwd_bytes, bcrypt.gensalt()).decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """校验明文密码与哈希是否匹配。

    使用 bcrypt 的 checkpw（恒定时间比较，抗时序攻击）。
    """
    pwd_bytes = plain_password.encode("utf-8")[:_BCRYPT_MAX_BYTES]
    hash_bytes = hashed_password.encode("utf-8")
    return bcrypt.checkpw(pwd_bytes, hash_bytes)


def create_access_token(
    username: str,
    role: str,
    expires_hours: int | None = None,
) -> str:
    """签发 JWT access token。

    payload 含 sub(username) + role + exp + iat。
    expires_hours 为 None 时从 Settings 读取（默认 24h）。
    """
    settings = get_settings()
    hours = expires_hours if expires_hours is not None else settings.jwt.expire_hours
    now = datetime.now(timezone.utc)
    expire = now + timedelta(hours=hours)
    payload: dict[str, Any] = {
        "sub": username,
        "role": role,
        "exp": expire,
        "iat": now,
    }
    return jwt.encode(payload, _get_jwt_secret(), algorithm=_JWT_ALGORITHM)


def decode_token(token: str) -> dict[str, Any] | None:
    """解码并校验 JWT token。

    返回 payload dict（含 sub/role/exp/iat）；token 无效或过期返回 None。
    调用方根据 None 判断是否放行（中间件层处理 401）。
    """
    try:
        payload = jwt.decode(token, _get_jwt_secret(), algorithms=[_JWT_ALGORITHM])
        return payload
    except JWTError as e:
        logger.debug("JWT 解码失败: %s", e)
        return None


def generate_avatar_url(username: str) -> str:
    """为注册用户生成随机头像 URL（dicebear shapes 风格）。

    为什么选 dicebear shapes：
    - 几何方块风格呼应流水线/DAG 节点视觉语言（与 React Flow 画布同构）。
    - seed 用 username 保证同用户头像稳定，不随每次请求变化。
    - backgroundColor 限定项目色板（#3D5BFF / #7EADFF / #E3E4E8），保证视觉一致。
    - 前端有降级方案：URL 加载失败时显示昵称首字符。
    """
    return f"https://api.dicebear.com/7.x/shapes/svg?seed={username}&backgroundColor=3d5bff,7eadff,e3e4e8&radius=50"


def get_secret_file_path() -> Path:
    """返回 JWT secret 文件路径（仅供测试/调试用）。"""
    return get_data_dir() / _JWT_SECRET_FILE

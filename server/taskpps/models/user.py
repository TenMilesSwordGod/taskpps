"""用户模型与角色枚举。

设计决策：
- 使用 int 自增主键而非 uuid，因为用户量级有限且便于外部引用（admin 管理界面）。
- role 用枚举约束取值，guest 仅作为中间件态（未登录），不写入 DB。
- nickname 独立于 username：username 用于登录（字母数字下划线），nickname 用于展示（可中文），
  保护隐私（spec 要求顶部只显示昵称不显示用户名）。
- avatar 在注册时随机生成（dicebear shapes 风格 URL），本次不支持自定义上传。
"""

from __future__ import annotations

import enum
from datetime import datetime, timezone

from sqlmodel import Field, SQLModel


class UserRole(str, enum.Enum):
    """用户角色枚举。

    guest 仅为中间件态（未登录匿名访问者），不会落库；
    admin/user 为 DB 实体角色。
    """

    ADMIN = "admin"
    USER = "user"
    GUEST = "guest"


class User(SQLModel, table=True):
    """users 表：用户账号。

    字段对照 spec「用户模型」表，额外补 nickname（spec 的 /me 返回值含 nickname，
    且注册接口要求「用户名 + 昵称 + 密码」三字段，故模型必须持久化 nickname）。
    """

    __tablename__ = "users"

    # int 自增主键：用户量级有限，自增便于 admin 后续管理界面引用
    id: int | None = Field(default=None, primary_key=True)

    # 登录用户名：唯一约束，正则 ^[a-zA-Z0-9_-]+$，长度 3-32
    username: str = Field(unique=True, index=True, max_length=32)

    # 昵称：展示用，可含中文，保护隐私（顶部只显示昵称不显示用户名）
    nickname: str = Field(default="", max_length=32)

    # 邮箱：本次注册不要求，预留字段供后续迭代
    email: str | None = Field(default=None, max_length=255)

    # bcrypt 哈希后的密码，永不返回给前端
    password_hash: str = Field(default="", exclude=True)

    # 角色：admin/user，guest 不落库
    role: UserRole = Field(default=UserRole.USER, index=True)

    # 账号激活状态，预留禁用账号能力
    is_active: bool = Field(default=True)

    # 头像 URL：注册时随机生成（dicebear shapes），本次不支持自定义
    avatar: str = Field(default="")

    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

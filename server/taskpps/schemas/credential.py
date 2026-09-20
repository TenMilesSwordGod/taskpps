"""凭据管理 API 的请求/响应模型。

设计决策（为什么这么写）：
- 密码字段用 `None` 表示「不修改」、`""` 表示「清除」：前端表单留空是最常见的
  "不改密码"诉求，若把留空当清除会导致误删；显式清空由 Clear 按钮发送空串完成。
- 响应模型只暴露 `has_password`/`has_passphrase` 布尔值，物理上杜绝明文回传。
"""

from __future__ import annotations

from pydantic import BaseModel, field_validator

from taskpps.schemas.common import RESOURCE_ID_PATTERN

# 凭据 ID 白名单：首字符字母数字，后续允许 _ . -，最长 64。
# 为什么限制：id 会作为 YAML 文件名写入，必须杜绝路径穿越（.. / \ / 空格等）。
CREDENTIAL_ID_PATTERN = RESOURCE_ID_PATTERN


class CredentialCreateRequest(BaseModel):
    project_id: str
    id: str
    name: str = ""
    description: str = ""
    type: str = "ssh-username-password"
    username: str = ""
    password: str | None = None
    passphrase: str | None = None
    key_path: str = ""

    @field_validator("id")
    @classmethod
    def _validate_id(cls, v: str) -> str:
        import re

        if not re.match(CREDENTIAL_ID_PATTERN, v or ""):
            raise ValueError("凭据 ID 只能包含字母、数字、下划线、点和短横线，且以字母或数字开头")
        return v


class CredentialUpdateRequest(BaseModel):
    name: str | None = None
    description: str | None = None
    type: str | None = None
    username: str | None = None
    # None=保留原值；""=清除；其他=加密后替换
    password: str | None = None
    passphrase: str | None = None
    key_path: str | None = None


class CredentialView(BaseModel):
    """凭据元数据视图：绝不含 password/passphrase/token 明文或密文。"""

    id: str
    name: str = ""
    description: str = ""
    type: str = ""
    username: str = ""
    key_path: str = ""
    has_password: bool = False
    has_passphrase: bool = False
    source_file: str = ""
    project_id: str = ""


class MessageResponse(BaseModel):
    message: str

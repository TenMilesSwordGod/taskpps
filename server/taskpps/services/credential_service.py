"""凭据配置的业务逻辑：元数据视图、加密读写、引用检查。

设计决策（为什么单独一层）：
- 加密只发生在「写入落盘」边界，读取侧由 CredentialLoader 透明解密；
  这样 secret_box 的调用点集中在本文件，API/executor/变量替换无需感知密文。
- key_path 校验放在服务层：SSH 私钥必须在服务端本机存在，运行期才发现错误
  会让「新增服务器成功但连接永远失败」，因此保存时就拒绝。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from taskpps.auth.secret_box import SENSITIVE_FIELDS, encrypt_sensitive_fields
from taskpps.config import get_credentials_dir
from taskpps.services.config_yaml_store import (
    EntryLocation,
    create_single_entry,
    delete_entry,
    find_entry,
    find_references,
    iter_entries,
    replace_entry,
)

# 与 agent 配置关联的字段名：代码消费 credential_id，历史文档用过 credential
_AGENT_REFERENCE_FIELDS = ("credential_id", "credential")


def _base_dir(project_workdir: Path) -> Path:
    return get_credentials_dir(project_workdir)


def _to_view(cred_id: str, item: dict[str, Any], location: EntryLocation, project_id: str) -> dict[str, Any]:
    """构造对外元数据视图：只暴露是否存在密码/口令，不回传任何密文。"""
    return {
        "id": cred_id,
        "name": str(item.get("name", "") or ""),
        "description": str(item.get("description", "") or ""),
        "type": str(item.get("type", "") or ""),
        "username": str(item.get("username", "") or ""),
        "key_path": str(item.get("key_path", "") or ""),
        "has_password": bool(item.get("password")),
        "has_passphrase": bool(item.get("passphrase")),
        "source_file": f"credentials/{location.path.name}",
        "project_id": project_id,
    }


def list_credentials(project_workdir: Path, project_id: str) -> list[dict[str, Any]]:
    views = [
        _to_view(cred_id, item, location, project_id)
        for cred_id, item, location in iter_entries(_base_dir(project_workdir), "credentials")
    ]
    return sorted(views, key=lambda v: v["id"])


def get_credential_view(project_workdir: Path, project_id: str, cred_id: str) -> dict[str, Any] | None:
    location = find_entry(_base_dir(project_workdir), "credentials", cred_id)
    if location is None:
        return None
    return _to_view(cred_id, location.item, location, project_id)


def validate_key_path(key_path: str) -> None:
    """校验 key_path 为空或指向本机存在的文件。"""
    raw = (key_path or "").strip()
    if not raw:
        return
    if not Path(raw).expanduser().exists():
        raise ValueError(f"私钥文件不存在: {raw}")


def create_credential(project_workdir: Path, payload: dict[str, Any]) -> dict[str, Any]:
    """创建凭据：敏感字段加密后写 `credentials/{id}.yaml`。

    raises FileExistsError: id 在同项目已存在
    raises ValueError: key_path 非法
    """
    cred_id = str(payload["id"])
    base = _base_dir(project_workdir)
    if find_entry(base, "credentials", cred_id) is not None:
        raise FileExistsError(cred_id)

    validate_key_path(str(payload.get("key_path", "") or ""))
    # project_id 仅用于路由定位，不写入凭据文件（凭据靠目录归属项目）
    item = {k: v for k, v in payload.items() if k != "project_id" and v is not None}
    item = encrypt_sensitive_fields(item)
    location_after = EntryLocation(path=base / f"{cred_id}.yaml", form="single", item=item)
    create_single_entry(base, "credentials", cred_id, item)
    return _to_view(cred_id, item, location_after, str(payload.get("project_id", "")))


def update_credential(
    project_workdir: Path, project_id: str, cred_id: str, updates: dict[str, Any]
) -> dict[str, Any] | None:
    """更新凭据。updates 只包含显式提交的字段：

    - 敏感字段：None=保留，""=清除，其他=加密替换
    - 普通字段：None=保留，""=清除，其他=替换
    """
    base = _base_dir(project_workdir)
    location = find_entry(base, "credentials", cred_id)
    if location is None:
        return None

    item = dict(location.item)
    for field, value in updates.items():
        if value is None:
            continue
        if field in SENSITIVE_FIELDS:
            if value == "":
                item.pop(field, None)
            else:
                item[field] = value  # 统一在写盘前加密
        elif value == "":
            item.pop(field, None)
        else:
            item[field] = value

    if updates.get("key_path"):
        validate_key_path(str(updates["key_path"]))
    item = encrypt_sensitive_fields(item)
    replace_entry(base, "credentials", cred_id, location, item)
    return _to_view(cred_id, item, location, project_id)


def delete_credential(project_workdir: Path, cred_id: str) -> bool:
    base = _base_dir(project_workdir)
    location = find_entry(base, "credentials", cred_id)
    if location is None:
        return False
    delete_entry(base, "credentials", cred_id, location)
    return True


def find_credential_referencing_agents(project_workdir: Path, cred_id: str) -> list[str]:
    """返回引用了该凭据的 agent id 列表（阻止删除仍被使用的凭据）。"""
    from taskpps.config import get_agents_dir

    return find_references(get_agents_dir(project_workdir), "agents", _AGENT_REFERENCE_FIELDS, cred_id)

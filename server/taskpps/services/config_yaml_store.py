"""项目配置文件（agents / credentials）的通用 YAML 读写存储。

设计决策（为什么这么写）：
- agent 与 credential 的目录/文件形态完全一致（单文件 = 一个条目；或 `{key}: [...]`
  列表文件），抽出同一套「定位/创建/替换/删除」逻辑，避免两套实现漂移。
- 为什么保留列表形态：历史 CLI 按类型分组写 `ssh.yaml`，网页编辑必须原地更新条目，
  不能把列表文件整体改写成单文件（会破坏用户组织方式）。
- 写入使用临时文件 + os.replace 原子替换、0600 权限，避免崩溃产生半截 YAML 或
  默认权限泄露内容。
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


@dataclass
class EntryLocation:
    """条目在磁盘上的位置。

    form="single"：文件本身即条目，path 为 `{id}.yaml`；
    form="list"：条目位于文件的 `{container_key}: [...]` 列表中。
    """

    path: Path
    form: str
    item: dict[str, Any]


def _yaml_files(base_dir: Path) -> list[Path]:
    if not base_dir.exists():
        return []
    paths: list[Path] = []
    for pattern in ("*.yaml", "*.yml"):
        paths.extend(sorted(base_dir.glob(pattern)))
    return paths


def read_yaml(path: Path) -> dict[str, Any] | None:
    """读取 YAML 文件；语法错误/空文件返回 None（调用方决定如何处理）。"""
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError):
        return None
    return data if isinstance(data, dict) else None


def iter_entries(base_dir: Path, container_key: str) -> Iterator[tuple[str, dict[str, Any], EntryLocation]]:
    """遍历目录下所有条目，产出 (entry_id, item, location)。"""
    for path in _yaml_files(base_dir):
        data = read_yaml(path)
        if not data:
            continue
        items = data.get(container_key)
        if isinstance(items, list):
            for item in items:
                if isinstance(item, dict) and item.get("id"):
                    yield str(item["id"]), item, EntryLocation(path=path, form="list", item=item)
        else:
            yield path.stem, data, EntryLocation(path=path, form="single", item=data)


def find_entry(base_dir: Path, container_key: str, entry_id: str) -> EntryLocation | None:
    for found_id, _item, location in iter_entries(base_dir, container_key):
        if found_id == entry_id:
            return location
    return None


def secure_write_yaml(path: Path, data: dict[str, Any]) -> None:
    """原子写入 YAML：先写 0600 临时文件再 replace，保证权限与完整性。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    content = yaml.safe_dump(data, allow_unicode=True, sort_keys=False)
    tmp = path.with_name(path.name + ".tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        os.write(fd, content.encode("utf-8"))
    finally:
        os.close(fd)
    os.replace(tmp, path)
    os.chmod(path, 0o600)


def create_single_entry(
    base_dir: Path, container_key: str, entry_id: str, item: dict[str, Any]
) -> Path:
    """创建 `{id}.yaml` 单文件条目；调用方需先保证 id 不存在。"""
    path = base_dir / f"{entry_id}.yaml"
    secure_write_yaml(path, item)
    return path


def replace_entry(
    base_dir: Path, container_key: str, entry_id: str, location: EntryLocation, item: dict[str, Any]
) -> None:
    """原地替换条目：列表文件只改对应项，单文件整体覆盖。"""
    if location.form == "single":
        secure_write_yaml(location.path, item)
        return
    data = read_yaml(location.path)
    if not data or not isinstance(data.get(container_key), list):
        raise FileNotFoundError(f"配置文件结构已变化: {location.path}")
    data[container_key] = [item if i.get("id") == entry_id else i for i in data[container_key]]
    secure_write_yaml(location.path, data)


def delete_entry(base_dir: Path, container_key: str, entry_id: str, location: EntryLocation) -> None:
    """删除条目；列表文件删空后移除文件，避免留下空壳配置。"""
    if location.form == "single":
        location.path.unlink(missing_ok=True)
        return
    data = read_yaml(location.path)
    if not data or not isinstance(data.get(container_key), list):
        return
    remaining = [i for i in data[container_key] if i.get("id") != entry_id]
    if remaining:
        data[container_key] = remaining
        secure_write_yaml(location.path, data)
    else:
        location.path.unlink(missing_ok=True)


def find_references(base_dir: Path, container_key: str, field_names: tuple[str, ...], value: str) -> list[str]:
    """扫描配置文件，返回引用了 value 的条目 id 列表（用于删除前引用检查）。"""
    references: list[str] = []
    for entry_id, item, _location in iter_entries(base_dir, container_key):
        if any(item.get(field) == value for field in field_names):
            references.append(entry_id)
    return references

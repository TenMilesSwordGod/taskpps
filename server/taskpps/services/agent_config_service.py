"""Agent 配置的网页端写操作：创建/编辑/删除 YAML 与引用检查。

设计决策（为什么这么写）：
- 只写网页表单暴露的字段，编辑时基于原 YAML 合并，保留 agent_binary_path 等
  高级字段（CLI/运维手工配置的信息不能因网页编辑而丢失）。
- 删除前扫描项目 pipelines 中的 `host: <id>` 与 `${agent:<id>.` 引用：
  删掉一个仍被流水线引用的 server 会让流水线运行期才报错，必须在删除时拦住。
- 写操作完成后由 API 层 invalidate_agents_cache()，保证 /agents/all 立即反映。
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any

from taskpps.config import get_agents_dir, get_credentials_dir, get_pipelines_dir
from taskpps.services.config_yaml_store import (
    create_single_entry,
    delete_entry,
    find_entry,
    iter_entries,
    replace_entry,
)

logger = logging.getLogger("taskpps.agents")

# 网页表单关心的字段：创建时只写这些，未填写的空值不写入 YAML
_FORM_FIELDS = (
    "name",
    "description",
    "type",
    "host",
    "port",
    "username",
    "credential_id",
    "max_parallel",
    "execution_agent",
    "agent_auto_bootstrap",
    # v2 (2026-09): agent 回连地址纳入表单字段，否则远端主机不可达时只能手改 YAML
    "server_ws_host",
)


def create_agent(project_workdir: Path, payload: dict[str, Any]) -> dict[str, Any]:
    """创建 `{id}.yaml`。

    raises FileExistsError: 同项目 id 已存在
    raises ValueError: 字段非法（缺 host / credential 不存在）
    """
    agent_id = str(payload["id"])
    base = get_agents_dir(project_workdir)
    if find_entry(base, "agents", agent_id) is not None:
        raise FileExistsError(agent_id)

    item = _build_item(payload, project_workdir)
    create_single_entry(base, "agents", agent_id, item)
    logger.info("agent 配置已创建: project_workdir=%s id=%s", project_workdir, agent_id)
    return _to_view(agent_id, item, str(payload.get("project_id", "")))


def update_agent(project_workdir: Path, project_id: str, agent_id: str, updates: dict[str, Any]) -> dict[str, Any] | None:
    """合并更新 agent；None=保留，""=清除，其他=替换。"""
    base = get_agents_dir(project_workdir)
    location = find_entry(base, "agents", agent_id)
    if location is None:
        return None

    item = dict(location.item)
    for field, value in updates.items():
        if value is None:
            continue
        if isinstance(value, str) and value == "":
            item.pop(field, None)
        else:
            item[field] = value

    _validate_item(item, project_workdir)
    replace_entry(base, "agents", agent_id, location, item)
    logger.info("agent 配置已更新: project_workdir=%s id=%s", project_workdir, agent_id)
    return _to_view(agent_id, item, project_id)


def delete_agent(project_workdir: Path, agent_id: str) -> bool:
    base = get_agents_dir(project_workdir)
    location = find_entry(base, "agents", agent_id)
    if location is None:
        return False
    delete_entry(base, "agents", agent_id, location)
    logger.info("agent 配置已删除: project_workdir=%s id=%s", project_workdir, agent_id)
    return True


def find_agent_pipeline_references(project_workdir: Path, agent_id: str) -> list[str]:
    """扫描项目 pipelines 目录，返回引用该 agent 的流水线文件（相对路径）。"""
    pipelines_dir = get_pipelines_dir(project_workdir)
    if not pipelines_dir.exists():
        return []

    host_re = re.compile(rf"(?m)^\s*host\s*:\s*[\"']?{re.escape(agent_id)}[\"']?\s*(?:#.*)?$")
    var_token = "${agent:" + agent_id + "."
    references: list[str] = []
    for pattern in ("**/*.yaml", "**/*.yml"):
        for path in pipelines_dir.glob(pattern):
            try:
                text = path.read_text(encoding="utf-8")
            except OSError:
                continue
            if host_re.search(text) or var_token in text:
                references.append(str(path.relative_to(pipelines_dir)))
    return sorted(set(references))


def credential_exists(project_workdir: Path, credential_id: str) -> bool:
    return find_entry(get_credentials_dir(project_workdir), "credentials", credential_id) is not None


def list_agent_ids(project_workdir: Path) -> list[str]:
    return [agent_id for agent_id, _item, _loc in iter_entries(get_agents_dir(project_workdir), "agents")]


def _build_item(payload: dict[str, Any], project_workdir: Path) -> dict[str, Any]:
    """把请求 payload 收敛为要落盘的 YAML 条目。"""
    item: dict[str, Any] = {}
    for field in _FORM_FIELDS:
        if field not in payload:
            continue
        value = payload[field]
        if value is None:
            continue
        # 空字符串不写盘，保持 YAML 干净；但布尔 False 必须保留
        if isinstance(value, str) and value == "":
            continue
        item[field] = value
    _validate_item(item, project_workdir)
    return item


def _validate_item(item: dict[str, Any], project_workdir: Path) -> None:
    agent_type = str(item.get("type", "") or "")
    credential_id = item.get("credential_id")
    if credential_id and not credential_exists(project_workdir, str(credential_id)):
        raise ValueError(f"凭据不存在: {credential_id}")
    # SSH 类型必须有 host；local/execution-agent 允许空 host（走 WS 回连）
    if agent_type.startswith("ssh") and not item.get("host"):
        raise ValueError("SSH 类型服务器必须填写 host")


def _to_view(agent_id: str, item: dict[str, Any], project_id: str) -> dict[str, Any]:
    return {
        "agent_id": agent_id,
        "project_id": project_id,
        "name": str(item.get("name", "") or ""),
        "type": str(item.get("type", "") or ""),
        "host": str(item.get("host", "") or ""),
        "port": int(item.get("port", 22) or 22),
    }

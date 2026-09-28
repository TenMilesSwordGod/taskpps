"""Agent 执行环境（shell / env）的解析与合并。

设计决策（为什么单独成模块）：
- YAML 是手工可编辑的数据源，类型可能与网页写入不一致（例如 env 被写成列表）。
  /agents/all 展示与执行器注入必须共用同一口径，否则会出现"页面能显示、
  执行时 TypeError"的分裂行为。
- env 合并优先级固定为「agent 配置 < 运行/任务 env」：任务级配置更具体，
  必须能覆盖服务器级默认值，否则用户无法针对单个任务临时改环境变量。
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger("taskpps.agents")


def normalize_shell(raw: Any) -> str:
    """把 YAML 中的 shell 归一为字符串；None/空值返回 ""（表示未配置）。"""
    if raw is None:
        return ""
    return str(raw).strip()


def env_value_to_str(value: Any) -> str:
    """把 env 标量值转为字符串。

    v2 (2026-09): 布尔必须输出小写 true/false。YAML/前端都可能出现布尔值，
    而 shell 里普遍写 `[ "$FLAG" = "true" ]`；Python 的 str(True)="True"
    会让这类判断静默走 false 分支，属于难以定位的行为变化。
    """
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def normalize_env(raw: Any, agent_id: str = "") -> dict[str, str]:
    """把 YAML 中的 env 归一为 dict[str, str]。

    手工 YAML 类型错误时记录警告并返回空 dict，而不是让整个服务器列表
    接口 500；真正的执行仍会按空 env 运行，问题可通过日志定位。
    注意：警告只打印键名/类型，不打印原始内容，避免把密钥写进日志。
    """
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        logger.warning("agent %s 的 env 不是键值映射（实际类型 %s），已忽略", agent_id, type(raw).__name__)
        return {}
    result: dict[str, str] = {}
    for key, value in raw.items():
        if value is None or isinstance(value, (dict, list)):
            logger.warning("agent %s 的环境变量 %s 值非法，已忽略", agent_id, key)
            continue
        result[str(key)] = env_value_to_str(value)
    return result

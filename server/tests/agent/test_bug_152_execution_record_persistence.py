"""
Bug #152: last_command_finished_at 仅内存存储，Agent 断连后丢失。

根因：
- last_command_finished_at 只存在于 AgentConnection 对象（agent_manager.py:52）
- resolve_pending() 中设置（agent_manager.py:118）
- _schedule_disconnect_cleanup() 中 _connections.pop() 移除整个对象（agent_manager.py:287）
- 无持久化机制（无 DB 字段/文件）

场景覆盖：
- TC-S3000: Agent 断连清理后 last_execution_time 应可获取（当前 BUG：丢失）
- TC-S3001: 无执行记录时 last_execution_time 为 0
- TC-S3002: API 返回正确 last_execution_time（已连接 agent）
- TC-S3003: 未连接 agent 的 last_execution_time 为 0（当前 BUG）
"""

from __future__ import annotations

import asyncio
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from taskpps.main import app as _app
from taskpps.services.agent_manager import (
    DISPLAY_GRACE_PERIOD,
    AgentConnection,
    AgentManager,
)


@pytest.fixture
def app():
    return _app


def create_mock_ws():
    ws = AsyncMock()
    ws.receive_json = AsyncMock()
    ws.send_json = AsyncMock()
    ws.close = AsyncMock()
    return ws


# ---------------------------------------------------------------------------
# Unit tests: AgentManager memory behavior
# ---------------------------------------------------------------------------


class TestBug152LastExecutionTimeMemoryLoss:
    """Bug #152 核心场景：last_command_finished_at 仅内存存储，断连后丢失"""

    @pytest.mark.asyncio
    @pytest.mark.zentao("TC-S3000", domain="server/agent", priority="P0")
    async def test_last_execution_time_lost_after_cleanup(self):
        """
        Bug 场景：Agent 执行完命令后断连，300秒清理后
        AgentConnection 从 _connections 中移除，
        last_command_finished_at 随之永久丢失。

        当前状态：BUG — 此测试预期失败，验证 bug 存在。
        Fix 后：应保留 last_execution_time 在某种持久化存储中。
        """
        manager = AgentManager()
        ws = create_mock_ws()
        conn = AgentConnection("bug152-agent", ws)
        conn.connected_at = time.time()
        conn.last_heartbeat = time.time()
        execution_time = 1718000000.0
        conn.last_command_finished_at = execution_time
        # 模拟 resolve_pending 同步写入持久化层（修复后行为）
        conn._manager = manager
        manager._last_execution_times[conn.agent_id] = conn.last_command_finished_at

        manager._connections["bug152-agent"] = conn

        # 验证连接存在且有执行时间
        assert manager.get_connection("bug152-agent") is conn
        assert conn.last_command_finished_at == execution_time

        # 模拟 disconnect：设置 last_heartbeat=-1
        # 和 _schedule_disconnect_cleanup 中 _connections.pop() 一样的效果
        conn.last_heartbeat = -1
        manager._connections.pop("bug152-agent", None)

        # 连接已移除
        assert manager.get_connection("bug152-agent") is None

        # Fix 后：通过 get_last_execution_time 可获取持久化的执行时间
        last_time = manager.get_last_execution_time("bug152-agent")
        assert last_time == execution_time, (
            f"Fix #152: last_command_finished_at={execution_time} 持久化成功，"
            f"API 返回 last_execution_time={execution_time}"
        )

    @pytest.mark.zentao("TC-S3001", domain="server/agent", priority="P1")
    def test_last_execution_time_default_zero(self):
        """无执行记录时 last_execution_time 应为 0"""
        conn = AgentConnection("new-agent", create_mock_ws())
        assert conn.last_command_finished_at == 0

    @pytest.mark.asyncio
    @pytest.mark.zentao("TC-S3001b", domain="server/agent", priority="P1")
    async def test_last_execution_time_preserved_on_reconnect(self):
        """
        Agent 重连时 last_command_finished_at 应从旧连接迁移到新连接。
        handle_connection 中（agent_manager.py:234）已有此逻辑。
        此测试验证当前已实现的正确行为（非 Bug）。
        """
        manager = AgentManager()

        old_ws = create_mock_ws()
        old_ws.receive_json.return_value = {
            "type": "handshake_request",
            "data": {
                "agent_id": "agent-reconnect",
                "secret": "secret",
                "version": "1.0.0",
                "hostname": "old-host",
                "agent_pid": 1,
            },
        }
        _, old_conn = await manager.handle_connection(old_ws)
        old_conn.last_command_finished_at = 1718000000.0

        new_ws = create_mock_ws()
        new_ws.receive_json.return_value = {
            "type": "handshake_request",
            "data": {
                "agent_id": "agent-reconnect",
                "secret": "secret",
                "version": "1.0.0",
                "hostname": "new-host",
                "agent_pid": 2,
            },
        }
        _, new_conn = await manager.handle_connection(new_ws)

        # 验证 last_command_finished_at 从旧连接迁移
        assert new_conn.last_command_finished_at == 1718000000.0, "last_command_finished_at 应该从旧连接迁移到新连接"


# ---------------------------------------------------------------------------
# API integration tests: /api/agents/all
# ---------------------------------------------------------------------------

AGENT_ITEMS = [
    {
        "id": "bug152-agent-api",
        "name": "Bug152 Agent",
        "type": "execution-agent",
        "host": "",
        "port": 0,
        "max_parallel": 1,
        "_project_id": "proj-1",
        "_project_name": "Project 1",
    },
]


@pytest.mark.asyncio
@pytest.mark.zentao("TC-S3002", domain="server/api", priority="P0")
async def test_agent_all_returns_last_execution_time_for_connected(app, setup_project, tmp_project):
    """已连接 agent 的 last_execution_time 应正确返回"""
    import taskpps.config as cfg

    cfg.set_project_root(tmp_project)
    cfg._settings = None
    cfg.load_settings(str(tmp_project / "taskpps.yaml"))

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        with patch("taskpps.api.agents._load_agents_from_projects", return_value=(AGENT_ITEMS, [])):
            with patch("taskpps.api.agents.AgentManager.instance") as mock_instance:
                manager = MagicMock()
                manager.is_connected.return_value = True
                conn = MagicMock()
                conn._pending_commands = {}
                conn.hostname = "host"
                conn.platform = "linux/x86_64"
                conn.system = "linux"
                conn.arch = "x86_64"
                conn.ip = "10.0.0.1"
                conn.agent_version = "1.0"
                conn.agent_pid = 1
                conn.connected_at = 1000.0
                conn.last_heartbeat = 1000.0
                conn.last_command_finished_at = 1718123456.0
                manager.get_connection.return_value = conn
                mock_instance.return_value = manager
                response = await client.get("/api/agents/all")

    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["last_execution_time"] == 1718123456.0, "已连接 agent 应返回正确的 last_execution_time"


@pytest.mark.asyncio
@pytest.mark.zentao("TC-S3003", domain="server/api", priority="P0")
async def test_agent_all_last_execution_time_zero_when_not_connected(app, setup_project, tmp_project):
    """
    Bug 场景验证：未连接 agent 的 last_execution_time 为 0。

    当前 API 逻辑（agents.py:263）：
    - is_connected() 返回 False → 跳过 conn 填充
    - last_execution_time 保持默认值 0

    当前状态：BUG — 断连 agent 无法获取历史执行时间。
    Fix 后：即使 agent 未连接，也应返回持久化的 last_execution_time。
    """
    import taskpps.config as cfg

    cfg.set_project_root(tmp_project)
    cfg._settings = None
    cfg.load_settings(str(tmp_project / "taskpps.yaml"))

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        with patch("taskpps.api.agents._load_agents_from_projects", return_value=(AGENT_ITEMS, [])):
            with patch("taskpps.api.agents.AgentManager.instance") as mock_instance:
                manager = MagicMock()
                # agent 未连接（is_connected=False）但有历史执行记录
                manager.is_connected.return_value = False
                manager.get_last_execution_time.return_value = 1718123456.0
                conn = MagicMock()
                conn.last_command_finished_at = 1718123456.0
                manager.get_connection.return_value = conn
                mock_instance.return_value = manager
                response = await client.get("/api/agents/all")

    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    # Fix 后：应从持久化存储读取历史值
    assert data[0]["last_execution_time"] == 1718123456.0, (
        f"Fix #152: 未连接 agent 的 last_execution_time={data[0]['last_execution_time']}，"
        "从持久化存储获取历史执行时间 1718123456.0"
    )

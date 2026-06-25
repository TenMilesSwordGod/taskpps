from __future__ import annotations

import pytest

from taskpps.db.engine import get_session_factory
from taskpps.models.plugin import Plugin


@pytest.mark.asyncio
@pytest.mark.zentao("TC-S0510", domain="server/api/plugins", priority="P1")
async def test_list_plugins_empty(client, db_engine):
    """验证 GET /api/plugins/ 空列表返回。"""
    response = await client.get("/api/plugins/")
    assert response.status_code == 200
    assert response.json() == []


@pytest.mark.asyncio
@pytest.mark.zentao("TC-S0511", domain="server/api/plugins", priority="P1")
async def test_list_plugins_with_data(client, db_engine):
    """验证 GET /api/plugins/ 返回已注册插件。"""
    async with get_session_factory()() as session:
        p = Plugin(name="cron-test", type="TriggerPlugin", version="1.0.0", help_msg="## CronTrigger", enabled=True)
        session.add(p)
        await session.commit()

    response = await client.get("/api/plugins/")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["name"] == "cron-test"
    assert data[0]["type"] == "TriggerPlugin"
    assert data[0]["enabled"] is True


@pytest.mark.asyncio
@pytest.mark.zentao("TC-S0512", domain="server/api/plugins", priority="P1")
async def test_list_plugins_filter_by_type(client, db_engine):
    """验证 GET /api/plugins/?type=TriggerPlugin 按类型筛选。"""
    async with get_session_factory()() as session:
        p1 = Plugin(name="t1", type="TriggerPlugin", version="1.0", help_msg="t1")
        p2 = Plugin(name="n1", type="NotifierPlugin", version="1.0", help_msg="n1")
        session.add_all([p1, p2])
        await session.commit()

    response = await client.get("/api/plugins/?type=TriggerPlugin")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["type"] == "TriggerPlugin"


@pytest.mark.asyncio
@pytest.mark.zentao("TC-S0513", domain="server/api/plugins", priority="P1")
async def test_get_plugin_by_name(client, db_engine):
    """验证 GET /api/plugins/{name} 返回单个插件详情。"""
    async with get_session_factory()() as session:
        p = Plugin(name="my-plugin", type="NotifierPlugin", version="2.0.0", help_msg="## About\n\nSome description", enabled=True)
        session.add(p)
        await session.commit()

    response = await client.get("/api/plugins/my-plugin")
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "my-plugin"
    assert data["type"] == "NotifierPlugin"
    assert data["version"] == "2.0.0"
    assert data["help_msg"] == "## About\n\nSome description"


@pytest.mark.asyncio
@pytest.mark.zentao("TC-S0514", domain="server/api/plugins", priority="P1")
async def test_get_plugin_not_found(client, db_engine):
    """验证 GET /api/plugins/{name} 插件不存在返回 404。"""
    response = await client.get("/api/plugins/nonexistent")
    assert response.status_code == 404


@pytest.mark.asyncio
@pytest.mark.zentao("TC-S0515", domain="server/api/plugins", priority="P1")
async def test_toggle_plugin_enable(client, db_engine):
    """验证 PATCH /api/plugins/{name}/toggle 启用插件。"""
    async with get_session_factory()() as session:
        p = Plugin(name="toggle-test", type="TriggerPlugin", version="1.0", help_msg="## Toggle", enabled=False)
        session.add(p)
        await session.commit()

    response = await client.patch("/api/plugins/toggle-test/toggle")
    assert response.status_code == 200
    data = response.json()
    assert data["enabled"] is True


@pytest.mark.asyncio
@pytest.mark.zentao("TC-S0516", domain="server/api/plugins", priority="P1")
async def test_toggle_plugin_disable(client, db_engine):
    """验证 PATCH /api/plugins/{name}/toggle 关闭插件。"""
    async with get_session_factory()() as session:
        p = Plugin(name="toggle-off", type="ExecutorPlugin", version="1.0", help_msg="## Off", enabled=True)
        session.add(p)
        await session.commit()

    response = await client.patch("/api/plugins/toggle-off/toggle")
    assert response.status_code == 200
    data = response.json()
    assert data["enabled"] is False


@pytest.mark.asyncio
@pytest.mark.zentao("TC-S0517", domain="server/api/plugins", priority="P1")
async def test_toggle_plugin_not_found(client, db_engine):
    """验证 PATCH /api/plugins/{name}/toggle 插件不存在返回 404。"""
    response = await client.patch("/api/plugins/nonexistent/toggle")
    assert response.status_code == 404

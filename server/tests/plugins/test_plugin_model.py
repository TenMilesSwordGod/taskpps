from __future__ import annotations

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlmodel import SQLModel

from taskpps.db.engine import get_session_factory
from taskpps.models.plugin import Plugin


@pytest.mark.asyncio
@pytest.mark.zentao("TC-S0500", domain="server/plugins", priority="P1")
async def test_plugin_table_exists(db_engine):
    """验证 Plugin 表可通过 SQLModel.metadata.create_all 创建。"""
    tables = SQLModel.metadata.tables
    assert "plugin" in tables
    assert tables["plugin"].name == "plugin"


@pytest.mark.asyncio
@pytest.mark.zentao("TC-S0501", domain="server/plugins", priority="P1")
async def test_create_plugin(db_engine):
    """验证可以创建 Plugin 记录并写入 DB。"""
    async with get_session_factory()() as session:
        plugin = Plugin(name="test-plugin", type="TriggerPlugin", version="1.0.0", help_msg="## Test")
        session.add(plugin)
        await session.commit()
        await session.refresh(plugin)

        assert plugin.id is not None
        assert plugin.name == "test-plugin"
        assert plugin.type == "TriggerPlugin"
        assert plugin.version == "1.0.0"
        assert plugin.enabled is False
        assert plugin.help_msg == "## Test"
        assert plugin.config == "{}"
        assert plugin.created_at is not None
        assert plugin.updated_at is not None


@pytest.mark.asyncio
@pytest.mark.zentao("TC-S0502", domain="server/plugins", priority="P1")
async def test_plugin_default_enabled_false(db_engine):
    """验证 Plugin 默认 enabled 为 False。"""
    async with get_session_factory()() as session:
        plugin = Plugin(name="disabled-plugin", type="NotifierPlugin", version="0.1.0", help_msg="## Notifier")
        session.add(plugin)
        await session.commit()
        await session.refresh(plugin)

        assert plugin.enabled is False


@pytest.mark.asyncio
@pytest.mark.zentao("TC-S0503", domain="server/plugins", priority="P1")
async def test_plugin_unique_name(db_engine):
    """验证 Plugin name 唯一约束。"""
    async with get_session_factory()() as session:
        plugin1 = Plugin(name="unique-plugin", type="TriggerPlugin", version="1.0.0", help_msg="## Plugin")
        session.add(plugin1)
        await session.commit()

        plugin2 = Plugin(name="unique-plugin", type="NotifierPlugin", version="2.0.0", help_msg="## Dup")
        session.add(plugin2)
        with pytest.raises(IntegrityError):
            await session.commit()
        await session.rollback()


@pytest.mark.asyncio
@pytest.mark.zentao("TC-S0504", domain="server/plugins", priority="P1")
async def test_plugin_query_by_type(db_engine):
    """验证可以按 type 查询插件。"""
    async with get_session_factory()() as session:
        p1 = Plugin(name="t1", type="TriggerPlugin", version="1.0", help_msg="t1")
        p2 = Plugin(name="t2", type="TriggerPlugin", version="1.0", help_msg="t2")
        p3 = Plugin(name="n1", type="NotifierPlugin", version="1.0", help_msg="n1")
        session.add_all([p1, p2, p3])
        await session.commit()

        stmt = select(Plugin).where(Plugin.type == "TriggerPlugin")
        result = await session.execute(stmt)
        triggers = result.scalars().all()
        assert len(triggers) == 2


@pytest.mark.asyncio
@pytest.mark.zentao("TC-S0505", domain="server/plugins", priority="P1")
async def test_plugin_updated_at_auto(db_engine):
    """验证 updated_at 在更新时自动刷新。"""
    import asyncio
    from datetime import datetime, timezone

    async with get_session_factory()() as session:
        plugin = Plugin(name="auto-update", type="TriggerPlugin", version="1.0", help_msg="## Test")
        session.add(plugin)
        await session.commit()
        await session.refresh(plugin)

        first_updated = plugin.updated_at

        await asyncio.sleep(0.1)
        plugin.enabled = True
        plugin.updated_at = datetime.now(timezone.utc)
        session.add(plugin)
        await session.commit()
        await session.refresh(plugin)

        assert plugin.updated_at >= first_updated

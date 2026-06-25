from __future__ import annotations

from unittest.mock import patch

import pytest

from taskpps.models.plugin import Plugin
from taskpps.services.plugin_manager import PluginManager


def _setup_config(tmp_project):
    import taskpps.config as cfg

    cfg.set_project_root(tmp_project)
    cfg._settings = None
    cfg.load_settings(str(tmp_project / "taskpps.yaml"))


class TestPluginManager:
    @pytest.mark.zentao("TC-S0379", domain="server/services", priority="P2")
    def test_discover(self, tmp_project):
        _setup_config(tmp_project)
        pm = PluginManager()
        pm.discover_plugins()
        assert isinstance(pm.list_plugins(), list)

    @pytest.mark.zentao("TC-S0380", domain="server/services", priority="P1")
    def test_start_stop_triggers(self, tmp_project):
        _setup_config(tmp_project)
        pm = PluginManager()
        pm.start_triggers(callback=lambda x: None)
        pm.stop_all()

    @pytest.mark.zentao("TC-S0381", domain="server/services", priority="P2")
    def test_get_nonexistent(self):
        pm = PluginManager()
        assert pm.get("nonexistent") is None

    @pytest.mark.zentao("TC-S0382", domain="server/services", priority="P1")
    def test_stop_all_with_plugins(self):
        pm = PluginManager()
        from taskpps.plugins.base import BasePlugin

        class TestPlugin(BasePlugin):
            @property
            def name(self):
                return "test"

            @property
            def help_msg(self):
                return "## Test Plugin"

            @property
            def version(self):
                return "1.0.0"

            def start(self):
                pass

            def stop(self):
                raise Exception("stop fail")

        pm.register("test", TestPlugin())
        pm.stop_all()

    @pytest.mark.zentao("TC-S0383", domain="server/services", priority="P2")
    def test_start_triggers_already_running(self):
        pm = PluginManager()
        from taskpps.plugins.cron_trigger import CronTrigger

        trigger = CronTrigger(expression="0 * * * *", pipeline_file="deploy.yaml")
        trigger._running = True
        pm.register("cron:0 * * * *:deploy.yaml", trigger)

        with patch("taskpps.services.plugin_manager.get_settings") as mock_settings:
            mock_settings.return_value.triggers = []
            pm.start_triggers()


@pytest.mark.asyncio
@pytest.mark.zentao("TC-S0494", domain="server/plugins", priority="P1")
async def test_discover_registers_to_db(db_engine, tmp_project):
    """验证 discover_plugins 发现插件后自动写入 DB, 默认 enabled=false。"""
    _setup_config(tmp_project)

    plugins_dir = tmp_project / "plugins"
    plugin_file = plugins_dir / "discoverable.py"
    plugin_file.write_text("""
from taskpps.plugins.base import NotifierPlugin

class DiscoverablePlugin(NotifierPlugin):
    @property
    def name(self):
        return "discoverable"

    @property
    def help_msg(self):
        return "## Discoverable"

    @property
    def version(self):
        return "0.1.0"

    def start(self):
        pass

    def stop(self):
        pass

    def notify(self, event, data):
        pass
""")

    pm = PluginManager()
    with patch("taskpps.services.plugin_manager.get_plugins_dir", return_value=plugins_dir):
        pm.discover_plugins()

    from taskpps.db.engine import get_session_factory
    async with get_session_factory()() as session:
        from sqlalchemy import select
        result = await session.execute(select(Plugin).where(Plugin.name == "discoverable"))
        record = result.scalar_one_or_none()
        assert record is not None
        assert record.type == "NotifierPlugin"
        assert record.version == "0.1.0"
        assert record.enabled is False
        assert record.help_msg == "## Discoverable"


@pytest.mark.asyncio
@pytest.mark.zentao("TC-S0495", domain="server/plugins", priority="P1")
async def test_discover_upserts_existing(db_engine, tmp_project):
    """验证重复 discover 只更新已有记录, 不重复插入。"""
    _setup_config(tmp_project)

    from taskpps.db.engine import get_session_factory

    async with get_session_factory()() as session:
        plugin = Plugin(name="upsertable", type="NotifierPlugin", version="0.1.0", help_msg="## Old")
        session.add(plugin)
        await session.commit()

    plugins_dir = tmp_project / "plugins"
    plugin_file = plugins_dir / "upsertable.py"
    plugin_file.write_text("""
from taskpps.plugins.base import NotifierPlugin

class UpsertablePlugin(NotifierPlugin):
    @property
    def name(self):
        return "upsertable"

    @property
    def help_msg(self):
        return "## New Help"

    @property
    def version(self):
        return "0.2.0"

    def start(self):
        pass

    def stop(self):
        pass

    def notify(self, event, data):
        pass
""")

    pm = PluginManager()
    with patch("taskpps.services.plugin_manager.get_plugins_dir", return_value=plugins_dir):
        pm.discover_plugins()

    async with get_session_factory()() as session:
        from sqlalchemy import select
        result = await session.execute(select(Plugin).where(Plugin.name == "upsertable"))
        records = result.scalars().all()
        assert len(records) == 1
        record = records[0]
        assert record.version == "0.2.0"
        assert record.help_msg == "## New Help"


@pytest.mark.zentao("TC-S0496", domain="server/plugins", priority="P1")
async def test_start_triggers_only_enabled(db_engine, tmp_project):
    """验证 start_triggers 只启动 enabled=true 的插件 (禁用插件静默跳过)."""

    _setup_config(tmp_project)

    from taskpps.db.engine import get_session_factory

    async with get_session_factory()() as session:
        p1 = Plugin(name="cron:0 * * * *:deploy.yaml", type="TriggerPlugin", version="1.0.0", help_msg="## T1", enabled=True)
        p2 = Plugin(name="cron:*/5 * * * *:build.yaml", type="TriggerPlugin", version="1.0.0", help_msg="## T2", enabled=False)
        session.add_all([p1, p2])
        await session.commit()

    from taskpps.config import Settings, TriggerConfig

    settings = Settings(triggers=[
        TriggerConfig(type="cron", schedule="0 * * * *", pipeline="deploy.yaml"),
        TriggerConfig(type="cron", schedule="*/5 * * * *", pipeline="build.yaml"),
    ])

    pm = PluginManager()
    with patch("taskpps.services.plugin_manager.get_settings", return_value=settings):
        pm.start_triggers(callback=lambda x: None)

    # deploy 的 trigger 应该启动 (enabled=true)
    deploy_trigger = pm.get("cron:0 * * * *:deploy.yaml")
    assert deploy_trigger is not None
    assert deploy_trigger._running is True

    # build 的 trigger 不应启动 (enabled=false, 被跳过)
    build_trigger = pm.get("cron:*/5 * * * *:build.yaml")
    assert build_trigger is None

    pm.stop_all()

@pytest.mark.asyncio
@pytest.mark.zentao("TC-S0497", domain="server/plugins", priority="P1")
async def test_pipeline_not_exists_error(db_engine, tmp_project):
    """验证 pipeline 不存在时返回明确错误信息。"""
    _setup_config(tmp_project)

    from taskpps.db.engine import get_session_factory

    async with get_session_factory()() as session:
        p = Plugin(name="cron:0 * * * *:nonexistent.yaml", type="TriggerPlugin", version="1.0.0", help_msg="## T", enabled=True)
        session.add(p)
        await session.commit()

    from taskpps.config import Settings, TriggerConfig

    settings = Settings(triggers=[
        TriggerConfig(type="cron", schedule="0 * * * *", pipeline="nonexistent.yaml"),
    ])

    pm = PluginManager()
    with (
        patch("taskpps.services.plugin_manager.get_settings", return_value=settings),
        patch("taskpps.services.plugin_manager.get_pipelines_dir", return_value=tmp_project / "pipelines"),
        pytest.raises(FileNotFoundError, match=r"Pipeline.*不存在"),
    ):
        pm.start_triggers(callback=lambda x: None)


@pytest.mark.asyncio
@pytest.mark.zentao("TC-S0498", domain="server/plugins", priority="P1")
async def test_plugin_disabled_is_skipped(db_engine, tmp_project):
    """验证插件未启用时 start_triggers 跳过该触发器的启动。"""
    _setup_config(tmp_project)

    from taskpps.db.engine import get_session_factory

    async with get_session_factory()() as session:
        p = Plugin(name="cron:0 * * * *:disabled.yaml", type="TriggerPlugin", version="1.0.0", help_msg="## T", enabled=False)
        session.add(p)
        await session.commit()

    from taskpps.config import Settings, TriggerConfig

    settings = Settings(triggers=[
        TriggerConfig(type="cron", schedule="0 * * * *", pipeline="disabled.yaml"),
    ])

    pm = PluginManager()
    with patch("taskpps.services.plugin_manager.get_settings", return_value=settings):
        # disabled 插件被静默跳过, 不会报错
        pm.start_triggers(callback=lambda x: None)

    assert pm.get("cron:0 * * * *:disabled.yaml") is None
    pm.stop_all()


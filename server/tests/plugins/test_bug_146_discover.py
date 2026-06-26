from __future__ import annotations

from unittest.mock import patch

import pytest

from taskpps.services.cron_trigger import CronTrigger
from taskpps.services.plugin_manager import PluginManager


class TestBug146PluginDiscovery:
    """Bug #146 问题1：插件管理页面无插件显示。
    
    根因：plugins/ 目录为空，discover_plugins() 不注册任何插件。
    内建 CronTrigger 不在 project plugins 目录下，不会被 discover。
    """

    @pytest.mark.zentao("TC-S0506", domain="server/plugins", priority="P1")
    def test_discover_empty_plugins_dir_returns_empty(self, tmp_path):
        """verify: plugins/ 目录为空时 discover_plugins() 返回空列表（当前行为，作为 baseline）。"""
        pm = PluginManager()
        empty_dir = tmp_path / "plugins"
        empty_dir.mkdir()
        with patch("taskpps.services.plugin_manager.get_plugins_dir", return_value=empty_dir):
            pm.discover_plugins()
        assert pm.list_plugins() == []

    @pytest.mark.zentao("TC-S0507", domain="server/plugins", priority="P1")
    def test_cron_trigger_not_discovered_from_empty_dir(self, tmp_path):
        """verify: 空 plugins/ 目录下 discover_plugins() 不会注册 CronTrigger。
        
        CronTrigger 定义在 server/taskpps/plugins/cron_trigger.py，
        不在 project workdir/plugins/ 目录内，因此不会被 discover_plugins 发现。
        """
        pm = PluginManager()
        empty_dir = tmp_path / "plugins"
        empty_dir.mkdir()
        with patch("taskpps.services.plugin_manager.get_plugins_dir", return_value=empty_dir):
            pm.discover_plugins()
        assert "cron" not in str(pm.list_plugins())

    @pytest.mark.zentao("TC-S0508", domain="server/plugins", priority="P1")
    def test_no_triggers_from_empty_config(self):
        """verify: triggers=[] 时 start_triggers() 不注册任何触发器。"""
        pm = PluginManager()
        with patch("taskpps.services.plugin_manager.get_settings") as mock_settings:
            mock_settings.return_value.triggers = []
            pm.start_triggers()
        assert pm.list_plugins() == []

    @pytest.mark.zentao("TC-S0509", domain="server/plugins", priority="P1")
    def test_discover_with_plugins_in_dir_registers_them(self, tmp_path):
        """verify: plugins/ 目录下有合法插件时 discover_plugins() 能注册它们。
        
        这是修复验证——部署后确保 plugins/ 目录有插件时系统能正常工作。
        """
        plugins_dir = tmp_path / "plugins"
        plugins_dir.mkdir()
        plugin_file = plugins_dir / "my_plugin.py"
        plugin_file.write_text("""
from taskpps.services.plugin_base import TriggerPlugin

class MyPlugin(TriggerPlugin):
    @property
    def name(self):
        return "my-plugin"

    @property
    def help_msg(self):
        return "## My Plugin"

    @property
    def version(self):
        return "1.0.0"

    def start(self):
        pass

    def stop(self):
        pass

    def get_type(self):
        return "custom"
""")

        pm = PluginManager()
        with patch("taskpps.services.plugin_manager.get_plugins_dir", return_value=plugins_dir):
            pm.discover_plugins()
        assert "my-plugin" in pm.list_plugins()

    @pytest.mark.zentao("TC-S0510", domain="server/plugins", priority="P1")
    def test_cron_trigger_isinstance_trigger_plugin(self):
        """verify: CronTrigger 正确继承 TriggerPlugin 并可正常实例化。"""
        trigger = CronTrigger(expression="0 * * * *", pipeline_file="deploy.yaml")
        from taskpps.services.plugin_base import TriggerPlugin
        assert isinstance(trigger, TriggerPlugin)

    @pytest.mark.zentao("TC-S0511", domain="server/plugins", priority="P1")
    def test_discover_plugins_dir_nonexistent_no_error(self, tmp_path):
        """verify: plugins/ 目录不存在时 discover_plugins() 不报错，列表为空。"""
        pm = PluginManager()
        nonexistent = tmp_path / "nonexistent"
        with patch("taskpps.services.plugin_manager.get_plugins_dir", return_value=nonexistent):
            pm.discover_plugins()
        assert pm.list_plugins() == []

    @pytest.mark.zentao("TC-S0512", domain="server/plugins", priority="P2")
    def test_start_triggers_with_cron_config_creates_trigger_plugin(self, tmp_path):
        """verify: triggers 配置中有 cron 类型时 start_triggers 创建并注册 CronTrigger。"""
        from taskpps.config import Settings, TriggerConfig

        pipelines_dir = tmp_path / "pipelines"
        pipelines_dir.mkdir()
        (pipelines_dir / "deploy.yaml").write_text("name: deploy")

        settings = Settings(triggers=[
            TriggerConfig(type="cron", schedule="0 * * * *", pipeline="deploy.yaml"),
        ])

        pm = PluginManager()
        with (
            patch("taskpps.services.plugin_manager.get_settings", return_value=settings),
            patch("taskpps.services.plugin_manager.get_pipelines_dir", return_value=pipelines_dir),
        ):
            pm.start_triggers(callback=lambda x: None)

        assert len(pm.list_plugins()) > 0
        pm.stop_all()

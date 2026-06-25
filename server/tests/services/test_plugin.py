from __future__ import annotations

from unittest.mock import patch

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


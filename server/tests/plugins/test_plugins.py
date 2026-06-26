from unittest.mock import MagicMock, patch

import pytest

from taskpps.services.plugin_base import BasePlugin, ExecutorPlugin, NotifierPlugin, TriggerPlugin
from taskpps.services.cron_trigger import CronTrigger
from taskpps.services.plugin_manager import PluginManager


class TestBasePlugin:
    def test_is_abstract(self):
        with pytest.raises(TypeError):
            BasePlugin()

    def test_interface(self):
        class ConcretePlugin(BasePlugin):
            @property
            def name(self):
                return "concrete"

            @property
            def help_msg(self):
                return "## Help"

            @property
            def version(self):
                return "1.0.0"

            def start(self):
                pass

            def stop(self):
                pass

        p = ConcretePlugin()
        assert p.name == "concrete"
        assert p.help_msg == "## Help"
        assert p.version == "1.0.0"

    @pytest.mark.zentao("TC-S0490", domain="server/plugins", priority="P1")
    def test_missing_help_msg_raises(self):
        """验证未实现 help_msg 的子类实例化报 TypeError。"""
        class NoHelpPlugin(BasePlugin):
            @property
            def name(self):
                return "no-help"

            @property
            def version(self):
                return "1.0"

            def start(self):
                pass

            def stop(self):
                pass

        with pytest.raises(TypeError):
            NoHelpPlugin()

    @pytest.mark.zentao("TC-S0491", domain="server/plugins", priority="P1")
    def test_missing_version_raises(self):
        """验证未实现 version 的子类实例化报 TypeError。"""
        class NoVersionPlugin(BasePlugin):
            @property
            def name(self):
                return "no-version"

            @property
            def help_msg(self):
                return "## Help"

            def start(self):
                pass

            def stop(self):
                pass

        with pytest.raises(TypeError):
            NoVersionPlugin()


class TestTriggerPlugin:
    def test_is_abstract(self):
        with pytest.raises(TypeError):
            TriggerPlugin()

    def test_interface(self):
        class ConcreteTrigger(TriggerPlugin):
            @property
            def name(self):
                return "test-trigger"

            @property
            def help_msg(self):
                return "## Trigger"

            @property
            def version(self):
                return "1.0.0"

            def start(self):
                pass

            def stop(self):
                pass

            def get_type(self):
                return "test"

        t = ConcreteTrigger()
        assert t.get_type() == "test"


class TestNotifierPlugin:
    def test_is_abstract(self):
        with pytest.raises(TypeError):
            NotifierPlugin()

    def test_interface(self):
        class ConcreteNotifier(NotifierPlugin):
            @property
            def name(self):
                return "test-notifier"

            @property
            def help_msg(self):
                return "## Notifier"

            @property
            def version(self):
                return "1.0.0"

            def start(self):
                pass

            def stop(self):
                pass

            def notify(self, event, data):
                pass

        n = ConcreteNotifier()
        n.notify("test", {})


class TestExecutorPlugin:
    def test_is_abstract(self):
        with pytest.raises(TypeError):
            ExecutorPlugin()

    def test_interface(self):
        class ConcreteExecutor(ExecutorPlugin):
            @property
            def name(self):
                return "test-executor"

            @property
            def help_msg(self):
                return "## Executor"

            @property
            def version(self):
                return "1.0.0"

            def start(self):
                pass

            def stop(self):
                pass

            def can_handle(self, task_type):
                return True

        e = ConcreteExecutor()
        assert e.can_handle("test") is True


class TestCronTrigger:
    @pytest.mark.zentao("TC-S0462", domain="server/plugins", priority="P2")
    def test_name(self):
        trigger = CronTrigger(expression="0 * * * *", pipeline_file="deploy.yaml")
        assert trigger.name == "cron:0 * * * *:deploy.yaml"

    @pytest.mark.zentao("TC-S0463", domain="server/plugins", priority="P2")
    def test_type(self):
        trigger = CronTrigger(expression="0 * * * *", pipeline_file="deploy.yaml")
        assert trigger.get_type() == "cron"

    @pytest.mark.zentao("TC-S0492", domain="server/plugins", priority="P1")
    def test_help_msg(self):
        trigger = CronTrigger(expression="0 * * * *", pipeline_file="deploy.yaml")
        assert "Cron" in trigger.help_msg

    @pytest.mark.zentao("TC-S0493", domain="server/plugins", priority="P1")
    def test_version(self):
        trigger = CronTrigger(expression="0 * * * *", pipeline_file="deploy.yaml")
        assert trigger.version == "1.0.0"

    @pytest.mark.zentao("TC-S0464", domain="server/plugins", priority="P1")
    def test_start_stop(self):
        trigger = CronTrigger(expression="0 * * * *", pipeline_file="deploy.yaml")
        trigger.start()
        assert trigger._running is True
        trigger.stop()
        assert trigger._running is False

    @pytest.mark.zentao("TC-S0465", domain="server/plugins", priority="P2")
    def test_start_twice(self):
        trigger = CronTrigger(expression="0 * * * *", pipeline_file="deploy.yaml")
        trigger.start()
        assert trigger._running is True
        trigger.start()
        assert trigger._running is True
        trigger.stop()

    @pytest.mark.zentao("TC-S0466", domain="server/plugins", priority="P2")
    def test_run_loop_with_callback(self, tmp_path):
        callback = MagicMock()
        trigger = CronTrigger(expression="* * * * *", pipeline_file="deploy.yaml", callback=callback)
        trigger._running = True
        trigger._stop_event.set()
        trigger._run_loop()
        assert trigger._running is True

    @pytest.mark.zentao("TC-S0467", domain="server/plugins", priority="P1")
    def test_run_loop_callback_exception(self, tmp_path):
        callback = MagicMock(side_effect=Exception("callback error"))
        trigger = CronTrigger(expression="* * * * *", pipeline_file="deploy.yaml", callback=callback)
        trigger._running = True
        trigger._stop_event.set()
        trigger._run_loop()


class TestPluginManagerPlugins:
    @pytest.mark.zentao("TC-S0468", domain="server/plugins", priority="P2")
    def test_default_empty(self):
        pm = PluginManager()
        assert pm.list_plugins() == []

    @pytest.mark.zentao("TC-S0469", domain="server/plugins", priority="P2")
    def test_register(self):
        pm = PluginManager()
        plugin = MockPlugin()
        pm.register("mock", plugin)
        assert "mock" in pm.list_plugins()
        assert pm.get("mock") is plugin

    @pytest.mark.zentao("TC-S0470", domain="server/plugins", priority="P2")
    def test_discover_no_dir(self, tmp_path):
        pm = PluginManager()
        with patch("taskpps.services.plugin_manager.get_plugins_dir", return_value=tmp_path / "nonexistent"):
            pm.discover_plugins()
            assert pm.list_plugins() == []

    @pytest.mark.zentao("TC-S0471", domain="server/plugins", priority="P2")
    def test_discover_with_plugin_dir(self, tmp_path):
        plugins_dir = tmp_path / "plugins"
        plugins_dir.mkdir()
        plugin_subdir = plugins_dir / "my_plugin"
        plugin_subdir.mkdir()
        (plugin_subdir / "__init__.py").write_text("")
        (plugin_subdir / "plugin.py").write_text("")

        pm = PluginManager()
        with patch("taskpps.services.plugin_manager.get_plugins_dir", return_value=plugins_dir):
            pm.discover_plugins()

    @pytest.mark.zentao("TC-S0472", domain="server/plugins", priority="P2")
    def test_discover_with_py_file(self, tmp_path):
        plugins_dir = tmp_path / "plugins"
        plugins_dir.mkdir()
        plugin_file = plugins_dir / "simple_plugin.py"
        plugin_file.write_text("""
from taskpps.services.plugin_base import BasePlugin

class SimplePlugin(BasePlugin):
    @property
    def name(self):
        return "simple"

    @property
    def help_msg(self):
        return "## Simple Plugin"

    @property
    def version(self):
        return "1.0.0"

    def start(self):
        pass

    def stop(self):
        pass
""")

        pm = PluginManager()
        with patch("taskpps.services.plugin_manager.get_plugins_dir", return_value=plugins_dir):
            pm.discover_plugins()
            assert "simple" in pm.list_plugins()

    @pytest.mark.zentao("TC-S0473", domain="server/plugins", priority="P2")
    def test_discover_bad_plugin(self, tmp_path):
        plugins_dir = tmp_path / "plugins"
        plugins_dir.mkdir()
        bad_file = plugins_dir / "bad_plugin.py"
        bad_file.write_text("import nonexistent_module\n")

        pm = PluginManager()
        with patch("taskpps.services.plugin_manager.get_plugins_dir", return_value=plugins_dir):
            pm.discover_plugins()

    @pytest.mark.zentao("TC-S0474", domain="server/plugins", priority="P1")
    def test_start_triggers_from_config(self, tmp_path):
        config_file = tmp_path / "taskpps.yaml"
        config_file.write_text(
            "server:\n  host: 127.0.0.1\n  port: 26521\n"
            "executor:\n  default_timeout: 60\n  max_workers: 4\n"
            "triggers:\n"
            "  - type: cron\n"
            "    schedule: '0 * * * *'\n"
            "    pipeline: deploy.yaml\n"
        )

        pm = PluginManager()
        with patch("taskpps.services.plugin_manager.get_settings") as mock_settings:
            mock_settings.return_value.triggers = []
            pm.start_triggers()

    @pytest.mark.zentao("TC-S0475", domain="server/plugins", priority="P2")
    def test_start_triggers_with_cron(self, tmp_path):
        from taskpps.config import Settings, TriggerConfig

        settings = Settings(triggers=[TriggerConfig(type="cron", schedule="0 * * * *", pipeline="deploy.yaml")])

        pm = PluginManager()
        with patch("taskpps.services.plugin_manager.get_settings", return_value=settings):
            pm.start_triggers(callback=lambda x: None)
            assert len(pm._triggers) > 0
        pm.stop_all()

    @pytest.mark.zentao("TC-S0476", domain="server/plugins", priority="P1")
    def test_stop_all(self):
        pm = PluginManager()
        pm.stop_all()

    @pytest.mark.zentao("TC-S0477", domain="server/plugins", priority="P1")
    def test_stop_all_with_error(self):
        class BadPlugin(BasePlugin):
            @property
            def name(self):
                return "bad"

            @property
            def help_msg(self):
                return "## Bad"

            @property
            def version(self):
                return "1.0.0"

            def start(self):
                pass

            def stop(self):
                raise Exception("stop error")

        pm = PluginManager()
        pm.register("bad", BadPlugin())
        pm.stop_all()

    @pytest.mark.zentao("TC-S0478", domain="server/plugins", priority="P2")
    def test_try_load_plugin_no_init(self, tmp_path):
        plugins_dir = tmp_path / "plugins"
        plugins_dir.mkdir()
        plugin_dir = plugins_dir / "no_init"
        plugin_dir.mkdir()

        pm = PluginManager()
        pm._try_load_plugin(plugin_dir)

    @pytest.mark.zentao("TC-S0479", domain="server/plugins", priority="P2")
    def test_try_load_plugin_dir_with_init(self, tmp_path):
        plugins_dir = tmp_path / "plugins"
        plugins_dir.mkdir()
        plugin_dir = plugins_dir / "empty_plugin"
        plugin_dir.mkdir()
        (plugin_dir / "__init__.py").write_text("")

        pm = PluginManager()
        pm._try_load_plugin(plugin_dir)

    @pytest.mark.zentao("TC-S0480", domain="server/plugins", priority="P1")
    def test_try_load_plugin_module_error(self, tmp_path):
        plugins_dir = tmp_path / "plugins"
        plugins_dir.mkdir()
        plugin_dir = plugins_dir / "err_plugin"
        plugin_dir.mkdir()
        (plugin_dir / "__init__.py").write_text("import nonexistent_module\n")

        pm = PluginManager()
        pm._try_load_plugin(plugin_dir)


class MockPlugin(BasePlugin):
    @property
    def name(self):
        return "mock"

    @property
    def help_msg(self):
        return "## Mock Plugin"

    @property
    def version(self):
        return "1.0.0"

    def start(self):
        pass

    def stop(self):
        pass


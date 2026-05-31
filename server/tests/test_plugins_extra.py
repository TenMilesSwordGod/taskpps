from unittest.mock import MagicMock, patch

from taskpps.plugins.base import BasePlugin, ExecutorPlugin, NotifierPlugin, TriggerPlugin
from taskpps.plugins.cron_trigger import CronTrigger
from taskpps.services.plugin_manager import PluginManager


def test_base_plugin_interface():
    class ConcretePlugin(BasePlugin):
        @property
        def name(self):
            return "concrete"

        def start(self):
            pass

        def stop(self):
            pass

    p = ConcretePlugin()
    assert p.name == "concrete"


def test_trigger_plugin_interface():
    class ConcreteTrigger(TriggerPlugin):
        @property
        def name(self):
            return "test-trigger"

        def start(self):
            pass

        def stop(self):
            pass

        def get_type(self):
            return "test"

    t = ConcreteTrigger()
    assert t.get_type() == "test"


def test_notifier_plugin_interface():
    class ConcreteNotifier(NotifierPlugin):
        @property
        def name(self):
            return "test-notifier"

        def start(self):
            pass

        def stop(self):
            pass

        def notify(self, event, data):
            pass

    n = ConcreteNotifier()
    n.notify("test", {})


def test_executor_plugin_interface():
    class ConcreteExecutor(ExecutorPlugin):
        @property
        def name(self):
            return "test-executor"

        def start(self):
            pass

        def stop(self):
            pass

        def can_handle(self, task_type):
            return True

    e = ConcreteExecutor()
    assert e.can_handle("test") is True


def test_cron_trigger_start_twice():
    trigger = CronTrigger(expression="0 * * * *", pipeline_file="deploy.yaml")
    trigger.start()
    assert trigger._running is True
    trigger.start()
    assert trigger._running is True
    trigger.stop()


def test_plugin_manager_discover_no_dir(tmp_path):
    pm = PluginManager()
    with patch("taskpps.services.plugin_manager.get_plugins_dir", return_value=tmp_path / "nonexistent"):
        pm.discover_plugins()
        assert pm.list_plugins() == []


def test_plugin_manager_discover_with_plugin_dir(tmp_path):
    plugins_dir = tmp_path / "plugins"
    plugins_dir.mkdir()
    plugin_subdir = plugins_dir / "my_plugin"
    plugin_subdir.mkdir()
    (plugin_subdir / "__init__.py").write_text("")
    (plugin_subdir / "plugin.py").write_text("")

    pm = PluginManager()
    with patch("taskpps.services.plugin_manager.get_plugins_dir", return_value=plugins_dir):
        pm.discover_plugins()


def test_plugin_manager_discover_with_py_file(tmp_path):
    plugins_dir = tmp_path / "plugins"
    plugins_dir.mkdir()
    plugin_file = plugins_dir / "simple_plugin.py"
    plugin_file.write_text("""
from taskpps.plugins.base import BasePlugin

class SimplePlugin(BasePlugin):
    @property
    def name(self):
        return "simple"

    def start(self):
        pass

    def stop(self):
        pass
""")

    pm = PluginManager()
    with patch("taskpps.services.plugin_manager.get_plugins_dir", return_value=plugins_dir):
        pm.discover_plugins()
        assert "simple" in pm.list_plugins()


def test_plugin_manager_discover_bad_plugin(tmp_path):
    plugins_dir = tmp_path / "plugins"
    plugins_dir.mkdir()
    bad_file = plugins_dir / "bad_plugin.py"
    bad_file.write_text("import nonexistent_module\n")

    pm = PluginManager()
    with patch("taskpps.services.plugin_manager.get_plugins_dir", return_value=plugins_dir):
        pm.discover_plugins()


def test_plugin_manager_start_triggers_from_config(tmp_path):
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


def test_plugin_manager_start_triggers_with_cron(tmp_path):
    from taskpps.config import Settings, TriggerConfig

    settings = Settings(triggers=[TriggerConfig(type="cron", schedule="0 * * * *", pipeline="deploy.yaml")])

    pm = PluginManager()
    with patch("taskpps.services.plugin_manager.get_settings", return_value=settings):
        pm.start_triggers(callback=lambda x: None)
        assert len(pm._triggers) > 0
    pm.stop_all()


def test_plugin_manager_stop_all():
    pm = PluginManager()
    pm.stop_all()


def test_plugin_manager_stop_all_with_error():
    class BadPlugin(BasePlugin):
        @property
        def name(self):
            return "bad"

        def start(self):
            pass

        def stop(self):
            raise Exception("stop error")

    pm = PluginManager()
    pm.register("bad", BadPlugin())
    pm.stop_all()


def test_plugin_manager_try_load_plugin_no_init(tmp_path):
    plugins_dir = tmp_path / "plugins"
    plugins_dir.mkdir()
    plugin_dir = plugins_dir / "no_init"
    plugin_dir.mkdir()

    pm = PluginManager()
    pm._try_load_plugin(plugin_dir)


def test_plugin_manager_try_load_plugin_dir_with_init(tmp_path):
    plugins_dir = tmp_path / "plugins"
    plugins_dir.mkdir()
    plugin_dir = plugins_dir / "empty_plugin"
    plugin_dir.mkdir()
    (plugin_dir / "__init__.py").write_text("")

    pm = PluginManager()
    pm._try_load_plugin(plugin_dir)


def test_plugin_manager_try_load_plugin_module_error(tmp_path):
    plugins_dir = tmp_path / "plugins"
    plugins_dir.mkdir()
    plugin_dir = plugins_dir / "err_plugin"
    plugin_dir.mkdir()
    (plugin_dir / "__init__.py").write_text("import nonexistent_module\n")

    pm = PluginManager()
    pm._try_load_plugin(plugin_dir)


def test_cron_trigger_run_loop_with_callback(tmp_path):
    callback = MagicMock()
    trigger = CronTrigger(expression="* * * * *", pipeline_file="deploy.yaml", callback=callback)
    trigger._running = True
    trigger._stop_event.set()
    trigger._run_loop()
    assert trigger._running is True


def test_cron_trigger_run_loop_callback_exception(tmp_path):
    callback = MagicMock(side_effect=Exception("callback error"))
    trigger = CronTrigger(expression="* * * * *", pipeline_file="deploy.yaml", callback=callback)
    trigger._running = True
    trigger._stop_event.set()
    trigger._run_loop()

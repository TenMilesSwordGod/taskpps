import pytest
from taskpps.plugins.base import BasePlugin, TriggerPlugin, NotifierPlugin, ExecutorPlugin
from taskpps.plugins.cron_trigger import CronTrigger


def test_base_plugin_is_abstract():
    with pytest.raises(TypeError):
        BasePlugin()


def test_trigger_plugin_is_abstract():
    with pytest.raises(TypeError):
        TriggerPlugin()


def test_notifier_plugin_is_abstract():
    with pytest.raises(TypeError):
        NotifierPlugin()


def test_executor_plugin_is_abstract():
    with pytest.raises(TypeError):
        ExecutorPlugin()


def test_cron_trigger_name():
    trigger = CronTrigger(expression="0 * * * *", pipeline_file="deploy.yaml")
    assert trigger.name == "cron:0 * * * *:deploy.yaml"


def test_cron_trigger_type():
    trigger = CronTrigger(expression="0 * * * *", pipeline_file="deploy.yaml")
    assert trigger.get_type() == "cron"


def test_cron_trigger_start_stop():
    trigger = CronTrigger(expression="0 * * * *", pipeline_file="deploy.yaml")
    trigger.start()
    assert trigger._running is True
    trigger.stop()
    assert trigger._running is False


def test_plugin_manager():
    from taskpps.services.plugin_manager import PluginManager
    pm = PluginManager()
    assert pm.list_plugins() == []


class MockPlugin(BasePlugin):
    @property
    def name(self):
        return "mock"

    def start(self):
        pass

    def stop(self):
        pass


def test_plugin_manager_register():
    from taskpps.services.plugin_manager import PluginManager
    pm = PluginManager()
    plugin = MockPlugin()
    pm.register("mock", plugin)
    assert "mock" in pm.list_plugins()
    assert pm.get("mock") is plugin

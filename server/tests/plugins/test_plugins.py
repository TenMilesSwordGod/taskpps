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

    @pytest.mark.zentao("TC-S3350", domain="server/plugins", priority="P1")
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

    @pytest.mark.zentao("TC-S3351", domain="server/plugins", priority="P1")
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
        # v2 (2026-09 治理): 原用例在测试内定义 notify=pass 的桩再调用自身，
        # 断言对象是测试代码而非生产契约。重写为验证 NotifierPlugin 的抽象
        # 契约：子类未实现 notify 时实例化必须 TypeError。
        class NoNotifyNotifier(NotifierPlugin):
            @property
            def name(self):
                return "no-notify"

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

        with pytest.raises(TypeError):
            NoNotifyNotifier()


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

    @pytest.mark.zentao("TC-S3358", domain="server/plugins", priority="P1")
    def test_help_msg(self):
        trigger = CronTrigger(expression="0 * * * *", pipeline_file="deploy.yaml")
        assert "Cron" in trigger.help_msg

    @pytest.mark.zentao("TC-S3359", domain="server/plugins", priority="P1")
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
    def test_run_loop_callback_exception(self, caplog):
        # v2 (2026-09 治理): 原用例只设置 stop_event 后调用 _run_loop，回调
        # 从未执行（stop 已置位，循环直接退出），零断言。重写为让 croniter
        # 返回"当前时刻"使回调真正触发，回调抛异常后由回调自身置位 stop
        # 事件结束循环，断言异常被吞并写入 error 日志。
        import logging
        from datetime import datetime, timezone

        def _boom(_pipeline_file):
            trigger._stop_event.set()
            raise Exception("callback error")

        trigger = CronTrigger(expression="* * * * *", pipeline_file="deploy.yaml", callback=_boom)
        trigger._running = True

        with (
            patch("taskpps.services.cron_trigger.croniter") as mock_croniter,
            caplog.at_level(logging.ERROR, logger="taskpps.services.cron_trigger"),
        ):
            mock_croniter.return_value.get_next.return_value = datetime.now(timezone.utc)
            trigger._run_loop()

        assert any("callback error" in r.message for r in caplog.records)


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
        # v2 (2026-09 治理): 原用例写了目录+空插件文件后零断言。重写为
        # 目录形态的真实插件并断言发现成功。
        plugins_dir = tmp_path / "plugins"
        plugins_dir.mkdir()
        plugin_subdir = plugins_dir / "dir_plugin"
        plugin_subdir.mkdir()
        (plugin_subdir / "__init__.py").write_text("""
from taskpps.services.plugin_base import BasePlugin

class DirPlugin(BasePlugin):
    @property
    def name(self):
        return "dir-plugin"

    @property
    def help_msg(self):
        return "## Dir Plugin"

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

        assert "dir-plugin" in pm.list_plugins()

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
        # v2 (2026-09 治理): 原用例零断言。重写为断言坏插件被跳过、
        # 同目录好插件仍被加载（发现流程对坏插件容错）。
        plugins_dir = tmp_path / "plugins"
        plugins_dir.mkdir()
        bad_file = plugins_dir / "bad_plugin.py"
        bad_file.write_text("import nonexistent_module\n")
        good_file = plugins_dir / "good_plugin.py"
        good_file.write_text("""
from taskpps.services.plugin_base import BasePlugin

class GoodPlugin(BasePlugin):
    @property
    def name(self):
        return "good-plugin"

    @property
    def help_msg(self):
        return "## Good"

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

        assert pm.list_plugins() == ["good-plugin"]

    @pytest.mark.zentao("TC-S0474", domain="server/plugins", priority="P1")
    def test_start_triggers_from_config(self, tmp_path):
        # v2 (2026-09 治理): 原用例写了一份含 triggers 的配置文件却从未加载，
        # 还把 get_settings mock 成 triggers=[]，名字完全名不副实。重写为真实
        # 加载该配置文件，断言 cron 触发器被注册并已启动。
        config_file = tmp_path / "taskpps.yaml"
        config_file.write_text(
            "server:\n  host: 127.0.0.1\n  port: 26521\n"
            "executor:\n  default_timeout: 60\n  max_workers: 4\n"
            "triggers:\n"
            "  - type: cron\n"
            "    schedule: '0 * * * *'\n"
            "    pipeline: deploy.yaml\n"
        )
        import taskpps.config as cfg

        cfg.load_settings(str(config_file))

        pm = PluginManager()
        pm.start_triggers(callback=lambda x: None)

        trigger = pm.get("cron:0 * * * *:deploy.yaml")
        assert trigger is not None
        assert trigger._running is True
        pm.stop_all()

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
        # v2 (2026-09 治理): 原用例在空 manager 上调 stop_all，纯 no-op。
        # 重写为断言 stop_all 对已注册插件确实调用了 stop()。
        class TrackedPlugin(BasePlugin):
            def __init__(self):
                self.stopped = False

            @property
            def name(self):
                return "tracked"

            @property
            def help_msg(self):
                return "## Tracked"

            @property
            def version(self):
                return "1.0.0"

            def start(self):
                pass

            def stop(self):
                self.stopped = True

        plugin = TrackedPlugin()
        pm = PluginManager()
        pm.register("tracked", plugin)
        pm.stop_all()

        assert plugin.stopped is True

    @pytest.mark.zentao("TC-S0477", domain="server/plugins", priority="P1")
    def test_stop_all_with_error(self):
        # v2 (2026-09 治理): 原用例插件 stop 抛异常但零断言。重写为断言异常
        # 被吞掉且后续插件仍能停止（stop_all 对单插件故障容错）。
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

        class TrackedPlugin(BasePlugin):
            def __init__(self):
                self.stopped = False

            @property
            def name(self):
                return "tracked"

            @property
            def help_msg(self):
                return "## Tracked"

            @property
            def version(self):
                return "1.0.0"

            def start(self):
                pass

            def stop(self):
                self.stopped = True

        tracked = TrackedPlugin()
        pm = PluginManager()
        pm.register("bad", BadPlugin())
        pm.register("tracked", tracked)
        pm.stop_all()

        assert tracked.stopped is True

    @pytest.mark.zentao("TC-S0478", domain="server/plugins", priority="P2")
    def test_try_load_plugin_no_init(self, tmp_path):
        # v2 (2026-09 治理): 原用例直调私有方法零断言。重写为断言没有
        # __init__.py 的插件目录不会被加载。
        plugins_dir = tmp_path / "plugins"
        plugins_dir.mkdir()
        plugin_dir = plugins_dir / "no_init"
        plugin_dir.mkdir()

        pm = PluginManager()
        pm._try_load_plugin(plugin_dir)

        assert pm.list_plugins() == []

    @pytest.mark.zentao("TC-S0479", domain="server/plugins", priority="P2")
    def test_try_load_plugin_dir_with_init(self, tmp_path):
        # v2 (2026-09 治理): 原用例空 __init__.py 加载成败都无断言。重写为
        # 断言空包不会注册任何插件（无插件类可发现）。
        plugins_dir = tmp_path / "plugins"
        plugins_dir.mkdir()
        plugin_dir = plugins_dir / "empty_plugin"
        plugin_dir.mkdir()
        (plugin_dir / "__init__.py").write_text("")

        pm = PluginManager()
        pm._try_load_plugin(plugin_dir)

        assert pm.list_plugins() == []

    @pytest.mark.zentao("TC-S0480", domain="server/plugins", priority="P1")
    def test_try_load_plugin_module_error(self, tmp_path):
        # v2 (2026-09 治理): 原用例直调私有方法零断言。重写为断言导入报错
        # 的插件目录被跳过且不抛异常。
        plugins_dir = tmp_path / "plugins"
        plugins_dir.mkdir()
        plugin_dir = plugins_dir / "err_plugin"
        plugin_dir.mkdir()
        (plugin_dir / "__init__.py").write_text("import nonexistent_module\n")

        pm = PluginManager()
        pm._try_load_plugin(plugin_dir)

        assert pm.list_plugins() == []


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


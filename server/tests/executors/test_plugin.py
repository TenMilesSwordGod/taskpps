from __future__ import annotations

import stat
import sys
from unittest.mock import patch

import pytest

from taskpps.domain.pipeline import ResolvedTask
from taskpps.executors import create_executor
from taskpps.executors.plugin import PluginExecutor


def _make_mock_plugin(tmp_path, name, body):
    binary = tmp_path / name
    binary.write_text(f"#!{sys.executable}\n{body}")
    binary.chmod(binary.stat().st_mode | stat.S_IEXEC)
    return binary


class TestPluginExecutor:
    def test_plugin_executor_has_command(self):
        executor = PluginExecutor('echo "hello"')
        assert executor._command == 'echo "hello"'

    @pytest.mark.asyncio
    async def test_plugin_executor_execute_local(self, tmp_path):
        executor = PluginExecutor('echo "hello"')
        log_path = tmp_path / "output.log"
        result = await executor.execute(command="", env={}, log_path=log_path)
        assert result.exit_code == 0
        assert "hello" in result.stdout


class TestPluginBuilder:
    def test_build_python_plugin_command(self, tmp_path):
        from taskpps.executors import _build_python_plugin_command

        py_file = tmp_path / "test_plugin" / "plugin.py"
        py_file.parent.mkdir()
        py_file.write_text(
            "class TestPlugin:\n"
            '    """Test."""\n'
            "    type = 'executor'\n"
            "    version = '1.0.0'\n"
            "    params_schema = {'name': {'type': 'string', 'required': True}}\n"
            "    def __init__(self, name): self.name = name\n"
            "    def build_command(self): return f'echo hello {self.name}'\n"
        )

        cmd = _build_python_plugin_command(py_file, {"name": "world"})
        assert cmd == "echo hello world"

    def test_build_python_plugin_command_no_class_raises(self, tmp_path):
        from taskpps.executors import _build_python_plugin_command

        py_file = tmp_path / "bad" / "plugin.py"
        py_file.parent.mkdir()
        py_file.write_text("x = 1\n")

        with pytest.raises(ValueError, match="No plugin class"):
            _build_python_plugin_command(py_file, {})


class TestPluginCenterPython:
    @pytest.mark.asyncio
    async def test_load_python_plugin(self, tmp_path):
        from taskpps.services.plugin_center import PluginCenter

        plugin_dir = tmp_path / "test_echo"
        plugin_dir.mkdir()
        py_file = plugin_dir / "plugin.py"
        py_file.write_text(
            "class EchoPlugin:\n"
            '    """Echo — 回显消息。"""\n'
            "    type = 'executor'\n"
            "    version = '1.0.0'\n"
            "    params_schema = {'message': {'type': 'string', 'required': True}}\n"
            "    def __init__(self, message): pass\n"
            "    def build_command(self): return 'echo'\n"
        )

        pc = PluginCenter(tmp_path)
        await pc._load_python_plugin(py_file)

        assert "test_echo" in pc._plugins
        info = pc._plugins["test_echo"]
        assert info.name == "test_echo"
        assert info.type == "executor"
        assert info.version == "1.0.0"
        assert "回显消息" in info.help_msg
        assert info.status == "loaded"
        assert "test_echo" in pc._executor_map

    def test_scan_finds_plugin_py(self, tmp_path):
        from taskpps.services.plugin_center import PluginCenter

        plugin_dir = tmp_path / "echo"
        plugin_dir.mkdir()
        (plugin_dir / "plugin.py").write_text(
            "class EchoPlugin:\n"
            '    """Echo."""\n'
            "    type = 'executor'\n"
            "    version = '1.0.0'\n"
            "    params_schema = {'message': {'type': 'string'}}\n"
            "    def __init__(self, message): pass\n"
            "    def build_command(self): return 'echo'\n"
        )

        pc = PluginCenter(tmp_path)
        binaries = pc._scan_plugins_dir(tmp_path)
        assert len(binaries) == 1
        assert binaries[0].name == "plugin.py"

    def test_scan_finds_both_binary_and_python(self, tmp_path):
        from taskpps.services.plugin_center import PluginCenter

        # python plugin
        plugin_dir = tmp_path / "echo"
        plugin_dir.mkdir()
        (plugin_dir / "plugin.py").write_text(
            "class EchoPlugin:\n"
            '    """Echo."""\n'
            "    type = 'executor'\n"
            "    version = '1.0.0'\n"
            "    params_schema = {'msg': {'type': 'string'}}\n"
            "    def __init__(self, msg): pass\n"
            "    def build_command(self): return 'echo'\n"
        )

        # binary plugin (backward compat)
        bin_dir = tmp_path / "hello"
        bin_dir.mkdir()
        binary = bin_dir / "hello"
        binary.write_text(f"#!{sys.executable}\nprint('ok')\n")
        binary.chmod(binary.stat().st_mode | stat.S_IEXEC)

        pc = PluginCenter(tmp_path)
        binaries = pc._scan_plugins_dir(tmp_path)
        assert len(binaries) == 2
        names = {b.name for b in binaries}
        assert names == {"plugin.py", "hello"}

    def test_scan_ignores_other_files(self, tmp_path):
        from taskpps.services.plugin_center import PluginCenter

        (tmp_path / "readme.md").write_text("# readme")
        (tmp_path / ".hidden").write_text("...")

        pc = PluginCenter(tmp_path)
        binaries = pc._scan_plugins_dir(tmp_path)
        assert len(binaries) == 0


class TestPluginTaskType:
    def test_get_task_type_plugin(self):
        from taskpps.schemas.pipeline import TaskYAML

        task = TaskYAML(
            name="my_task",
            plugin="echo",
            params={"message": "hello"},
        )
        assert task.get_task_type() == "plugin"

    def test_get_task_type_command_when_plugin_is_none(self):
        from taskpps.schemas.pipeline import TaskYAML

        task = TaskYAML(name="my_task", command="echo hello")
        assert task.get_task_type() == "command"

    def test_invoke_priority_over_plugin(self):
        from taskpps.schemas.pipeline import InvokeSpec, TaskYAML

        task = TaskYAML(
            name="my_task",
            invoke=InvokeSpec(task="some.mod.fn"),
            plugin="echo",
            params={"message": "hello"},
        )
        assert task.get_task_type() == "invoke"


class TestPluginExecutorFactory:
    def test_plugin_type_without_host_returns_plugin_executor(self, tmp_path):
        py_file = tmp_path / "echo" / "plugin.py"
        py_file.parent.mkdir()
        py_file.write_text(
            "class EchoPlugin:\n"
            '    """Echo plugin."""\n'
            "    type = 'executor'\n"
            "    version = '1.0.0'\n"
            "    params_schema = {'message': {'type': 'string', 'required': True}}\n"
            "    def __init__(self, message): self.message = message\n"
            "    def build_command(self): return f'echo {self.message}'\n"
        )

        task = ResolvedTask(
            name="my_task",
            task_type="plugin",
            plugin="echo",
            plugin_params={"message": "hello"},
        )

        p_info = type("PInfo", (), {
            "name": "echo",
            "type": "executor",
            "binary_path": py_file,
            "status": "loaded",
        })
        mock_pc = type("MPC", (), {})()
        mock_pc.get_plugin = lambda name: p_info if name == "echo" else None

        with patch("taskpps.services.plugin_center.get_plugin_center", return_value=mock_pc):
            executor = create_executor(task)
            assert isinstance(executor, PluginExecutor)
            assert executor._command == "echo hello"

    def test_plugin_type_raises_when_not_found(self):
        task = ResolvedTask(
            name="my_task",
            task_type="plugin",
            plugin="unknown",
        )

        with patch("taskpps.services.plugin_center.get_plugin_center", return_value=None):
            with pytest.raises(ValueError, match="not found"):
                create_executor(task)

    def test_plugin_type_delegates_to_remote_when_host_set(self, tmp_path):
        py_file = tmp_path / "echo" / "plugin.py"
        py_file.parent.mkdir()
        py_file.write_text(
            "class EchoPlugin:\n"
            '    """Echo."""\n'
            "    type = 'executor'\n"
            "    version = '1.0.0'\n"
            "    params_schema = {'message': {'type': 'string', 'required': True}}\n"
            "    def __init__(self, message): self.message = message\n"
            "    def build_command(self): return f'echo {self.message}'\n"
        )

        task = ResolvedTask(
            name="my_task",
            task_type="plugin",
            plugin="echo",
            plugin_params={"message": "hello"},
            host="my-agent",
        )

        p_info = type("PInfo", (), {
            "name": "echo",
            "type": "executor",
            "binary_path": py_file,
            "status": "loaded",
        })
        mock_pc = type("MPC", (), {})()
        mock_pc.get_plugin = lambda name: p_info if name == "echo" else None

        with (
            patch("taskpps.services.plugin_center.get_plugin_center", return_value=mock_pc),
            patch("taskpps.loaders.agent_loader.get_agents_dir") as mock_dir,
        ):
            agents_dir = tmp_path / "agents"
            agents_dir.mkdir()
            agent_file = agents_dir / "my-agent.yaml"
            agent_file.write_text("host: 1.2.3.4\nport: 22\nusername: admin\nexecution_agent: false\n")
            mock_dir.return_value = agents_dir

            executor = create_executor(task)
            assert isinstance(executor, PluginExecutor)
            assert executor._command == "echo hello"
            assert executor._delegate is not None

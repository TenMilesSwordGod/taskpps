from __future__ import annotations

from unittest.mock import patch

import pytest

from taskpps.domain.pipeline import ResolvedTask
from taskpps.executors import create_executor
from taskpps.executors.local import LocalExecutor
from taskpps.executors.plugin import PluginExecutor


class TestPluginExecutor:
    def test_plugin_executor_has_command(self):
        executor = PluginExecutor('echo "hello"')
        assert executor._command == 'echo "hello"'


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

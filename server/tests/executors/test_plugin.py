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


_MOCK_ECHO_BODY = (
    "import json, sys\n"
    "req = json.loads(sys.stdin.readline())\n"
    "params = req.get('params', {})\n"
    "msg = params.get('message', '')\n"
    "sys.stdout.write(json.dumps({'jsonrpc':'2.0',"
    "'result':{'success':True,'stdout':'echo: '+msg,'stderr':'','exit_code':0},"
    "'id':1})+'\\n')\n"
    "sys.stdout.flush()\n"
)

_MOCK_FAIL_BODY = (
    "import json, sys\n"
    "sys.stdin.readline()\n"
    "sys.stdout.write(json.dumps({'jsonrpc':'2.0',"
    "'result':{'success':False,'stdout':'','stderr':'something went wrong','exit_code':1},"
    "'id':1})+'\\n')\n"
    "sys.stdout.flush()\n"
)

_MOCK_SLOW_BODY = (
    "import sys, time\n"
    "sys.stdin.readline()\n"
    "time.sleep(5)\n"
    "sys.stdout.write('{\"jsonrpc\":\"2.0\",\"result\":{\"success\":true},\"id\":1}\\n')\n"
    "sys.stdout.flush()\n"
)


class TestPluginExecutor:
    @pytest.mark.asyncio
    async def test_local_execution_success(self, tmp_path):
        binary = _make_mock_plugin(tmp_path, "echo_plugin", _MOCK_ECHO_BODY)

        executor = PluginExecutor(binary_path=binary, params={"message": "hello"})
        log_path = tmp_path / "output.log"
        result = await executor.execute(command="", env={}, log_path=log_path)

        assert result.exit_code == 0
        assert "echo: hello" in result.stdout

    @pytest.mark.asyncio
    async def test_local_execution_failure(self, tmp_path):
        binary = _make_mock_plugin(tmp_path, "fail_plugin", _MOCK_FAIL_BODY)

        executor = PluginExecutor(binary_path=binary, params={})
        log_path = tmp_path / "output.log"
        result = await executor.execute(command="", env={}, log_path=log_path)

        assert result.exit_code == 1
        assert "something went wrong" in result.stderr

    @pytest.mark.asyncio
    async def test_nonexistent_binary(self, tmp_path):
        binary = tmp_path / "nonexistent"
        executor = PluginExecutor(binary_path=binary, params={})
        log_path = tmp_path / "output.log"
        result = await executor.execute(command="", env={}, log_path=log_path)

        assert result.exit_code == -1
        assert "Failed to spawn plugin binary" in result.stderr

    @pytest.mark.asyncio
    async def test_timeout(self, tmp_path):
        binary = _make_mock_plugin(tmp_path, "slow_plugin", _MOCK_SLOW_BODY)

        executor = PluginExecutor(binary_path=binary, params={})
        log_path = tmp_path / "output.log"
        result = await executor.execute(command="", env={}, log_path=log_path, timeout=1)

        assert result.exit_code == -1
        assert "timed out" in result.stderr


class TestPluginExecutorFactory:
    def test_plugin_type_routes_to_plugin_executor(self, tmp_path):
        binary = tmp_path / "test_plugin"
        binary.write_text(f"#!{sys.executable}\nprint('ok')\n")
        binary.chmod(binary.stat().st_mode | stat.S_IEXEC)

        task = ResolvedTask(
            name="my_task",
            task_type="plugin",
            plugin="test_plugin",
            plugin_params={"key": "val"},
        )

        p_info = type("PInfo", (), {
            "name": "test_plugin",
            "type": "executor",
            "binary_path": binary,
            "status": "loaded",
        })

        mock_get_pc = type("MPC", (), {})()
        mock_get_pc.get_plugin = lambda name: p_info if name == "test_plugin" else None

        with patch("taskpps.services.plugin_center.get_plugin_center", return_value=mock_get_pc):
            executor = create_executor(task)
            assert isinstance(executor, PluginExecutor)

    def test_plugin_type_raises_when_not_found(self):
        task = ResolvedTask(
            name="my_task",
            task_type="plugin",
            plugin="unknown_plugin",
        )

        mock_get_pc = type("MPC", (), {})()
        mock_get_pc.get_plugin = lambda name: None

        with patch("taskpps.services.plugin_center.get_plugin_center", return_value=mock_get_pc):
            with pytest.raises(ValueError, match="not found"):
                create_executor(task)

    def test_plugin_type_falls_back_when_pc_none(self):
        task = ResolvedTask(
            name="my_task",
            task_type="plugin",
            plugin="test_plugin",
            plugin_params={"key": "val"},
        )

        with patch("taskpps.services.plugin_center.get_plugin_center", return_value=None):
            with pytest.raises(ValueError, match="not available"):
                create_executor(task)


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

    def test_git_takes_priority_over_plugin(self):
        from taskpps.schemas.pipeline import GitSpec, TaskYAML

        task = TaskYAML(
            name="my_task",
            git=GitSpec(repo="http://example.com/repo.git"),
            plugin="echo",
            params={"message": "hello"},
        )
        assert task.get_task_type() == "git"

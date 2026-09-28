"""Agent 执行环境（shell/env）在服务端执行链路的生效测试。

设计决策（为什么覆盖三类执行器）：
- shell/env 在网页上是一份配置，但实际执行分散在 Local/SSH/远程 Agent 三条路径，
  只测配置读写会出现"页面显示已保存、任务里没生效"的假保证。
- env 优先级固定为「agent 配置 < 本次执行 env」：本文件用同名 key 验证覆盖方向。
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from taskpps.domain.pipeline import ResolvedTask
from taskpps.executors import create_executor
from taskpps.executors.agent_executor import AgentExecutor
from taskpps.executors.ssh import SSHExecutor, build_remote_command
from taskpps.services.agent_exec_env import normalize_env, normalize_shell
from taskpps.services.agent_manager import AgentConnection


class TestNormalizeAgentExecEnv:
    """手工 YAML 的容错口径：坏类型不能让 /agents/all 500，也不能让执行器 TypeError。"""

    def test_env_coerces_scalars_to_str(self):
        # 布尔必须落成 shell 语义的小写 true/false：
        # `[ "$DEBUG" = "true" ]` 这类判断在 "True" 下会静默走 false 分支
        assert normalize_env({"PORT": 8080, "DEBUG": True, "VERBOSE": False, "NAME": "x"}) == {
            "PORT": "8080",
            "DEBUG": "true",
            "VERBOSE": "false",
            "NAME": "x",
        }

    def test_env_ignores_malformed_values(self):
        assert normalize_env(None) == {}
        assert normalize_env(["A=1"]) == {}
        assert normalize_env({"GOOD": "1", "nested": {"x": 1}, "nil": None}) == {"GOOD": "1"}

    def test_shell_trims_and_normalizes_none(self):
        assert normalize_shell(None) == ""
        assert normalize_shell(" /bin/zsh ") == "/bin/zsh"


class TestApplyAgentEnv:
    """agent 配置 env 与任务 env 的合并优先级（LocalExecutor 不会挂 agent 配置：
    create_executor 仅在 task.host 分支注入，无 host 的本地任务没有 agent 可读）。"""

    def test_agent_env_is_default_and_task_env_wins(self):
        executor = SSHExecutor(host="10.0.0.1")
        executor.agent_env = {"FOO": "agent", "BAR": "agent"}
        assert executor.apply_agent_env({"FOO": "task"}) == {"FOO": "task", "BAR": "agent"}

    def test_no_agent_env_returns_copy(self):
        executor = SSHExecutor(host="10.0.0.1")
        source = {"A": "1"}
        merged = executor.apply_agent_env(source)
        assert merged == source
        assert merged is not source


class TestSshRemoteCommand:
    def test_legacy_format_without_shell(self):
        cmd = build_remote_command("echo hi", {"K": "v"}, ".", "")
        assert "source /etc/profile" in cmd
        assert "export K=v" in cmd
        # 空 env 不能拼出 `&& &&` 这种语法错误
        assert "&&  &&" not in cmd
        assert "&&  &&" not in build_remote_command("echo hi", {}, ".", "")

    def test_with_shell_wraps_command(self):
        cmd = build_remote_command("echo 'a b'", {"K": "v v"}, "/tmp/x y", "/bin/zsh")
        assert "export K='v v'" in cmd
        assert "exec /bin/zsh -c" in cmd
        assert "cd '/tmp/x y'" in cmd

    def test_shell_quoting_is_safe(self):
        cmd = build_remote_command("echo \"it's\"", {}, ".", "/bin/bash")
        # 命令中的单引号必须被正确转义，不能逃逸出 -c 参数
        assert "exec /bin/bash -c" in cmd


class TestCreateExecutorAgentExecEnv:
    def test_attaches_shell_and_env_from_agent_yaml(self, tmp_path):
        agents_dir = tmp_path / "agents"
        agents_dir.mkdir()
        (agents_dir / "cfg.yaml").write_text(
            "id: cfg\n"
            "host: 10.0.0.9\n"
            "type: ssh-username-password\n"
            "execution_agent: false\n"
            "shell: /bin/zsh\n"
            "env:\n"
            "  FOO: bar\n"
            "  NUM: 7\n"
        )
        task = ResolvedTask(name="t", task_type="command", command="echo hi", host="cfg")
        executor = create_executor(task, str(tmp_path))
        assert isinstance(executor, SSHExecutor)
        assert executor.agent_shell == "/bin/zsh"
        assert executor.agent_env == {"FOO": "bar", "NUM": "7"}


class TestAgentExecutorAgentExecEnv:
    @pytest.fixture
    def mock_manager(self):
        mgr = MagicMock()
        mgr.is_connected = MagicMock(return_value=True)
        mgr.send_command = AsyncMock()
        mgr.cancel_command = AsyncMock()
        mgr.cleanup_command = MagicMock()
        mgr.create_pending = MagicMock()
        mgr.register_output_callback = MagicMock()
        mgr.acquire_agent = AsyncMock()
        mgr.acquire_global = AsyncMock()
        mgr.release_agent = MagicMock()
        mgr.release_global = MagicMock()
        mgr.promote_command_to_running = MagicMock()
        mgr.get_connection = MagicMock(return_value=None)
        return mgr

    @pytest.mark.asyncio
    async def test_sends_merged_env_and_shell_to_agent(self, tmp_path, mock_manager):
        fut = asyncio.get_event_loop().create_future()
        fut.set_result({"exit_code": 0, "signal_name": "", "error": ""})
        mock_manager.create_pending.return_value = fut

        executor = AgentExecutor("agent-1", mock_manager, {"id": "agent-1"})
        executor.agent_env = {"FOO": "agent", "BAR": "agent"}
        executor.agent_shell = "/bin/zsh"

        result = await executor.execute("echo hi", {"FOO": "task"}, tmp_path / "t.log", timeout=30)
        assert result.exit_code == 0
        mock_manager.send_command.assert_called_once_with(
            "agent-1",
            executor._command_id,
            "echo hi",
            {"FOO": "task", "BAR": "agent"},
            "",
            30,
            shell="/bin/zsh",
        )


class TestConnectionSendCommandShell:
    @pytest.mark.asyncio
    async def test_payload_contains_shell_only_when_configured(self):
        ws = AsyncMock()
        conn = AgentConnection("a1", ws)

        await conn.send_command("cid", "echo hi", {"A": "1"}, "/tmp", 5, shell="/bin/zsh")
        payload = ws.send_json.await_args.args[0]["data"]
        assert payload["shell"] == "/bin/zsh"
        assert payload["env"] == {"A": "1"}

        # 未配置 shell 时保持旧报文格式，兼容未升级的 agent
        ws.reset_mock()
        await conn.send_command("cid", "echo hi", {}, "", 5)
        assert "shell" not in ws.send_json.await_args.args[0]["data"]

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from taskpps.schemas.plugin_spec import DescribeRPCResponse
from taskpps.services.plugin_center import MAX_RESTARTS, PluginCenter, PluginInfo


def _describe_json(name, type, hooks=None, version="1.0.0", help_msg="test",
                   params_schema=None, config_schema=None):
    return DescribeRPCResponse.model_validate({
        "jsonrpc": "2.0",
        "result": {
            "name": name,
            "type": type,
            "version": version,
            "help_msg": help_msg,
            "hooks": hooks or [],
            "params_schema": params_schema or {},
            "config_schema": config_schema or {},
        },
        "id": 1,
    })


def _describe_bytes(name, type, **kwargs):
    return (_describe_json(name, type, **kwargs).model_dump_json() + "\n").encode()


def _execute_bytes(success=True, stdout="ok", stderr="", exit_code=0):
    return (json.dumps({
        "jsonrpc": "2.0",
        "result": {"success": success, "stdout": stdout, "stderr": stderr, "exit_code": exit_code},
        "id": 1,
    }) + "\n").encode()


class _QueueStreamReader:
    def __init__(self, *data_items):
        self._queue = asyncio.Queue()
        for item in data_items:
            self._queue.put_nowait(item)

    async def readline(self):
        return await self._queue.get()


class _MockProcess:
    def __init__(self, stdout_data_list=None, returncode=None, stdin_write_ok=True):
        if stdout_data_list:
            self.stdout = _QueueStreamReader(*stdout_data_list)
        else:
            self.stdout = _QueueStreamReader()
        self.stdin = AsyncMock() if stdin_write_ok else None
        self.stderr = _QueueStreamReader()
        self.returncode = returncode
        self._killed = False

    async def wait(self):
        return self.returncode if self.returncode is not None else 0

    def kill(self):
        self.returncode = -9

    def terminate(self):
        self.returncode = -15


class TestPluginCenterDescribe:
    @pytest.mark.asyncio
    @pytest.mark.zentao("TC-S1137", domain="server/plugin_center", priority="P1")
    async def test_describe_executor_plugin_parsed_correctly(self, tmp_project):
        pc = PluginCenter(tmp_project)
        mock_proc = _MockProcess(stdout_data_list=[_describe_bytes("git_plugin", "executor",
            version="2.0.0", help_msg="Git 操作插件",
            params_schema={"remote": {"type": "string", "required": True}},
        )])
        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            info = await pc._describe(mock_proc, Path("/fake/git_plugin"))
        assert info is not None
        assert info.name == "git_plugin"
        assert info.type == "executor"
        assert info.version == "2.0.0"
        assert info.help_msg == "Git 操作插件"
        assert info.params_schema == {"remote": {"type": "string", "required": True}}

    @pytest.mark.asyncio
    @pytest.mark.zentao("TC-S1137", domain="server/plugin_center", priority="P1")
    async def test_describe_hook_plugin_parsed_correctly(self, tmp_project):
        pc = PluginCenter(tmp_project)
        mock_proc = _MockProcess(stdout_data_list=[_describe_bytes("slack_notifier", "hook",
            hooks=["on_pipeline_end", "on_stage_complete"],
            config_schema={"webhook_url": {"type": "string", "required": True}},
        )])
        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            info = await pc._describe(mock_proc, Path("/fake/slack_notifier"))
        assert info is not None
        assert info.name == "slack_notifier"
        assert info.type == "hook"
        assert info.hooks == ["on_pipeline_end", "on_stage_complete"]
        assert info.config_schema == {"webhook_url": {"type": "string", "required": True}}

    @pytest.mark.asyncio
    @pytest.mark.zentao("TC-S1137", domain="server/plugin_center", priority="P2")
    async def test_describe_empty_hooks_and_schema(self, tmp_project):
        pc = PluginCenter(tmp_project)
        mock_proc = _MockProcess(stdout_data_list=[_describe_bytes("minimal", "executor")])
        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            info = await pc._describe(mock_proc, Path("/fake/minimal"))
        assert info is not None
        assert info.hooks == []
        assert info.params_schema == {}


class TestPluginCenterBinaryNotFound:
    @pytest.mark.asyncio
    @pytest.mark.zentao("TC-S1138", domain="server/plugin_center", priority="P1")
    async def test_binary_not_found_logs_error_and_skips(self, tmp_project):
        pc = PluginCenter(tmp_project)
        bad_path = Path("/nonexistent/binary")
        with patch("asyncio.create_subprocess_exec", side_effect=FileNotFoundError("not found")):
            await pc._load_plugin(bad_path)
        assert bad_path.name not in pc._plugins


class TestPluginCenterInvalidJSON:
    @pytest.mark.asyncio
    @pytest.mark.zentao("TC-S1139", domain="server/plugin_center", priority="P1")
    async def test_invalid_json_skips_and_logs_error(self, tmp_project, caplog):
        pc = PluginCenter(tmp_project)
        mock_proc = _MockProcess(stdout_data_list=[b"this is not valid json\n"])
        with patch("asyncio.create_subprocess_exec", return_value=mock_proc), caplog.at_level(logging.ERROR):
            info = await pc._describe(mock_proc, Path("/fake/badjson"))
        assert info is None
        assert any("Failed to parse describe response" in r.message for r in caplog.records)


class TestPluginCenterUnknownType:
    @pytest.mark.asyncio
    @pytest.mark.zentao("TC-S1140", domain="server/plugin_center", priority="P2")
    async def test_unknown_type_skips_and_warns(self, tmp_project, caplog):
        pc = PluginCenter(tmp_project)
        mock_proc = _MockProcess(stdout_data_list=[_describe_bytes("weird_plugin", "invalid")])
        with patch("asyncio.create_subprocess_exec", return_value=mock_proc), caplog.at_level(logging.WARNING):
            info = await pc._describe(mock_proc, Path("/fake/weird"))
        assert info is None
        assert any("unknown type" in r.message for r in caplog.records)

    @pytest.mark.asyncio
    @pytest.mark.zentao("TC-S1140", domain="server/plugin_center", priority="P2")
    async def test_type_none_skips_and_warns(self, tmp_project, caplog):
        pc = PluginCenter(tmp_project)
        raw = _describe_json("weird2", "executor")
        raw.result.type = None
        mock_proc = _MockProcess(stdout_data_list=[(raw.model_dump_json() + "\n").encode()])
        with patch("asyncio.create_subprocess_exec", return_value=mock_proc), caplog.at_level(logging.WARNING):
            info = await pc._describe(mock_proc, Path("/fake/weird2"))
        assert info is None


class TestPluginCenterExecute:
    @pytest.mark.asyncio
    @pytest.mark.zentao("TC-S1141", domain="server/plugin_center", priority="P1")
    async def test_execute_success(self, tmp_project):
        pc = PluginCenter(tmp_project)
        mock_proc = _MockProcess(
            stdout_data_list=[
                _describe_bytes("git_plugin", "executor", version="1.0.0"),
                _execute_bytes(True, "clone ok"),
            ],
            returncode=None,
        )
        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            await pc._load_plugin(Path("/fake/git_plugin"))
        result = await pc.execute("git_plugin", {"remote": "url", "branch": "main"})
        assert result.success is True
        assert result.stdout == "clone ok"

    @pytest.mark.asyncio
    @pytest.mark.zentao("TC-S1141", domain="server/plugin_center", priority="P1")
    async def test_execute_failure(self, tmp_project):
        pc = PluginCenter(tmp_project)
        mock_proc = _MockProcess(
            stdout_data_list=[
                _describe_bytes("fail_plugin", "executor", version="1.0.0"),
                _execute_bytes(False, "", "something wrong", 1),
            ],
            returncode=None,
        )
        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            await pc._load_plugin(Path("/fake/fail_plugin"))
        result = await pc.execute("fail_plugin", {})
        assert result.success is False
        assert result.stderr == "something wrong"
        assert result.exit_code == 1

    @pytest.mark.asyncio
    @pytest.mark.zentao("TC-S1141", domain="server/plugin_center", priority="P1")
    async def test_execute_nonexistent_plugin_raises(self, tmp_project):
        pc = PluginCenter(tmp_project)
        with pytest.raises(ValueError, match="not found"):
            await pc.execute("nonexistent", {})

    @pytest.mark.asyncio
    @pytest.mark.zentao("TC-S1141", domain="server/plugin_center", priority="P1")
    async def test_execute_crashed_plugin_raises(self, tmp_project):
        pc = PluginCenter(tmp_project)
        info = PluginInfo(name="crashed_plugin", type="executor", status="crashed")
        pc._plugins["crashed_plugin"] = info
        with pytest.raises(RuntimeError, match="crashed"):
            await pc.execute("crashed_plugin", {})

    @pytest.mark.asyncio
    @pytest.mark.zentao("TC-S1141", domain="server/plugin_center", priority="P2")
    async def test_execute_not_executor_type_raises(self, tmp_project):
        pc = PluginCenter(tmp_project)
        info = PluginInfo(name="hook_only", type="hook")
        pc._plugins["hook_only"] = info
        with pytest.raises(ValueError, match="not found"):
            await pc.execute("hook_only", {})


class TestPluginCenterHookDispatch:
    @pytest.mark.asyncio
    @pytest.mark.zentao("TC-S1142", domain="server/plugin_center", priority="P1")
    async def test_hook_registered_in_hook_map(self, tmp_project):
        pc = PluginCenter(tmp_project)
        mock_proc = _MockProcess(
            stdout_data_list=[_describe_bytes("notifier", "hook", hooks=["on_pipeline_end", "on_stage_complete"])],
            returncode=None,
        )
        with (
            patch("asyncio.create_subprocess_exec", return_value=mock_proc),
            patch.object(pc, "_monitor_process", return_value=None),
        ):
            await pc._load_plugin(Path("/fake/notifier"))
        assert "notifier" in pc._plugins
        assert pc._plugins["notifier"].type == "hook"
        assert pc._hook_map.get("on_pipeline_end") == ["notifier"]
        assert pc._hook_map.get("on_stage_complete") == ["notifier"]

    @pytest.mark.asyncio
    @pytest.mark.zentao("TC-S1142", domain="server/plugin_center", priority="P1")
    async def test_dispatch_sends_jsonrpc_to_plugin(self, tmp_project):
        pc = PluginCenter(tmp_project)
        mock_proc = _MockProcess(
            stdout_data_list=[_describe_bytes("notifier", "hook", hooks=["on_pipeline_end"])],
            returncode=None,
        )
        with (
            patch("asyncio.create_subprocess_exec", return_value=mock_proc),
            patch.object(pc, "_monitor_process", return_value=None),
        ):
            await pc._load_plugin(Path("/fake/notifier"))
        mock_proc.stdin.write.reset_mock()
        await pc.dispatch("on_pipeline_end", {"pipeline_id": "123"})
        mock_proc.stdin.write.assert_called_once()
        written = mock_proc.stdin.write.call_args[0][0].decode()
        rpc = json.loads(written.strip())
        assert rpc["method"] == "on_pipeline_end"
        assert rpc["params"] == {"pipeline_id": "123"}

    @pytest.mark.asyncio
    @pytest.mark.zentao("TC-S1142", domain="server/plugin_center", priority="P2")
    async def test_dispatch_nonexistent_hook_noop(self, tmp_project):
        pc = PluginCenter(tmp_project)
        await pc.dispatch("nonexistent_hook", {})

    @pytest.mark.asyncio
    @pytest.mark.zentao("TC-S1142", domain="server/plugin_center", priority="P2")
    async def test_dispatch_skips_crashed_plugin(self, tmp_project):
        pc = PluginCenter(tmp_project)
        info = PluginInfo(name="crashed_hook", type="hook", hooks=["on_pipeline_end"], status="crashed")
        pc._plugins["crashed_hook"] = info
        pc._hook_map["on_pipeline_end"] = ["crashed_hook"]
        await pc.dispatch("on_pipeline_end", {})


class TestPluginCenterMultiplePlugins:
    @pytest.mark.asyncio
    @pytest.mark.zentao("TC-S1143", domain="server/plugin_center", priority="P2")
    async def test_multiple_plugins_load_independently(self, tmp_project):
        pc = PluginCenter(tmp_project)

        desc_a = _describe_bytes("plugin_a", "executor", version="1.0.0")
        desc_b = _describe_bytes("plugin_b", "hook", hooks=["on_pipeline_end"], version="2.0.0")
        desc_c = _describe_bytes("plugin_c", "executor", version="3.0.0")

        call_count = 0

        def _spawn_side_effect(*args, **kwargs):
            nonlocal call_count
            data = [desc_a, desc_b, desc_c][call_count]
            call_count += 1
            return _MockProcess(stdout_data_list=[data], returncode=None)

        with (
            patch("asyncio.create_subprocess_exec", side_effect=_spawn_side_effect),
            patch.object(pc, "_monitor_process", return_value=None),
        ):
            await pc._load_plugin(Path("/fake/plugin_a"))
            await pc._load_plugin(Path("/fake/plugin_b"))
            await pc._load_plugin(Path("/fake/plugin_c"))

        assert len(pc._plugins) == 3
        assert pc._plugins["plugin_a"].version == "1.0.0"
        assert pc._plugins["plugin_b"].version == "2.0.0"
        assert pc._plugins["plugin_c"].version == "3.0.0"
        assert "plugin_a" in pc._executor_map
        assert "plugin_c" in pc._executor_map
        assert "on_pipeline_end" in pc._hook_map

    @pytest.mark.asyncio
    @pytest.mark.zentao("TC-S1143", domain="server/plugin_center", priority="P2")
    async def test_one_plugin_failure_does_not_block_others(self, tmp_project, caplog):
        pc = PluginCenter(tmp_project)

        call_count = 0

        def _spawn_side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise FileNotFoundError("bad binary")
            return _MockProcess(stdout_data_list=[_describe_bytes("good_plugin", "executor", version="1.0.0")], returncode=None)

        with (
            patch("asyncio.create_subprocess_exec", side_effect=_spawn_side_effect),
            patch.object(pc, "_monitor_process", return_value=None),
        ):
            await pc._load_plugin(Path("/fake/bad_plugin"))
            await pc._load_plugin(Path("/fake/good_plugin"))

        assert "bad_plugin" not in pc._plugins
        assert "good_plugin" in pc._plugins


class TestPluginCenterCrashRestart:
    @pytest.mark.asyncio
    @pytest.mark.zentao("TC-S1144", domain="server/plugin_center", priority="P1")
    async def test_crash_restart_works_within_limit(self, tmp_project):
        pc = PluginCenter(tmp_project)
        desc_bytes = _describe_bytes("restartable", "executor", version="1.0.0")

        mock_proc1 = _MockProcess(stdout_data_list=[desc_bytes], returncode=None)
        with patch("asyncio.create_subprocess_exec", return_value=mock_proc1):
            await pc._load_plugin(Path("/fake/restartable"))
        assert "restartable" in pc._plugins
        assert pc._plugins["restartable"].status == "loaded"

        pc._restart_counts["restartable"] = 0
        mock_proc2 = _MockProcess(stdout_data_list=[desc_bytes], returncode=None)
        with patch("asyncio.create_subprocess_exec", return_value=mock_proc2):
            await pc._monitor_process("restartable")
        assert pc._plugins["restartable"].status == "loaded"

    @pytest.mark.asyncio
    @pytest.mark.zentao("TC-S1144", domain="server/plugin_center", priority="P1")
    async def test_crash_exceeds_max_restarts_marks_crashed(self, tmp_project, caplog):
        pc = PluginCenter(tmp_project)
        info = PluginInfo(
            name="unstable", type="executor", version="1.0.0",
            binary_path=Path("/fake/unstable"),
        )
        pc._plugins["unstable"] = info
        pc._restart_counts["unstable"] = MAX_RESTARTS
        mock_proc = _MockProcess(returncode=0)
        pc._processes["unstable"] = mock_proc
        with caplog.at_level(logging.ERROR), patch("asyncio.create_subprocess_exec") as mock_spawn:
            await pc._monitor_process("unstable")
        assert pc._plugins["unstable"].status == "crashed"
        assert "unstable" not in pc._processes
        mock_spawn.assert_not_called()
        assert any("crashed" in r.message for r in caplog.records)


class TestPluginCenterDualDirectory:
    @pytest.mark.asyncio
    @pytest.mark.zentao("TC-S1145", domain="server/plugin_center", priority="P2")
    async def test_both_directories_scanned(self, tmp_project):
        official_dir = tmp_project / "official_plugins" / "git"
        official_dir.mkdir(parents=True)
        official_bin = official_dir / "git_plugin"
        official_bin.touch()
        official_bin.chmod(0o755)

        plugins_dir = tmp_project / "plugins" / "slack"
        plugins_dir.mkdir(parents=True)
        plugins_bin = plugins_dir / "slack_notifier"
        plugins_bin.touch()
        plugins_bin.chmod(0o755)

        pc = PluginCenter(tmp_project)

        responses = {
            str(official_bin.resolve()): _describe_bytes("git_plugin", "executor", version="1.0.0"),
            str(plugins_bin.resolve()): _describe_bytes("slack_notifier", "hook", hooks=["on_pipeline_end"], version="1.0.0"),
        }

        async def _spawn(*args, **kwargs):
            bin_path = str(Path(args[0]).resolve())
            data = responses.get(bin_path, b"{}")
            return _MockProcess(stdout_data_list=[data], returncode=None)

        with (
            patch("asyncio.create_subprocess_exec", side_effect=_spawn),
            patch.object(pc, "_monitor_process", return_value=None),
        ):
            await pc.discover_and_load()

        assert "git_plugin" in pc._plugins
        assert "slack_notifier" in pc._plugins
        assert "git_plugin" in pc._executor_map
        assert "on_pipeline_end" in pc._hook_map

    @pytest.mark.asyncio
    @pytest.mark.zentao("TC-S1145", domain="server/plugin_center", priority="P2")
    async def test_plugins_dir_not_exists_degraded(self, tmp_project):
        official_dir = tmp_project / "official_plugins" / "rsync"
        official_dir.mkdir(parents=True)
        official_bin = official_dir / "rsync_plugin"
        official_bin.touch()
        official_bin.chmod(0o755)

        pc = PluginCenter(tmp_project)
        mock_proc = _MockProcess(stdout_data_list=[_describe_bytes("rsync_plugin", "executor", version="1.0.0")], returncode=None)
        with (
            patch("asyncio.create_subprocess_exec", return_value=mock_proc),
            patch.object(pc, "_monitor_process", return_value=None),
        ):
            await pc.discover_and_load()
        assert "rsync_plugin" in pc._plugins

    @pytest.mark.asyncio
    @pytest.mark.zentao("TC-S1145", domain="server/plugin_center", priority="P2")
    async def test_empty_both_directories_no_plugins(self, tmp_project):
        pc = PluginCenter(tmp_project)
        await pc.discover_and_load()
        assert len(pc._plugins) == 0


class TestPluginCenterAPI:
    @pytest.mark.asyncio
    @pytest.mark.zentao("TC-S1146", domain="server/plugin_center", priority="P1")
    async def test_list_plugins_returns_status_and_help_msg(self, tmp_project):
        pc = PluginCenter(tmp_project)
        info = PluginInfo(name="test_plugin", type="executor", version="1.0.0", help_msg="## 测试", status="loaded")
        pc._plugins["test_plugin"] = info
        plugins = pc.list_plugins()
        assert len(plugins) == 1
        assert plugins[0].name == "test_plugin"
        assert plugins[0].type == "executor"
        assert plugins[0].version == "1.0.0"
        assert plugins[0].help_msg == "## 测试"
        assert plugins[0].status == "loaded"

    @pytest.mark.asyncio
    @pytest.mark.zentao("TC-S1146", domain="server/plugin_center", priority="P1")
    async def test_list_plugins_empty(self, tmp_project):
        pc = PluginCenter(tmp_project)
        plugins = pc.list_plugins()
        assert plugins == []

    @pytest.mark.asyncio
    @pytest.mark.zentao("TC-S1146", domain="server/plugin_center", priority="P2")
    async def test_get_plugin_by_name(self, tmp_project):
        pc = PluginCenter(tmp_project)
        info = PluginInfo(name="my_plugin", type="hook", version="2.0.0", hooks=["on_pipeline_start"], status="loaded")
        pc._plugins["my_plugin"] = info
        found = pc.get_plugin("my_plugin")
        assert found is not None
        assert found.name == "my_plugin"
        assert found.hooks == ["on_pipeline_start"]

    @pytest.mark.asyncio
    @pytest.mark.zentao("TC-S1146", domain="server/plugin_center", priority="P2")
    async def test_get_plugin_nonexistent(self, tmp_project):
        pc = PluginCenter(tmp_project)
        assert pc.get_plugin("nonexistent") is None


class TestPluginCenterTimeout:
    @pytest.mark.asyncio
    @pytest.mark.zentao("TC-S1147", domain="server/plugin_center", priority="P1")
    async def test_execute_timeout_returns_error(self, tmp_project, caplog):
        pc = PluginCenter(tmp_project)
        mock_proc = _MockProcess(
            stdout_data_list=[_describe_bytes("slow_plugin", "executor", version="1.0.0")],
            returncode=None,
        )
        with (
            patch("asyncio.create_subprocess_exec", return_value=mock_proc),
            patch.object(pc, "_monitor_process", return_value=None),
        ):
            await pc._load_plugin(Path("/fake/slow_plugin"))

        async def slow_readline():
            await asyncio.sleep(999)
            return b""

        mock_proc.stdout.readline = slow_readline
        with caplog.at_level(logging.ERROR):
            result = await pc.execute("slow_plugin", {}, timeout=0.01)
        assert result.success is False
        assert "timed out" in result.stderr
        assert any("timed out" in r.message for r in caplog.records)


class TestPluginCenterBoundary:
    @pytest.mark.asyncio
    @pytest.mark.zentao("TC-S1137", domain="server/plugin_center", priority="P2")
    async def test_describe_response_eof_returns_none(self, tmp_project):
        pc = PluginCenter(tmp_project)
        mock_proc = _MockProcess(stdout_data_list=[b""])
        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            info = await pc._describe(mock_proc, Path("/fake/eof"))
        assert info is None

    @pytest.mark.asyncio
    @pytest.mark.zentao("TC-S1138", domain="server/plugin_center", priority="P2")
    async def test_oserror_during_spawn_logs_and_skips(self, tmp_project, caplog):
        pc = PluginCenter(tmp_project)
        with (
            patch("asyncio.create_subprocess_exec", side_effect=OSError("permission denied")),
            caplog.at_level(logging.ERROR),
        ):
            await pc._load_plugin(Path("/fake/noperm"))
        assert any("Failed to spawn" in r.message for r in caplog.records)

    @pytest.mark.asyncio
    @pytest.mark.zentao("TC-S1139", domain="server/plugin_center", priority="P2")
    async def test_invalid_rpc_structure_skips_and_logs(self, tmp_project, caplog):
        pc = PluginCenter(tmp_project)
        bad_rpc = b'{"jsonrpc":"2.0","result":{"name":"no_type"},"id":1}\n'
        mock_proc = _MockProcess(stdout_data_list=[bad_rpc])
        with patch("asyncio.create_subprocess_exec", return_value=mock_proc), caplog.at_level(logging.ERROR):
            info = await pc._describe(mock_proc, Path("/fake/bad_rpc"))
        assert info is None


class TestPluginCenterShutdown:
    @pytest.mark.asyncio
    @pytest.mark.zentao("TC-S1147", domain="server/plugin_center", priority="P2")
    async def test_shutdown_cleans_up_plugins(self, tmp_project):
        pc = PluginCenter(tmp_project)
        mock_proc = _MockProcess(stdout_data_list=[_describe_bytes("plugin_x", "executor", version="1.0.0")])
        with (
            patch("asyncio.create_subprocess_exec", return_value=mock_proc),
            patch.object(pc, "_monitor_process", return_value=None),
        ):
            await pc._load_plugin(Path("/fake/plugin_x"))
        assert len(pc._plugins) == 1
        await pc.shutdown()
        assert len(pc._plugins) == 0
        assert len(pc._processes) == 0
        assert len(pc._hook_map) == 0
        assert len(pc._executor_map) == 0


class TestPluginCenterDescribeHang:
    @pytest.mark.asyncio
    @pytest.mark.zentao("TC-S1137", domain="server/plugin_center", priority="P2")
    async def test_describe_timeout_hang_returns_none(self, tmp_project, caplog):
        from taskpps.services import plugin_center as pc_mod

        pc = PluginCenter(tmp_project)
        mock_proc = _MockProcess()

        async def hang_readline():
            await asyncio.sleep(60)
            return b""
        mock_proc.stdout.readline = hang_readline

        with (
            caplog.at_level(logging.ERROR),
            patch.object(pc_mod, "DESCRIBE_TIMEOUT", 0.01),
        ):
            info = await pc._describe(mock_proc, Path("/fake/hang"))
        assert info is None
        assert any("Timeout" in r.message for r in caplog.records)


class TestPluginCenterConcurrent:
    @pytest.mark.asyncio
    @pytest.mark.zentao("TC-S1141", domain="server/plugin_center", priority="P2")
    async def test_concurrent_execute_independent_responses(self, tmp_project):
        pc = PluginCenter(tmp_project)
        desc = _describe_bytes("concurrent_plugin", "executor", version="1.0.0")
        resp1 = _execute_bytes(True, "result_a", "", 0)
        resp2 = _execute_bytes(True, "result_b", "", 0)

        mock_proc = _MockProcess(
            stdout_data_list=[desc, resp1, resp2],
            returncode=None,
        )
        with (
            patch("asyncio.create_subprocess_exec", return_value=mock_proc),
            patch.object(pc, "_monitor_process", return_value=None),
        ):
            await pc._load_plugin(Path("/fake/concurrent_plugin"))

        async def call_execute(params):
            return await pc.execute("concurrent_plugin", params)

        results = await asyncio.gather(
            call_execute({"i": "a"}),
            call_execute({"i": "b"}),
        )
        assert len(results) == 2
        stdout_values = {r.stdout for r in results}
        assert stdout_values == {"result_a", "result_b"}

    @pytest.mark.asyncio
    @pytest.mark.zentao("TC-S1141", domain="server/plugin_center", priority="P2")
    async def test_concurrent_execute_multiple_requests(self, tmp_project):
        pc = PluginCenter(tmp_project)
        desc = _describe_bytes("multi_plugin", "executor", version="1.0.0")
        responses = [_execute_bytes(True, f"result_{i}", "", 0) for i in range(5)]

        mock_proc = _MockProcess(
            stdout_data_list=[desc, *responses],
            returncode=None,
        )
        with (
            patch("asyncio.create_subprocess_exec", return_value=mock_proc),
            patch.object(pc, "_monitor_process", return_value=None),
        ):
            await pc._load_plugin(Path("/fake/multi_plugin"))

        tasks = [pc.execute("multi_plugin", {"i": str(n)}) for n in range(5)]
        results = await asyncio.gather(*tasks)
        assert len(results) == 5
        assert all(r.success for r in results)

    @pytest.mark.asyncio
    @pytest.mark.zentao("TC-S1142", domain="server/plugin_center", priority="P2")
    async def test_concurrent_dispatch_multiple_hooks(self, tmp_project):
        pc = PluginCenter(tmp_project)
        desc = _describe_bytes("multi_hook", "hook", hooks=["h1", "h2", "h3"], version="1.0.0")

        mock_proc = _MockProcess(stdout_data_list=[desc], returncode=None)
        with (
            patch("asyncio.create_subprocess_exec", return_value=mock_proc),
            patch.object(pc, "_monitor_process", return_value=None),
        ):
            await pc._load_plugin(Path("/fake/multi_hook"))

        await asyncio.gather(
            pc.dispatch("h1", {"x": 1}),
            pc.dispatch("h2", {"x": 2}),
            pc.dispatch("h3", {"x": 3}),
        )
        # describe writes 1 + 3 dispatches = 4 writes total
        assert mock_proc.stdin.write.call_count >= 3


class TestPluginCenterShutdownRace:
    @pytest.mark.asyncio
    @pytest.mark.zentao("TC-S1147", domain="server/plugin_center", priority="P2")
    async def test_shutdown_during_pending_execute(self, tmp_project):
        pc = PluginCenter(tmp_project)
        desc = _describe_bytes("slow_exec", "executor", version="1.0.0")

        mock_proc = _MockProcess(stdout_data_list=[desc], returncode=None)
        with (
            patch("asyncio.create_subprocess_exec", return_value=mock_proc),
            patch.object(pc, "_monitor_process", return_value=None),
        ):
            await pc._load_plugin(Path("/fake/slow_exec"))

        async def blocked_execute():
            try:
                await pc.execute("slow_exec", {}, timeout=0.01)
            except Exception:
                pass

        exec_task = asyncio.create_task(blocked_execute())
        await asyncio.sleep(0)
        await pc.shutdown()

        try:
            await asyncio.wait_for(exec_task, timeout=1)
        except asyncio.TimeoutError:
            exec_task.cancel()

        assert len(pc._plugins) == 0
        assert len(pc._processes) == 0

    @pytest.mark.asyncio
    @pytest.mark.zentao("TC-S1147", domain="server/plugin_center", priority="P2")
    async def test_shutdown_kills_unresponsive_process(self, tmp_project):
        pc = PluginCenter(tmp_project)
        mock_proc = _MockProcess(
            stdout_data_list=[_describe_bytes("stuck_plugin", "executor", version="1.0.0")],
            returncode=None,
        )
        with (
            patch("asyncio.create_subprocess_exec", return_value=mock_proc),
            patch.object(pc, "_monitor_process", return_value=None),
        ):
            await pc._load_plugin(Path("/fake/stuck_plugin"))

        assert pc._plugins["stuck_plugin"].status == "loaded"
        await pc.shutdown()
        assert len(pc._plugins) == 0
        assert len(pc._processes) == 0


class TestPluginCenterStderr:
    @pytest.mark.asyncio
    @pytest.mark.zentao("TC-S1137", domain="server/plugin_center", priority="P2")
    async def test_stderr_is_available_in_process(self, tmp_project):
        pc = PluginCenter(tmp_project)
        mock_proc = _MockProcess(
            stdout_data_list=[_describe_bytes("noisy_plugin", "executor", version="1.0.0")],
            returncode=None,
        )

        mock_proc.stderr = _QueueStreamReader(b"WARNING: deprecated config\n", b"INFO: started\n")

        with (
            patch("asyncio.create_subprocess_exec", return_value=mock_proc),
            patch.object(pc, "_monitor_process", return_value=None),
        ):
            await pc._load_plugin(Path("/fake/noisy_plugin"))

        assert "noisy_plugin" in pc._plugins
        stderr_line1 = await mock_proc.stderr.readline()
        stderr_line2 = await mock_proc.stderr.readline()
        assert b"WARNING" in stderr_line1
        assert b"INFO" in stderr_line2


class TestPluginCenterRealBinary:
    @pytest.mark.asyncio
    @pytest.mark.zentao("TC-S1141", domain="server/plugin_center", priority="P1")
    async def test_real_git_plugin_describe_and_execute(self, tmp_project):
        import sys

        git_plugin_path = tmp_project / "official_plugins" / "git" / "git_plugin.py"
        if not git_plugin_path.parent.exists():
            git_plugin_path.parent.mkdir(parents=True)
        import sys as _sys
        git_plugin_path.write_text(
            f"#!{_sys.executable}\n"
            "import json, sys\n"
            "def main():\n"
            " for line in sys.stdin:\n"
            "  line = line.strip()\n"
            "  if not line: continue\n"
            "  try: req = json.loads(line)\n"
            "  except: continue\n"
            "  m = req.get('method', ''); rid = req.get('id', 1)\n"
            "  if m == 'describe':\n"
            "   sys.stdout.write(json.dumps({'jsonrpc': '2.0',"
            "    'result': {'name': 'git_e2e', 'type': 'executor', 'version': '1.2.3',"
            "     'help_msg': 'E2E Git Plugin', 'hooks': [], 'params_schema': {}, 'config_schema': {}},"
            "    'id': rid}) + '\\n')\n"
            "   sys.stdout.flush()\n"
            "  elif m == 'execute':\n"
            "   p = req.get('params', {})\n"
            "   sys.stdout.write(json.dumps({'jsonrpc': '2.0',"
            "    'result': {'success': True, 'stdout': f\"git done {p}\", 'stderr': '', 'exit_code': 0},"
            "    'id': rid}) + '\\n')\n"
            "   sys.stdout.flush()\n"
            "  elif m == 'on_shutdown': break\n"
            " sys.exit(0)\n"
            "if __name__ == '__main__': main()\n"
        )
        git_plugin_path.chmod(0o755)

        pc = PluginCenter(tmp_project)
        await pc._load_plugin(git_plugin_path)

        assert "git_e2e" in pc._plugins
        info = pc._plugins["git_e2e"]
        assert info.name == "git_e2e"
        assert info.type == "executor"
        assert info.version == "1.2.3"
        assert info.help_msg == "E2E Git Plugin"
        assert info.status == "loaded"

        result = await pc.execute("git_e2e", {"action": "clone", "remote": "https://example.com/repo.git"})
        assert result.success is True
        assert "git done" in result.stdout
        assert "clone" in result.stdout

        await pc.shutdown()

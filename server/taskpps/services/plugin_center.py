from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from taskpps.schemas.plugin_spec import (
    DescribeRPCResponse,
    ExecuteResult,
    ExecuteRPCResponse,
)

logger = logging.getLogger(__name__)

MAX_RESTARTS = 3
DESCRIBE_TIMEOUT = 10
EXECUTE_DEFAULT_TIMEOUT = 3600

_plugin_center: PluginCenter | None = None


def get_plugin_center() -> PluginCenter | None:
    return _plugin_center


def set_plugin_center(pc: PluginCenter) -> None:
    global _plugin_center
    _plugin_center = pc


@dataclass
class PluginInfo:
    name: str
    type: str
    version: str = "0.0.0"
    help_msg: str = ""
    binary_path: Path | None = None
    hooks: list[str] = field(default_factory=list)
    params_schema: dict[str, Any] = field(default_factory=dict)
    config_schema: dict[str, Any] = field(default_factory=dict)
    status: str = "loaded"


class PluginCenter:
    def __init__(self, project_root: Path):
        self._project_root = project_root
        self._plugins: dict[str, PluginInfo] = {}
        self._hook_map: dict[str, list[str]] = {}
        self._executor_map: dict[str, str] = {}
        self._processes: dict[str, asyncio.subprocess.Process] = {}
        self._restart_counts: dict[str, int] = {}
        self._monitor_tasks: dict[str, asyncio.Task] = {}

    async def discover_and_load(self) -> None:
        official_dir = self._project_root / "official_plugins"
        plugins_dir = self._project_root / "plugins"

        discovered: set[str] = set()

        for binary_path in self._scan_plugins_dir(official_dir):
            key = str(binary_path.resolve())
            if key not in discovered:
                discovered.add(key)
                await self._load_plugin(binary_path)

        for binary_path in self._scan_plugins_dir(plugins_dir):
            key = str(binary_path.resolve())
            if key not in discovered:
                discovered.add(key)
                await self._load_plugin(binary_path)

    def _scan_plugins_dir(self, dir_path: Path) -> list[Path]:
        if not dir_path.exists() or not dir_path.is_dir():
            return []
        binaries: list[Path] = []
        for entry in sorted(dir_path.iterdir()):
            if entry.is_dir():
                py_file = entry / "plugin.py"
                if py_file.is_file():
                    binaries.append(py_file)
                    continue
                found = False
                for f in sorted(entry.iterdir()):
                    if self._is_plugin_binary(f):
                        binaries.append(f)
                        found = True
                        break
                if not found:
                    for f in sorted(entry.iterdir()):
                        if f.is_file() and not f.name.startswith(".") and not f.name.startswith("_"):
                            binaries.append(f)
                            break
            elif self._is_plugin_binary(entry) or (entry.name == "plugin.py" and entry.is_file()):
                binaries.append(entry)
        return binaries

    def _is_plugin_binary(self, path: Path) -> bool:
        if not path.is_file():
            return False
        if path.name.startswith("_") or path.name.startswith("."):
            return False
        if path.suffix == ".pyc":
            return False
        if path.name == "plugin.py":
            return False
        return os.access(path, os.X_OK)

    async def _load_python_plugin(self, plugin_py: Path) -> None:
        import importlib.util

        logger.info("Loading Python plugin: %s", plugin_py)
        try:
            spec = importlib.util.spec_from_file_location(
                f"taskpps_plugin_{plugin_py.parent.name}", str(plugin_py)
            )
            if spec is None or spec.loader is None:
                logger.error("Failed to load plugin spec: %s", plugin_py)
                return
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
        except Exception as e:
            logger.error("Failed to load Python plugin %s: %s", plugin_py, e)
            return

        plugin_cls = None
        for attr_name in dir(module):
            attr = getattr(module, attr_name)
            if (
                isinstance(attr, type)
                and attr.__module__ == module.__name__
                and hasattr(attr, "type")
                and hasattr(attr, "params_schema")
            ):
                plugin_cls = attr
                break

        if plugin_cls is None:
            logger.error("No plugin class found in %s", plugin_py)
            return

        name = plugin_py.parent.name
        p_type = getattr(plugin_cls, "type", "executor")
        version = getattr(plugin_cls, "version", "0.0.0")
        help_msg = (plugin_cls.__doc__ or "").strip()
        params_schema = getattr(plugin_cls, "params_schema", {})
        hooks = getattr(plugin_cls, "hooks", [])

        if p_type not in ("hook", "executor"):
            logger.warning("Plugin %s: unknown type '%s', skipping", name, p_type)
            return

        plugin_info = PluginInfo(
            name=name,
            type=p_type,
            version=version,
            help_msg=help_msg,
            binary_path=plugin_py,
            hooks=hooks,
            params_schema=params_schema,
        )
        self._plugins[plugin_info.name] = plugin_info
        self._register_python_info(plugin_info)
        logger.info("Registered Python plugin: %s (type=%s)", name, p_type)

    def _register_python_info(self, plugin_info: PluginInfo) -> None:
        if plugin_info.type == "hook":
            for hook in plugin_info.hooks:
                self._hook_map.setdefault(hook, []).append(plugin_info.name)
        elif plugin_info.type == "executor":
            self._executor_map[plugin_info.name] = plugin_info.name

    async def _load_plugin(self, binary_path: Path) -> None:
        if binary_path.name == "plugin.py":
            await self._load_python_plugin(binary_path)
            return

        logger.info("Loading plugin binary: %s", binary_path)
        try:
            proc = await asyncio.create_subprocess_exec(
                str(binary_path),
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
        except OSError as e:
            logger.error("Failed to spawn plugin binary %s: %s", binary_path, e)
            return

        plugin_info = await self._describe(proc, binary_path)
        if plugin_info is None:
            with contextlib.suppress(ProcessLookupError):
                proc.kill()
            await proc.wait()
            return

        self._register(plugin_info, proc)

    async def _describe(
        self, proc: asyncio.subprocess.Process, binary_path: Path
    ) -> PluginInfo | None:
        request = json.dumps({"jsonrpc": "2.0", "method": "describe", "id": 1})
        try:
            if proc.stdin is None:
                logger.error("Plugin %s: stdin is None", binary_path)
                return None
            proc.stdin.write((request + "\n").encode())
            await proc.stdin.drain()
        except (BrokenPipeError, ConnectionResetError, OSError) as e:
            logger.error("Failed to send describe request to %s: %s", binary_path, e)
            return None

        try:
            if proc.stdout is None:
                logger.error("Plugin %s: stdout is None", binary_path)
                return None
            line = await asyncio.wait_for(proc.stdout.readline(), timeout=DESCRIBE_TIMEOUT)
        except asyncio.TimeoutError:
            logger.error("Timeout waiting for describe response from %s", binary_path)
            return None

        if not line:
            logger.error("Plugin %s: no describe response (EOF)", binary_path)
            return None

        try:
            raw = json.loads(line.decode().strip())
        except json.JSONDecodeError as e:
            logger.error("Failed to parse describe response from %s: %s", binary_path, e)
            return None

        try:
            rpc_response = DescribeRPCResponse.model_validate(raw)
        except Exception as e:
            logger.error("Plugin %s: invalid describe RPC response: %s", binary_path, e)
            return None

        desc = rpc_response.result

        if not isinstance(desc.type, str) or desc.type not in ("hook", "executor"):
            logger.warning("Plugin %s: unknown type '%s', skipping", binary_path, desc.type)
            return None

        return PluginInfo(
            name=desc.name,
            type=desc.type,
            version=desc.version,
            help_msg=desc.help_msg,
            binary_path=binary_path,
            hooks=desc.hooks,
            params_schema=desc.params_schema,
            config_schema=desc.config_schema,
        )

    def _register(self, plugin_info: PluginInfo, proc: asyncio.subprocess.Process) -> None:
        self._plugins[plugin_info.name] = plugin_info
        self._processes[plugin_info.name] = proc
        self._restart_counts[plugin_info.name] = 0

        if plugin_info.type == "hook":
            for hook in plugin_info.hooks:
                self._hook_map.setdefault(hook, []).append(plugin_info.name)
            logger.info(
                "Registered hook plugin: %s (hooks: %s)", plugin_info.name, plugin_info.hooks
            )
        elif plugin_info.type == "executor":
            self._executor_map[plugin_info.name] = plugin_info.name
            logger.info("Registered executor plugin: %s", plugin_info.name)

        task = asyncio.create_task(self._monitor_process(plugin_info.name))
        self._monitor_tasks[plugin_info.name] = task

    async def _monitor_process(self, plugin_name: str) -> None:
        proc = self._processes.get(plugin_name)
        if proc is None:
            return
        with contextlib.suppress(Exception):
            await proc.wait()

        plugin_info = self._plugins.get(plugin_name)
        if plugin_info is None:
            return

        restart_count = self._restart_counts.get(plugin_name, 0)
        if restart_count < MAX_RESTARTS:
            logger.warning(
                "Plugin %s crashed, restarting (attempt %d/%d)",
                plugin_name,
                restart_count + 1,
                MAX_RESTARTS,
            )
            self._restart_counts[plugin_name] = restart_count + 1
            if plugin_info.binary_path is not None:
                await self._load_plugin(plugin_info.binary_path)
        else:
            logger.error(
                "Plugin %s crashed %d times, marking as crashed",
                plugin_name,
                MAX_RESTARTS,
            )
            plugin_info.status = "crashed"
            self._processes.pop(plugin_name, None)

    async def dispatch(self, hook_name: str, ctx: dict[str, Any]) -> None:
        if hook_name not in self._hook_map:
            return
        for plugin_name in self._hook_map[hook_name]:
            plugin_info = self._plugins.get(plugin_name)
            if plugin_info is None or plugin_info.status == "crashed":
                continue
            proc = self._processes.get(plugin_name)
            if proc is None or proc.returncode is not None:
                continue
            request = json.dumps(
                {"jsonrpc": "2.0", "method": hook_name, "params": ctx, "id": 1}
            )
            try:
                if proc.stdin is None:
                    continue
                proc.stdin.write((request + "\n").encode())
                await proc.stdin.drain()
            except (BrokenPipeError, ConnectionResetError, OSError) as e:
                logger.error("Failed to dispatch %s to %s: %s", hook_name, plugin_name, e)

    async def execute(
        self, plugin_name: str, params: dict[str, Any], timeout: float | None = None
    ) -> ExecuteResult:
        plugin_info = self._plugins.get(plugin_name)
        if plugin_info is None or plugin_info.type != "executor":
            raise ValueError(f"Executor plugin '{plugin_name}' not found")
        if plugin_info.status == "crashed":
            raise RuntimeError(f"Plugin '{plugin_name}' is crashed")

        proc = self._processes.get(plugin_name)
        if proc is None or proc.returncode is not None:
            raise RuntimeError(f"Plugin '{plugin_name}' process is not running")

        request = json.dumps(
            {"jsonrpc": "2.0", "method": "execute", "params": params, "id": 1}
        )
        try:
            if proc.stdin is None:
                raise RuntimeError(f"Plugin '{plugin_name}' stdin is None")
            proc.stdin.write((request + "\n").encode())
            await proc.stdin.drain()
        except (BrokenPipeError, ConnectionResetError, OSError) as e:
            logger.error("Failed to send execute request to %s: %s", plugin_name, e)
            raise

        effective_timeout = timeout if timeout is not None else EXECUTE_DEFAULT_TIMEOUT
        try:
            if proc.stdout is None:
                raise RuntimeError(f"Plugin '{plugin_name}' stdout is None")
            line = await asyncio.wait_for(proc.stdout.readline(), timeout=effective_timeout)
        except asyncio.TimeoutError:
            logger.error("Executor plugin %s timed out after %ss", plugin_name, effective_timeout)
            return ExecuteResult(success=False, stderr=f"Execution timed out after {effective_timeout}s")

        if not line:
            logger.error("Plugin %s: no execute response (EOF)", plugin_name)
            return ExecuteResult(success=False, stderr="Plugin process exited unexpectedly")

        try:
            raw = json.loads(line.decode().strip())
            rpc_response = ExecuteRPCResponse.model_validate(raw)
        except json.JSONDecodeError as e:
            logger.error("Failed to parse execute response from %s: %s", plugin_name, e)
            return ExecuteResult(success=False, stderr=f"Invalid JSON response: {e}")
        except Exception as e:
            logger.error("Invalid execute response from %s: %s", plugin_name, e)
            return ExecuteResult(success=False, stderr=f"Invalid RPC response: {e}")

        return rpc_response.result

    async def shutdown(self) -> None:
        shutdown_req = json.dumps({"jsonrpc": "2.0", "method": "on_shutdown", "id": 1}) + "\n"
        for plugin_name in list(self._plugins.keys()):
            proc = self._processes.get(plugin_name)
            if proc is not None and proc.returncode is None:
                try:
                    if proc.stdin is not None:
                        proc.stdin.write(shutdown_req.encode())
                        await proc.stdin.drain()
                except (BrokenPipeError, ConnectionResetError, OSError):
                    pass

        for plugin_name in list(self._processes.keys()):
            proc = self._processes[plugin_name]
            try:
                try:
                    await asyncio.wait_for(proc.wait(), timeout=3)
                except asyncio.TimeoutError:
                    proc.kill()
                    await proc.wait()
            except (ProcessLookupError, OSError):
                pass
            logger.info("Plugin %s shut down", plugin_name)

        self._plugins.clear()
        self._processes.clear()
        self._hook_map.clear()
        self._executor_map.clear()

        for task in self._monitor_tasks.values():
            task.cancel()
        self._monitor_tasks.clear()

    def list_plugins(self) -> list[PluginInfo]:
        return list(self._plugins.values())

    def get_plugin(self, name: str) -> PluginInfo | None:
        return self._plugins.get(name)

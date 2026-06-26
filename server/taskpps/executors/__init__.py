from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from taskpps.domain.pipeline import ResolvedTask
from taskpps.executors.agent_executor import AgentExecutor
from taskpps.executors.base import BaseExecutor
from taskpps.executors.invoke import InvokeExecutor
from taskpps.executors.local import LocalExecutor
from taskpps.executors.plugin import PluginExecutor
from taskpps.executors.ssh import SSHExecutor
from taskpps.i18n import t
from taskpps.loaders.agent_loader import AgentLoader
from taskpps.loaders.credential_loader import CredentialLoader
from taskpps.services.agent_manager import AgentManager

logger = logging.getLogger(__name__)


class AgentNotFoundError(Exception):
    pass


def create_executor(
    task: ResolvedTask, project_workdir: str | None = None, max_parallel: int | None = None
) -> BaseExecutor:
    if task.task_type == "invoke":
        return InvokeExecutor()

    if task.task_type == "plugin" and task.plugin:
        plugin_command = _build_plugin_command(task.plugin, task.plugin_params)
        if task.host:
            delegate = _create_plugin_remote_delegate(task, project_workdir)
            return PluginExecutor(plugin_command, delegate=delegate)
        return PluginExecutor(plugin_command)

    if task.host:
        from pathlib import Path

        from taskpps.config import get_agents_dir

        agents_dir = get_agents_dir(Path(project_workdir)) if project_workdir else None
        agent_loader = AgentLoader(base_dir=agents_dir) if agents_dir else AgentLoader()
        agent_data = _resolve_agent(agent_loader, task.host)

        # 如果在项目 agents 目录未找到,尝试默认 agents 目录
        if agent_data is None and agents_dir is not None:
            default_loader = AgentLoader()
            agent_data = _resolve_agent(default_loader, task.host)

        # 对于已通过 WebSocket 连接的 execution-agent,即使没有配置文件也可执行
        if agent_data is None:
            manager = AgentManager.instance()
            if manager.is_connected(task.host):
                logger.info(
                    "Agent '%s' not found in config but connected via WebSocket, using AgentExecutor",
                    task.host,
                )
                agent_data = {"id": task.host, "execution_agent": True}
            else:
                raise AgentNotFoundError(
                    t(
                        "Agent not found for host: '{host}'. Please create an agent config in the agents/ directory.",
                        host=task.host,
                    )
                )

        host = agent_data.get("host", task.host)
        port = agent_data.get("port", 22)

        if agent_data.get("execution_agent", True):
            manager = AgentManager.instance()
            # Issue #115: parallel 策略下,若 agent 未显式配置 max_parallel,
            # 使用 pipeline 的 max_concurrent_tasks 作为默认值,避免任务被串行化。
            effective_max_parallel: int | None = agent_data.get("max_parallel")
            if effective_max_parallel is None:
                effective_max_parallel = max_parallel
            if effective_max_parallel is not None:
                agent_data = {**agent_data, "max_parallel": effective_max_parallel}
            return AgentExecutor(agent_id=task.host, manager=manager, agent_data=agent_data)

        return _make_ssh_executor(host, port, agent_data, task)

    return LocalExecutor()


def _build_plugin_command(plugin_name: str, params: dict) -> str:
    from taskpps.services.plugin_center import get_plugin_center

    pc = get_plugin_center()
    if pc is not None:
        p_info = pc.get_plugin(plugin_name)
        if p_info is not None and p_info.binary_path is not None:
            bp = p_info.binary_path
            if bp.name == "plugin.py":
                return _build_python_plugin_command(bp, params)

    raise ValueError(f"Plugin '{plugin_name}' not found")


def _build_python_plugin_command(plugin_py: Path, params: dict) -> str:
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        f"_plugin_exec_{plugin_py.parent.name}", str(plugin_py)
    )
    if spec is None or spec.loader is None:
        raise ValueError(f"Failed to load plugin: {plugin_py}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    for attr_name in dir(module):
        attr = getattr(module, attr_name)
        if (
            isinstance(attr, type)
            and attr.__module__ == module.__name__
            and hasattr(attr, "params_schema")
            and hasattr(attr, "build_command")
        ):
            instance = attr(**params)
            return instance.build_command()

    raise ValueError(f"No plugin class with build_command found in {plugin_py}")


def _create_plugin_remote_delegate(
    task: ResolvedTask, project_workdir: str | None = None
) -> BaseExecutor:
    from taskpps.config import get_agents_dir

    agents_dir = get_agents_dir(Path(project_workdir)) if project_workdir else None
    agent_loader = AgentLoader(base_dir=agents_dir) if agents_dir else AgentLoader()
    agent_data = _resolve_agent(agent_loader, task.host)

    if agent_data is None and agents_dir is not None:
        default_loader = AgentLoader()
        agent_data = _resolve_agent(default_loader, task.host)

    if agent_data is not None:
        host = agent_data.get("host", task.host)
        port = agent_data.get("port", 22)
        if agent_data.get("execution_agent", True):
            manager = AgentManager.instance()
            if manager.is_connected(task.host):
                return AgentExecutor(
                    agent_id=task.host,
                    manager=manager,
                    agent_data=agent_data,
                )
            return _make_ssh_executor(host, port, agent_data, task)
        return _make_ssh_executor(host, port, agent_data, task)

    if task.host:
        manager = AgentManager.instance()
        if manager.is_connected(task.host):
            return AgentExecutor(
                agent_id=task.host,
                manager=manager,
                agent_data={"id": task.host, "execution_agent": True},
            )

    return SSHExecutor(host=task.host)


def _make_ssh_executor(host: str, port: int, agent_data: dict[str, Any], task: ResolvedTask) -> SSHExecutor:
    username = None
    password = None
    key_path = None

    credential_id = task.credential or agent_data.get("credential_id")
    if credential_id:
        cred_loader = CredentialLoader()
        cred_data = _resolve_credential(cred_loader, credential_id)
        if cred_data:
            username = cred_data.get("username")
            password = cred_data.get("password")
            key_path = cred_data.get("key_path")

    # 仅在 credential 未提供 username 时回退到 agent 配置或默认值
    if username is None:
        username = agent_data.get("username", "root")

    if not password and not key_path:
        logger.warning(
            t(
                "No authentication method for host '{host}'. "
                "Set credential_id with password or key_path in agent config.",
                host=host,
            )
        )

    return SSHExecutor(
        host=host,
        port=port,
        username=username,
        password=password,
        key_path=key_path,
    )


def _resolve_agent(agent_loader: AgentLoader, agent_ref: str) -> dict[str, Any] | None:
    agent_data = agent_loader.get(agent_ref)
    if agent_data is not None:
        return agent_data

    try:
        return agent_loader.load(agent_ref)
    except FileNotFoundError:
        logger.warning(f"Agent not found by ID or filename: {agent_ref}")
        return None


def _resolve_credential(cred_loader: CredentialLoader, cred_ref: str) -> dict[str, Any] | None:
    cred_data = cred_loader.get(cred_ref)
    if cred_data is not None:
        return cred_data

    try:
        return cred_loader.load(cred_ref)
    except FileNotFoundError:
        logger.warning(f"Credential not found by ID or filename: {cred_ref}")
        return None

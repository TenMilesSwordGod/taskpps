from __future__ import annotations

from typing import Any, Dict, Optional

from taskpps.domain.pipeline import ResolvedTask
from taskpps.executors.base import BaseExecutor, ExecutorResult
from taskpps.executors.local import LocalExecutor
from taskpps.executors.ssh import SSHExecutor
from taskpps.executors.invoke import InvokeExecutor
from taskpps.loaders.agent_loader import AgentLoader
from taskpps.loaders.credential_loader import CredentialLoader


def create_executor(task: ResolvedTask) -> BaseExecutor:
    if task.task_type == "invoke":
        return InvokeExecutor()

    # steps task type uses the same executor as command (LocalExecutor or SSHExecutor)
    if task.host:
        agent_loader = AgentLoader()
        try:
            agent_data = agent_loader.load(task.host)
        except FileNotFoundError:
            return LocalExecutor()

        host = agent_data.get("host", task.host)
        port = agent_data.get("port", 22)
        username = agent_data.get("username", "root")

        password = None
        key_path = None
        if task.credential:
            cred_loader = CredentialLoader()
            try:
                cred_data = cred_loader.load(task.credential)
                password = cred_data.get("password")
                key_path = cred_data.get("key_path")
            except FileNotFoundError:
                pass

        return SSHExecutor(
            host=host,
            port=port,
            username=username,
            password=password,
            key_path=key_path,
        )

    return LocalExecutor()

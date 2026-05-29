from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from taskpps.domain.pipeline import ResolvedTask
from taskpps.executors.base import BaseExecutor, ExecutorResult
from taskpps.executors.local import LocalExecutor
from taskpps.executors.ssh import SSHExecutor
from taskpps.executors.invoke import InvokeExecutor
from taskpps.loaders.agent_loader import AgentLoader
from taskpps.loaders.credential_loader import CredentialLoader

logger = logging.getLogger(__name__)


def create_executor(task: ResolvedTask) -> BaseExecutor:
    if task.task_type == "invoke":
        return InvokeExecutor()

    if task.host:
        agent_loader = AgentLoader()
        agent_data = _resolve_agent(agent_loader, task.host)

        if agent_data is None:
            return LocalExecutor()

        host = agent_data.get("host", task.host)
        port = agent_data.get("port", 22)
        username = agent_data.get("username", "root")

        password = None
        key_path = None

        credential_id = task.credential or agent_data.get("credential_id")
        if credential_id:
            cred_loader = CredentialLoader()
            cred_data = _resolve_credential(cred_loader, credential_id)
            if cred_data:
                password = cred_data.get("password")
                key_path = cred_data.get("key_path")

        return SSHExecutor(
            host=host,
            port=port,
            username=username,
            password=password,
            key_path=key_path,
        )

    return LocalExecutor()


def _resolve_agent(agent_loader: AgentLoader, agent_ref: str) -> Optional[Dict[str, Any]]:
    agent_data = agent_loader.get(agent_ref)
    if agent_data is not None:
        return agent_data

    try:
        return agent_loader.load(agent_ref)
    except FileNotFoundError:
        logger.warning(f"Agent not found by ID or filename: {agent_ref}")
        return None


def _resolve_credential(cred_loader: CredentialLoader, cred_ref: str) -> Optional[Dict[str, Any]]:
    cred_data = cred_loader.get(cred_ref)
    if cred_data is not None:
        return cred_data

    try:
        return cred_loader.load(cred_ref)
    except FileNotFoundError:
        logger.warning(f"Credential not found by ID or filename: {cred_ref}")
        return None
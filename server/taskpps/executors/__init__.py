from __future__ import annotations

import logging
from typing import Any

from taskpps.domain.pipeline import ResolvedTask
from taskpps.executors.base import BaseExecutor
from taskpps.executors.git import GitExecutor
from taskpps.executors.invoke import InvokeExecutor
from taskpps.executors.local import LocalExecutor
from taskpps.executors.nexus import NexusExecutor
from taskpps.executors.ssh import SSHExecutor
from taskpps.i18n import t
from taskpps.loaders.agent_loader import AgentLoader
from taskpps.loaders.credential_loader import CredentialLoader

logger = logging.getLogger(__name__)


class AgentNotFoundError(Exception):
    pass


def create_executor(task: ResolvedTask) -> BaseExecutor:
    if task.task_type == "invoke":
        return InvokeExecutor()

    if task.task_type == "git" and task.git:
        return GitExecutor(
            repo=task.git.get("repo", ""),
            ref=task.git.get("ref"),
            credential=task.git.get("credential"),
            dest=task.git.get("dest", "/workspace/repo"),
            depth=task.git.get("depth", 1),
            submodules=task.git.get("submodules", False),
        )

    if task.task_type == "nexus" and task.nexus:
        return NexusExecutor(
            action=task.nexus.get("action", "upload"),
            url=task.nexus.get("url", ""),
            repository=task.nexus.get("repository", ""),
            credential=task.nexus.get("credential"),
            group_id=task.nexus.get("group_id"),
            artifact_id=task.nexus.get("artifact_id"),
            version=task.nexus.get("version"),
            packaging=task.nexus.get("packaging", "jar"),
            classifier=task.nexus.get("classifier"),
            files=task.nexus.get("files"),
            dest=task.nexus.get("dest"),
            query=task.nexus.get("query"),
            source_repo=task.nexus.get("source_repo"),
            target_repo=task.nexus.get("target_repo"),
        )

    if task.host:
        agent_loader = AgentLoader()
        agent_data = _resolve_agent(agent_loader, task.host)

        if agent_data is None:
            raise AgentNotFoundError(
                t(
                    "Agent not found for host: '{host}'. Please create an agent config in the agents/ directory.",
                    host=task.host,
                )
            )

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
                username = cred_data.get("username", username)
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

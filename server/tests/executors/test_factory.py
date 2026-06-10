from __future__ import annotations

from unittest.mock import patch

import pytest

from taskpps.domain.pipeline import ResolvedTask
from taskpps.executors import AgentNotFoundError, create_executor
from taskpps.executors.invoke import InvokeExecutor
from taskpps.executors.local import LocalExecutor
from taskpps.executors.ssh import SSHExecutor


class TestCreateExecutor:
    def test_local(self):
        task = ResolvedTask(name="t", task_type="command", command="echo")
        executor = create_executor(task)
        assert isinstance(executor, LocalExecutor)

    def test_invoke(self):
        task = ResolvedTask(name="t", task_type="invoke", invoke_task="mod.fn")
        executor = create_executor(task)
        assert isinstance(executor, InvokeExecutor)

    def test_ssh(self, tmp_path):
        task = ResolvedTask(
            name="t",
            task_type="command",
            command="echo",
            host="myhost",
        )

        with patch("taskpps.loaders.agent_loader.get_agents_dir") as mock_get_agents_dir:
            agents_dir = tmp_path / "agents"
            agents_dir.mkdir()
            agent_file = agents_dir / "myhost.yaml"
            agent_file.write_text("host: 1.2.3.4\nport: 2222\nusername: admin\nexecution_agent: false\n")
            mock_get_agents_dir.return_value = agents_dir

            executor = create_executor(task)
            assert isinstance(executor, SSHExecutor)
            assert executor.host == "1.2.3.4"
            assert executor.port == 2222
            assert executor.username == "admin"

    def test_ssh_with_credential(self, tmp_path):
        task = ResolvedTask(
            name="t",
            task_type="command",
            command="echo",
            host="myhost",
            credential="mycred",
        )

        with (
            patch("taskpps.loaders.agent_loader.get_agents_dir") as mock_get_agents_dir,
            patch("taskpps.loaders.credential_loader.get_credentials_dir") as mock_get_creds_dir,
        ):
            agents_dir = tmp_path / "agents"
            agents_dir.mkdir()
            agent_file = agents_dir / "myhost.yaml"
            agent_file.write_text("host: 1.2.3.4\nport: 2222\nusername: admin\nexecution_agent: false\n")
            mock_get_agents_dir.return_value = agents_dir

            creds_dir = tmp_path / "credentials"
            creds_dir.mkdir()
            cred_file = creds_dir / "mycred.yaml"
            cred_file.write_text("password: secret123\n")
            mock_get_creds_dir.return_value = creds_dir

            executor = create_executor(task)
            assert isinstance(executor, SSHExecutor)
            assert executor.password == "secret123"

    def test_ssh_agent_not_found(self, tmp_path):
        task = ResolvedTask(
            name="t",
            task_type="command",
            command="echo",
            host="nonexistent-host",
        )

        with patch("taskpps.loaders.agent_loader.get_agents_dir") as mock_get_agents_dir:
            agents_dir = tmp_path / "agents"
            agents_dir.mkdir()
            mock_get_agents_dir.return_value = agents_dir

            with pytest.raises(AgentNotFoundError, match="nonexistent-host"):
                create_executor(task)

    def test_ssh_credential_not_found(self, tmp_path):
        task = ResolvedTask(
            name="t",
            task_type="command",
            command="echo",
            host="myhost",
            credential="nonexistent-cred",
        )

        with (
            patch("taskpps.loaders.agent_loader.get_agents_dir") as mock_get_agents_dir,
            patch("taskpps.loaders.credential_loader.get_credentials_dir") as mock_get_creds_dir,
        ):
            agents_dir = tmp_path / "agents"
            agents_dir.mkdir()
            agent_file = agents_dir / "myhost.yaml"
            agent_file.write_text("host: 1.2.3.4\nport: 2222\nusername: admin\nexecution_agent: false\n")
            mock_get_agents_dir.return_value = agents_dir

            creds_dir = tmp_path / "credentials"
            creds_dir.mkdir()
            mock_get_creds_dir.return_value = creds_dir

            executor = create_executor(task)
            assert isinstance(executor, SSHExecutor)
            assert executor.password is None
            assert executor.key_path is None

    def test_command_no_host(self):
        task = ResolvedTask(name="t", task_type="command", command="echo")
        executor = create_executor(task)
        assert isinstance(executor, LocalExecutor)

    def test_project_workdir_passed_to_agent_loader(self, tmp_path):
        """project_workdir 应传递给 AgentLoader，使其在正确的 agents 目录查找。"""
        project_dir = tmp_path / "myproject"
        project_dir.mkdir()
        agents_dir = project_dir / "agents"
        agents_dir.mkdir()
        agent_file = agents_dir / "auto-03.yaml"
        agent_file.write_text("host: 10.0.0.1\nport: 22\nexecution_agent: true\n")

        task = ResolvedTask(
            name="t",
            task_type="command",
            command="echo",
            host="auto-03",
        )

        executor = create_executor(task, project_workdir=str(project_dir))
        from taskpps.executors.agent_executor import AgentExecutor

        assert isinstance(executor, AgentExecutor)
        assert executor._agent_id == "auto-03"

    def test_project_workdir_not_found_agent(self, tmp_path):
        """project_workdir 指向的目录没有对应 agent 时应抛出 AgentNotFoundError。"""
        project_dir = tmp_path / "empty_project"
        project_dir.mkdir()
        agents_dir = project_dir / "agents"
        agents_dir.mkdir()

        task = ResolvedTask(
            name="t",
            task_type="command",
            command="echo",
            host="auto-03",
        )

        with pytest.raises(AgentNotFoundError, match="auto-03"):
            create_executor(task, project_workdir=str(project_dir))

    def test_invoke_type(self):
        task = ResolvedTask(name="t", task_type="invoke", invoke_task="mod.fn")
        executor = create_executor(task)
        assert isinstance(executor, InvokeExecutor)

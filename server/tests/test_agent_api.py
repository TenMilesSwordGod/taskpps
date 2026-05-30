import socket

import pytest
import yaml

from taskpps.loaders.agent_loader import AgentLoader
from taskpps.schemas.agent import AgentCheckRequest
from taskpps.services.agent_service import AgentService, _match_file_filter


# ============================================================
# AgentLoader source_file tests
# ============================================================

class TestAgentLoaderSourceFile:
    def test_agents_list_has_source_file(self, tmp_path):
        agent_file = tmp_path / "ssh.yaml"
        agent_file.write_text(yaml.dump({
            "agents": [
                {"id": "agent-a", "host": "10.0.0.1", "port": 22, "username": "admin"},
                {"id": "agent-b", "host": "10.0.0.2", "credential_id": "cred-x"},
            ]
        }))
        loader = AgentLoader(tmp_path)
        all_agents = loader.load_all()
        assert all_agents["agent-a"]["_source_file"] == f"{tmp_path.name}/ssh.yaml"
        assert all_agents["agent-b"]["_source_file"] == f"{tmp_path.name}/ssh.yaml"

    def test_old_format_has_source_file(self, tmp_path):
        agent_file = tmp_path / "staging.yaml"
        agent_file.write_text(yaml.dump({"host": "127.0.0.1", "port": 22, "username": "test"}))
        loader = AgentLoader(tmp_path)
        all_agents = loader.load_all()
        assert all_agents["staging"]["_source_file"] == f"{tmp_path.name}/staging.yaml"

    def test_source_file_with_nested_base_dir(self, tmp_path):
        agents_dir = tmp_path / "config" / "agents"
        agents_dir.mkdir(parents=True)
        (agents_dir / "prod.yaml").write_text(yaml.dump({
            "agents": [{"id": "agent-x", "host": "10.0.0.1"}]
        }))
        loader = AgentLoader(agents_dir)
        all_agents = loader.load_all()
        assert all_agents["agent-x"]["_source_file"] == "agents/prod.yaml"


# ============================================================
# _match_file_filter tests
# ============================================================

class TestMatchFileFilter:
    def test_exact_match(self):
        assert _match_file_filter("agents/staging.yaml", "staging")

    def test_no_match(self):
        assert not _match_file_filter("agents/staging.yaml", "prod")

    def test_partial_match(self):
        assert _match_file_filter("agents/prod.yaml", "prod")

    def test_case_insensitive(self):
        assert _match_file_filter("agents/STAGING.yaml", "staging")

    def test_no_source_file(self):
        assert not _match_file_filter("", "staging")


# ============================================================
# AgentService tests
# ============================================================

class TestAgentService:
    def _make_agents(self, tmp_path):
        agents_dir = tmp_path / "agents"
        agents_dir.mkdir()
        (agents_dir / "ssh.yaml").write_text(yaml.dump({
            "agents": [
                {"id": "agent-a", "host": "10.0.0.1", "port": 22, "username": "admin",
                 "name": "Agent A", "type": "ssh-key"},
                {"id": "agent-b", "host": "10.0.0.2", "port": 22, "username": "admin",
                 "name": "Agent B", "type": "ssh-key"},
            ]
        }))
        return agents_dir

    def test_try_connect_not_found(self, tmp_path):
        agents_dir = self._make_agents(tmp_path)
        svc = AgentService()
        svc._loader = AgentLoader(agents_dir)
        with pytest.raises(ValueError, match="Agent not found"):
            svc.try_connect("nonexistent")

    def test_try_connect_local_agent(self, tmp_path):
        agents_dir = tmp_path / "agents"
        agents_dir.mkdir()
        (agents_dir / "local.yaml").write_text(yaml.dump({
            "agents": [{"id": "local-agent", "host": "127.0.0.1", "port": 22, "name": "Local", "type": "local"}]
        }))
        svc = AgentService()
        svc._loader = AgentLoader(agents_dir)
        result = svc.try_connect("local-agent")
        assert result.status == "ready"
        assert result.host == "127.0.0.1"
        assert result.latency_ms == 0

    def test_try_connect_no_host(self, tmp_path):
        agents_dir = tmp_path / "agents"
        agents_dir.mkdir()
        (agents_dir / "local.yaml").write_text(yaml.dump({
            "agents": [{"id": "no-host-agent", "host": "", "port": 0, "name": "NoHost", "type": "local"}]
        }))
        svc = AgentService()
        svc._loader = AgentLoader(agents_dir)
        result = svc.try_connect("no-host-agent")
        assert result.status == "ready"

    def test_try_connect_timeout(self, tmp_path):
        agents_dir = tmp_path / "agents"
        agents_dir.mkdir()
        (agents_dir / "ssh.yaml").write_text(yaml.dump({
            "agents": [{"id": "timeout-agent", "host": "192.0.2.1", "port": 9999, "name": "Timeout", "type": "ssh-key"}]
        }))
        svc = AgentService()
        svc._loader = AgentLoader(agents_dir)
        result = svc.try_connect("timeout-agent", timeout=1)
        assert result.status == "failed"
        assert "timed out" in result.error.lower()

    def test_try_connect_refused(self, tmp_path):
        agents_dir = tmp_path / "agents"
        agents_dir.mkdir()
        (agents_dir / "ssh.yaml").write_text(yaml.dump({
            "agents": [{"id": "refused-agent", "host": "169.254.0.1", "port": 1, "name": "Refused", "type": "ssh-key"}]
        }))
        svc = AgentService()
        svc._loader = AgentLoader(agents_dir)
        result = svc.try_connect("refused-agent", timeout=1)
        assert result.status == "failed"

    def test_check_single_agent(self, tmp_path):
        agents_dir = tmp_path / "agents"
        agents_dir.mkdir()
        (agents_dir / "ssh.yaml").write_text(yaml.dump({
            "agents": [{"id": "agent-x", "host": "127.0.0.1", "port": 22, "name": "X", "type": "local"}]
        }))
        svc = AgentService()
        svc._loader = AgentLoader(agents_dir)
        response = svc.check(AgentCheckRequest(agent_id="agent-x"))
        assert response.summary.total == 1
        assert response.results[0].agent_id == "agent-x"

    def test_check_all(self, tmp_path):
        agents_dir = self._make_agents(tmp_path)
        svc = AgentService()
        svc._loader = AgentLoader(agents_dir)
        response = svc.check(AgentCheckRequest())
        assert response.summary.total == 2

    def test_check_file_filter(self, tmp_path):
        agents_dir = self._make_agents(tmp_path)
        svc = AgentService()
        svc._loader = AgentLoader(agents_dir)
        response = svc.check(AgentCheckRequest(file_filter="ssh"))
        assert response.summary.total == 2

    def test_check_file_filter_no_match(self, tmp_path):
        agents_dir = self._make_agents(tmp_path)
        svc = AgentService()
        svc._loader = AgentLoader(agents_dir)
        response = svc.check(AgentCheckRequest(file_filter="nonexistent"))
        assert response.summary.total == 0

    def test_check_with_timeout(self, tmp_path):
        agents_dir = self._make_agents(tmp_path)
        svc = AgentService()
        svc._loader = AgentLoader(agents_dir)
        response = svc.check(AgentCheckRequest(timeout=10))
        assert response.summary.total == 2

    def test_check_result_has_source_file(self, tmp_path):
        agents_dir = self._make_agents(tmp_path)
        svc = AgentService()
        svc._loader = AgentLoader(agents_dir)
        response = svc.check(AgentCheckRequest())
        for r in response.results:
            assert r.source_file == f"{agents_dir.name}/ssh.yaml"


def _find_free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("", 0))
        return s.getsockname()[1]
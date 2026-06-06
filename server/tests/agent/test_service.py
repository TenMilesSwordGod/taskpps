from unittest.mock import MagicMock, patch

from taskpps.services.agent_service import AgentService, _match_file_filter


def _make_agent_data(
    agent_id="test-agent",
    host="10.0.0.1",
    port=22,
    credential_id=None,
    username="root",
    agent_type="ssh-username-password",
):
    return {
        "id": agent_id,
        "name": f"Test Agent {agent_id}",
        "type": agent_type,
        "host": host,
        "port": port,
        "username": username,
        "credential_id": credential_id,
        "_source_file": "agents/test.yaml",
    }


def _make_credential_data(cred_id="test-cred", username="admin", password=None, key_path=None):
    data = {"id": cred_id, "username": username}
    if password:
        data["password"] = password
    if key_path:
        data["key_path"] = key_path
    return data


def _patch_paramiko():
    mock_paramiko = MagicMock()
    mock_client = MagicMock()
    mock_paramiko.SSHClient.return_value = mock_client
    mock_paramiko.AutoAddPolicy.return_value = MagicMock()
    mock_paramiko.AuthenticationException = type("AuthenticationException", (Exception,), {})
    return mock_paramiko, mock_client


class TestCheckOne:
    def test_local_agent_ready(self):
        svc = AgentService()
        agent = _make_agent_data(host="localhost")
        result = svc._check_one(agent, 5)
        assert result.status == "ready"
        assert result.agent_id == "test-agent"

    def test_local_agent_127(self):
        svc = AgentService()
        agent = _make_agent_data(host="127.0.0.1")
        result = svc._check_one(agent, 5)
        assert result.status == "ready"

    def test_local_agent_empty_host(self):
        svc = AgentService()
        agent = _make_agent_data(host="")
        result = svc._check_one(agent, 5)
        assert result.status == "ready"

    def test_tcp_connected_no_credential(self):
        svc = AgentService()
        agent = _make_agent_data(host="10.0.0.1", credential_id=None)
        with patch("taskpps.services.agent_service.socket") as mock_socket:
            mock_sock = MagicMock()
            mock_socket.create_connection.return_value = mock_sock
            result = svc._check_one(agent, 5)
        assert result.status == "connected"
        assert result.agent_id == "test-agent"

    def test_tcp_timeout(self):
        svc = AgentService()
        agent = _make_agent_data(host="10.0.0.1")
        with patch("taskpps.services.agent_service.socket") as mock_socket:
            mock_socket.create_connection.side_effect = TimeoutError()
            result = svc._check_one(agent, 5)
        assert result.status == "failed"
        assert "timed out" in result.error

    def test_tcp_connection_refused(self):
        svc = AgentService()
        agent = _make_agent_data(host="10.0.0.1")
        with patch("taskpps.services.agent_service.socket") as mock_socket:
            mock_socket.create_connection.side_effect = ConnectionRefusedError("Connection refused")
            result = svc._check_one(agent, 5)
        assert result.status == "failed"
        assert "Connection refused" in result.error


class TestCheckSshAuth:
    def test_credential_not_found(self):
        svc = AgentService()
        agent = _make_agent_data(host="10.0.0.1", credential_id="nonexistent-cred")
        with patch.object(svc._loader, "resolve_credential", return_value=None):
            result = svc._check_ssh_auth(agent, 5)
        assert result is not None
        assert result.status == "failed"
        assert "nonexistent-cred" in result.error

    def test_credential_no_password_no_key(self):
        svc = AgentService()
        agent = _make_agent_data(host="10.0.0.1", credential_id="bad-cred")
        cred = _make_credential_data(cred_id="bad-cred", username="admin")
        with patch.object(svc._loader, "resolve_credential", return_value=cred):
            result = svc._check_ssh_auth(agent, 5)
        assert result is not None
        assert result.status == "failed"
        assert "no password or key_path" in result.error

    def test_auth_success_with_password(self):
        svc = AgentService()
        agent = _make_agent_data(host="10.0.0.1", credential_id="test-cred")
        cred = _make_credential_data(cred_id="test-cred", username="admin", password="secret")
        mock_paramiko, _mock_client = _patch_paramiko()
        with (
            patch.object(svc._loader, "resolve_credential", return_value=cred),
            patch.dict("sys.modules", {"paramiko": mock_paramiko}),
        ):
            result = svc._check_ssh_auth(agent, 5)
        assert result is None

    def test_auth_success_with_key(self):
        svc = AgentService()
        agent = _make_agent_data(host="10.0.0.1", credential_id="test-cred")
        cred = _make_credential_data(cred_id="test-cred", username="admin", key_path="/path/to/key")
        mock_paramiko, _mock_client = _patch_paramiko()
        with (
            patch.object(svc._loader, "resolve_credential", return_value=cred),
            patch.dict("sys.modules", {"paramiko": mock_paramiko}),
        ):
            result = svc._check_ssh_auth(agent, 5)
        assert result is None

    def test_auth_failure_wrong_password(self):
        svc = AgentService()
        agent = _make_agent_data(host="10.0.0.1", credential_id="wrong-cred")
        cred = _make_credential_data(cred_id="wrong-cred", username="admin", password="wrong")
        mock_paramiko, mock_client = _patch_paramiko()
        mock_client.connect.side_effect = mock_paramiko.AuthenticationException("Auth failed")
        with (
            patch.object(svc._loader, "resolve_credential", return_value=cred),
            patch.dict("sys.modules", {"paramiko": mock_paramiko}),
        ):
            result = svc._check_ssh_auth(agent, 5)
        assert result is not None
        assert result.status == "failed"
        assert "Authentication failed" in result.error

    def test_auth_failure_wrong_key(self):
        svc = AgentService()
        agent = _make_agent_data(host="10.0.0.1", credential_id="wrong-key-cred")
        cred = _make_credential_data(cred_id="wrong-key-cred", username="admin", key_path="/bad/key")
        mock_paramiko, mock_client = _patch_paramiko()
        mock_client.connect.side_effect = mock_paramiko.AuthenticationException("Invalid key")
        with (
            patch.object(svc._loader, "resolve_credential", return_value=cred),
            patch.dict("sys.modules", {"paramiko": mock_paramiko}),
        ):
            result = svc._check_ssh_auth(agent, 5)
        assert result is not None
        assert result.status == "failed"
        assert "Authentication failed" in result.error

    def test_ssh_connection_error(self):
        svc = AgentService()
        agent = _make_agent_data(host="10.0.0.1", credential_id="test-cred")
        cred = _make_credential_data(cred_id="test-cred", username="admin", password="secret")
        mock_paramiko, mock_client = _patch_paramiko()
        mock_client.connect.side_effect = Exception("Network error")
        with (
            patch.object(svc._loader, "resolve_credential", return_value=cred),
            patch.dict("sys.modules", {"paramiko": mock_paramiko}),
        ):
            result = svc._check_ssh_auth(agent, 5)
        assert result is not None
        assert result.status == "failed"
        assert "SSH auth check failed" in result.error


class TestCheckOneWithCredential:
    def test_tcp_ok_but_auth_fails(self):
        svc = AgentService()
        agent = _make_agent_data(host="10.0.0.1", credential_id="wrong-cred")
        cred = _make_credential_data(cred_id="wrong-cred", username="admin", password="wrong")
        mock_paramiko, mock_client = _patch_paramiko()
        mock_client.connect.side_effect = mock_paramiko.AuthenticationException("Auth failed")
        with (
            patch("taskpps.services.agent_service.socket") as mock_socket,
            patch.object(svc._loader, "resolve_credential", return_value=cred),
            patch.dict("sys.modules", {"paramiko": mock_paramiko}),
        ):
            mock_sock = MagicMock()
            mock_socket.create_connection.return_value = mock_sock
            result = svc._check_one(agent, 5)
        assert result.status == "failed"
        assert "Authentication failed" in result.error

    def test_tcp_ok_and_auth_ok(self):
        svc = AgentService()
        agent = _make_agent_data(host="10.0.0.1", credential_id="good-cred")
        cred = _make_credential_data(cred_id="good-cred", username="admin", password="correct")
        mock_paramiko, _mock_client = _patch_paramiko()
        with (
            patch("taskpps.services.agent_service.socket") as mock_socket,
            patch.object(svc._loader, "resolve_credential", return_value=cred),
            patch.dict("sys.modules", {"paramiko": mock_paramiko}),
        ):
            mock_sock = MagicMock()
            mock_socket.create_connection.return_value = mock_sock
            result = svc._check_one(agent, 5)
        assert result.status == "connected"


class TestMatchFileFilter:
    def test_exact_match(self):
        assert _match_file_filter("agents/staging.yaml", "staging") is True

    def test_yml_extension(self):
        assert _match_file_filter("agents/staging.yml", "staging") is True

    def test_no_match(self):
        assert _match_file_filter("agents/prod.yaml", "staging") is False

    def test_partial_no_match(self):
        assert _match_file_filter("agents/staging-server.yaml", "staging") is False

    def test_case_insensitive(self):
        assert _match_file_filter("agents/Staging.yaml", "staging") is True

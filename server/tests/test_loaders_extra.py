import logging

import pytest

from taskpps.loaders.agent_loader import AgentLoader
from taskpps.loaders.credential_loader import CredentialLoader
from taskpps.loaders.pipeline_loader import PipelineLoader, substitute_env_vars


def test_pipeline_loader_empty_file(tmp_path):
    pipelines_dir = tmp_path / "pipelines"
    pipelines_dir.mkdir()
    empty_file = pipelines_dir / "empty.yaml"
    empty_file.write_text("")
    loader = PipelineLoader(pipelines_dir)
    with pytest.raises(ValueError, match="empty"):
        loader.load("empty.yaml")


def test_pipeline_loader_load_all_no_dir(tmp_path):
    loader = PipelineLoader(tmp_path / "nonexistent")
    result = loader.load_all()
    assert result == {}


def test_pipeline_loader_load_with_env_subst(tmp_path):
    pipelines_dir = tmp_path / "pipelines"
    pipelines_dir.mkdir()
    p = pipelines_dir / "env_test.yaml"
    p.write_text(
        "name: env_test\noptions:\n  env:\n    KEY: ${MY_VAR}\ntasks:\n  - name: step1\n    command: echo ${MY_VAR}\n"
    )
    loader = PipelineLoader(pipelines_dir)
    spec = loader.load("env_test.yaml", env={"MY_VAR": "resolved_value"})
    assert spec.options.env["KEY"] == "resolved_value"
    assert spec.tasks[0].command == "echo resolved_value"


def test_pipeline_loader_load_absolute_path(tmp_path):
    pipelines_dir = tmp_path / "pipelines"
    pipelines_dir.mkdir(parents=True, exist_ok=True)
    yaml_file = pipelines_dir / "absolute.yaml"
    yaml_file.write_text("name: absolute\noptions: {}\ntasks:\n  - name: t1\n    command: echo abs\n")
    loader = PipelineLoader(pipelines_dir)
    spec = loader.load("absolute.yaml")
    assert spec.name == "absolute"


def test_pipeline_loader_load_all_includes_yml(tmp_path):
    pipelines_dir = tmp_path / "pipelines"
    pipelines_dir.mkdir()
    yml_file = pipelines_dir / "test.yml"
    yml_file.write_text("name: yml_test\noptions: {}\ntasks:\n  - name: t1\n    command: echo yml\n")
    loader = PipelineLoader(pipelines_dir)
    result = loader.load_all()
    assert "yml_test" in result


def test_agent_loader_load_all_no_dir(tmp_path):
    loader = AgentLoader(tmp_path / "nonexistent")
    result = loader.load_all()
    assert result == {}


def test_agent_loader_load_all_includes_yml(tmp_path):
    agents_dir = tmp_path / "agents"
    agents_dir.mkdir()
    yml_file = agents_dir / "test-agent.yml"
    yml_file.write_text("host: 1.2.3.4\nport: 22\nusername: test\n")
    loader = AgentLoader(agents_dir)
    result = loader.load_all()
    assert "test-agent" in result


def test_agent_loader_empty_yaml(tmp_path):
    agents_dir = tmp_path / "agents"
    agents_dir.mkdir()
    empty_file = agents_dir / "empty.yaml"
    empty_file.write_text("")
    loader = AgentLoader(agents_dir)
    with pytest.raises(ValueError, match="empty"):
        loader.load("empty")


def test_agent_loader_load_all_with_exception(tmp_path):
    agents_dir = tmp_path / "agents"
    agents_dir.mkdir()
    bad_file = agents_dir / "bad.yaml"
    bad_file.write_text("{invalid: yaml: : }")
    loader = AgentLoader(agents_dir)
    result = loader.load_all()
    assert result == {}


def test_agent_loader_load_yml_extension(tmp_path):
    agents_dir = tmp_path / "agents"
    agents_dir.mkdir()
    yml_file = agents_dir / "test-agent.yml"
    yml_file.write_text("host: 5.6.7.8\nport: 2222\nusername: test\n")
    loader = AgentLoader(agents_dir)
    data = loader.load("test-agent")
    assert data["host"] == "5.6.7.8"


def test_credential_loader_load_all_no_dir(tmp_path):
    loader = CredentialLoader(tmp_path / "nonexistent")
    result = loader.load_all()
    assert result == {}


def test_credential_loader_load_all_includes_yml(tmp_path):
    creds_dir = tmp_path / "credentials"
    creds_dir.mkdir()
    yml_file = creds_dir / "test-cred.yml"
    yml_file.write_text("password: testpass\n")
    loader = CredentialLoader(creds_dir)
    result = loader.load_all()
    assert "test-cred" in result


def test_credential_loader_empty_yaml(tmp_path):
    creds_dir = tmp_path / "credentials"
    creds_dir.mkdir()
    empty_file = creds_dir / "empty.yaml"
    empty_file.write_text("")
    loader = CredentialLoader(creds_dir)
    with pytest.raises(ValueError, match="empty"):
        loader.load("empty")


def test_credential_loader_load_all_with_exception(tmp_path):
    creds_dir = tmp_path / "credentials"
    creds_dir.mkdir()
    bad_file = creds_dir / "bad.yaml"
    bad_file.write_text("{invalid: yaml: : }")
    loader = CredentialLoader(creds_dir)
    result = loader.load_all()
    assert result == {}


def test_credential_loader_load_yml_extension(tmp_path):
    creds_dir = tmp_path / "credentials"
    creds_dir.mkdir()
    yml_file = creds_dir / "test-cred.yml"
    yml_file.write_text("password: secret\n")
    loader = CredentialLoader(creds_dir)
    data = loader.load("test-cred")
    assert data["password"] == "secret"


def test_credential_loader_password_warning(tmp_path, caplog):
    creds_dir = tmp_path / "credentials"
    creds_dir.mkdir()
    yml_file = creds_dir / "test-cred.yaml"
    yml_file.write_text("password: changeme\n")
    loader = CredentialLoader(creds_dir)
    with caplog.at_level(logging.WARNING):
        data = loader.load("test-cred")
    assert data["password"] == "changeme"
    assert "plaintext password" in caplog.text


def test_credential_loader_key_path_no_warning(tmp_path, caplog):
    creds_dir = tmp_path / "credentials"
    creds_dir.mkdir()
    yml_file = creds_dir / "key-cred.yaml"
    yml_file.write_text("key_path: ~/.ssh/deploy_key\n")
    loader = CredentialLoader(creds_dir)
    with caplog.at_level(logging.WARNING):
        data = loader.load("key-cred")
    assert data["key_path"] == "~/.ssh/deploy_key"
    assert "plaintext password" not in caplog.text


def test_substitute_env_vars_no_match():
    result = substitute_env_vars("no vars here", {})
    assert result == "no vars here"


def test_substitute_env_vars_int():
    result = substitute_env_vars(42, {})
    assert result == 42

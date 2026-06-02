import logging

import pytest

from taskpps.loaders.agent_loader import AgentLoader
from taskpps.loaders.credential_loader import CredentialLoader
from taskpps.loaders.pipeline_loader import PipelineLoader, substitute_env_vars


class TestPipelineLoader:
    def test_load(self, setup_project, tmp_project):
        loader = PipelineLoader(tmp_project / "pipelines")
        spec = loader.load("deploy.yaml")
        assert spec.name == "deploy"
        assert len(spec.tasks) == 2
        assert spec.tasks[0].name == "step1"
        assert spec.tasks[1].depends_on == ["step1"]

    def test_load_with_pipelines_prefix(self, setup_project, tmp_project):
        loader = PipelineLoader(tmp_project / "pipelines")
        spec = loader.load("pipelines/deploy.yaml")
        assert spec.name == "deploy"
        assert len(spec.tasks) == 2

        spec2 = loader.load("pipelines/simple.yaml")
        assert spec2.name == "simple"

    def test_load_prefix_with_subdir(self, setup_project, tmp_project):
        subdir = tmp_project / "pipelines" / "nested"
        subdir.mkdir()
        nested_yaml = subdir / "inner.yaml"
        nested_yaml.write_text("name: inner\noptions: {}\ntasks:\n  - name: t1\n    command: echo nested\n")
        try:
            loader = PipelineLoader(tmp_project / "pipelines")
            spec = loader.load("pipelines/nested/inner.yaml")
            assert spec.name == "inner"
            assert spec.tasks[0].name == "t1"
        finally:
            nested_yaml.unlink()
            subdir.rmdir()

    def test_load_all(self, setup_project, tmp_project):
        loader = PipelineLoader(tmp_project / "pipelines")
        all_pipelines = loader.load_all()
        assert "deploy" in all_pipelines
        assert "simple" in all_pipelines

    def test_not_found(self, setup_project, tmp_project):
        loader = PipelineLoader(tmp_project / "pipelines")
        with pytest.raises(FileNotFoundError):
            loader.load("nonexistent.yaml")

    def test_empty_file(self, tmp_path):
        pipelines_dir = tmp_path / "pipelines"
        pipelines_dir.mkdir()
        empty_file = pipelines_dir / "empty.yaml"
        empty_file.write_text("")
        loader = PipelineLoader(pipelines_dir)
        with pytest.raises(ValueError, match="empty"):
            loader.load("empty.yaml")

    def test_load_all_no_dir(self, tmp_path):
        loader = PipelineLoader(tmp_path / "nonexistent")
        result = loader.load_all()
        assert result == {}

    def test_load_with_env_subst(self, tmp_path):
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

    def test_load_absolute_path(self, tmp_path):
        pipelines_dir = tmp_path / "pipelines"
        pipelines_dir.mkdir(parents=True, exist_ok=True)
        yaml_file = pipelines_dir / "absolute.yaml"
        yaml_file.write_text("name: absolute\noptions: {}\ntasks:\n  - name: t1\n    command: echo abs\n")
        loader = PipelineLoader(pipelines_dir)
        spec = loader.load("absolute.yaml")
        assert spec.name == "absolute"

    def test_load_all_includes_yml(self, tmp_path):
        pipelines_dir = tmp_path / "pipelines"
        pipelines_dir.mkdir()
        yml_file = pipelines_dir / "test.yml"
        yml_file.write_text("name: yml_test\noptions: {}\ntasks:\n  - name: t1\n    command: echo yml\n")
        loader = PipelineLoader(pipelines_dir)
        result = loader.load_all()
        assert "yml_test" in result


class TestAgentLoader:
    def test_load(self, setup_project, tmp_project):
        loader = AgentLoader(tmp_project / "agents")
        data = loader.load("staging-server")
        assert data["host"] == "127.0.0.1"
        assert data["port"] == 22
        assert data["username"] == "test"

    def test_not_found(self, setup_project, tmp_project):
        loader = AgentLoader(tmp_project / "agents")
        with pytest.raises(FileNotFoundError):
            loader.load("nonexistent")

    def test_load_all(self, setup_project, tmp_project):
        loader = AgentLoader(tmp_project / "agents")
        all_agents = loader.load_all()
        assert "staging-server" in all_agents

    def test_load_all_no_dir(self, tmp_path):
        loader = AgentLoader(tmp_path / "nonexistent")
        result = loader.load_all()
        assert result == {}

    def test_load_all_includes_yml(self, tmp_path):
        agents_dir = tmp_path / "agents"
        agents_dir.mkdir()
        yml_file = agents_dir / "test-agent.yml"
        yml_file.write_text("host: 1.2.3.4\nport: 22\nusername: test\n")
        loader = AgentLoader(agents_dir)
        result = loader.load_all()
        assert "test-agent" in result

    def test_empty_yaml(self, tmp_path):
        agents_dir = tmp_path / "agents"
        agents_dir.mkdir()
        empty_file = agents_dir / "empty.yaml"
        empty_file.write_text("")
        loader = AgentLoader(agents_dir)
        with pytest.raises(ValueError, match="empty"):
            loader.load("empty")

    def test_load_all_with_exception(self, tmp_path):
        agents_dir = tmp_path / "agents"
        agents_dir.mkdir()
        bad_file = agents_dir / "bad.yaml"
        bad_file.write_text("{invalid: yaml: : }")
        loader = AgentLoader(agents_dir)
        result = loader.load_all()
        assert result == {}

    def test_load_yml_extension(self, tmp_path):
        agents_dir = tmp_path / "agents"
        agents_dir.mkdir()
        yml_file = agents_dir / "test-agent.yml"
        yml_file.write_text("host: 5.6.7.8\nport: 2222\nusername: test\n")
        loader = AgentLoader(agents_dir)
        data = loader.load("test-agent")
        assert data["host"] == "5.6.7.8"


class TestCredentialLoader:
    def test_load(self, setup_project, tmp_project):
        loader = CredentialLoader(tmp_project / "credentials")
        data = loader.load("default-cred")
        assert data["password"] == "testpass"

    def test_not_found(self, setup_project, tmp_project):
        loader = CredentialLoader(tmp_project / "credentials")
        with pytest.raises(FileNotFoundError):
            loader.load("nonexistent")

    def test_load_all_no_dir(self, tmp_path):
        loader = CredentialLoader(tmp_path / "nonexistent")
        result = loader.load_all()
        assert result == {}

    def test_load_all_includes_yml(self, tmp_path):
        creds_dir = tmp_path / "credentials"
        creds_dir.mkdir()
        yml_file = creds_dir / "test-cred.yml"
        yml_file.write_text("password: testpass\n")
        loader = CredentialLoader(creds_dir)
        result = loader.load_all()
        assert "test-cred" in result

    def test_empty_yaml(self, tmp_path):
        creds_dir = tmp_path / "credentials"
        creds_dir.mkdir()
        empty_file = creds_dir / "empty.yaml"
        empty_file.write_text("")
        loader = CredentialLoader(creds_dir)
        with pytest.raises(ValueError, match="empty"):
            loader.load("empty")

    def test_load_all_with_exception(self, tmp_path):
        creds_dir = tmp_path / "credentials"
        creds_dir.mkdir()
        bad_file = creds_dir / "bad.yaml"
        bad_file.write_text("{invalid: yaml: : }")
        loader = CredentialLoader(creds_dir)
        result = loader.load_all()
        assert result == {}

    def test_load_yml_extension(self, tmp_path):
        creds_dir = tmp_path / "credentials"
        creds_dir.mkdir()
        yml_file = creds_dir / "test-cred.yml"
        yml_file.write_text("password: secret\n")
        loader = CredentialLoader(creds_dir)
        data = loader.load("test-cred")
        assert data["password"] == "secret"

    def test_password_warning(self, tmp_path, caplog):
        creds_dir = tmp_path / "credentials"
        creds_dir.mkdir()
        yml_file = creds_dir / "test-cred.yaml"
        yml_file.write_text("password: changeme\n")
        loader = CredentialLoader(creds_dir)
        with caplog.at_level(logging.WARNING):
            data = loader.load("test-cred")
        assert data["password"] == "changeme"
        assert "plaintext password" in caplog.text

    def test_key_path_no_warning(self, tmp_path, caplog):
        creds_dir = tmp_path / "credentials"
        creds_dir.mkdir()
        yml_file = creds_dir / "key-cred.yaml"
        yml_file.write_text("key_path: ~/.ssh/deploy_key\n")
        loader = CredentialLoader(creds_dir)
        with caplog.at_level(logging.WARNING):
            data = loader.load("key-cred")
        assert data["key_path"] == "~/.ssh/deploy_key"
        assert "plaintext password" not in caplog.text


class TestSubstituteEnvVars:
    def test_simple(self):
        env = {"APP_ENV": "production", "TAG": "v1.0"}
        result = substitute_env_vars("echo ${APP_ENV} ${TAG}", env)
        assert result == "echo production v1.0"

    def test_missing(self):
        env = {}
        result = substitute_env_vars("echo ${MISSING}", env)
        assert result == "echo ${MISSING}"

    def test_dict(self):
        env = {"KEY": "val"}
        data = {"command": "echo ${KEY}", "nested": {"val": "${KEY}"}}
        result = substitute_env_vars(data, env)
        assert result["command"] == "echo val"
        assert result["nested"]["val"] == "val"

    def test_list(self):
        env = {"X": "1"}
        data = ["${X}", "static"]
        result = substitute_env_vars(data, env)
        assert result == ["1", "static"]

    def test_no_match(self):
        result = substitute_env_vars("no vars here", {})
        assert result == "no vars here"

    def test_int(self):
        result = substitute_env_vars(42, {})
        assert result == 42
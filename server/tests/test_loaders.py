import pytest

from taskpps.loaders.agent_loader import AgentLoader
from taskpps.loaders.credential_loader import CredentialLoader
from taskpps.loaders.pipeline_loader import PipelineLoader, substitute_env_vars


def test_substitute_env_vars():
    env = {"APP_ENV": "production", "TAG": "v1.0"}
    result = substitute_env_vars("echo ${APP_ENV} ${TAG}", env)
    assert result == "echo production v1.0"


def test_substitute_env_vars_missing():
    env = {}
    result = substitute_env_vars("echo ${MISSING}", env)
    assert result == "echo ${MISSING}"


def test_substitute_env_vars_dict():
    env = {"KEY": "val"}
    data = {"command": "echo ${KEY}", "nested": {"val": "${KEY}"}}
    result = substitute_env_vars(data, env)
    assert result["command"] == "echo val"
    assert result["nested"]["val"] == "val"


def test_substitute_env_vars_list():
    env = {"X": "1"}
    data = ["${X}", "static"]
    result = substitute_env_vars(data, env)
    assert result == ["1", "static"]


def test_pipeline_loader_load(setup_project, tmp_project):
    loader = PipelineLoader(tmp_project / "pipelines")
    spec = loader.load("deploy.yaml")
    assert spec.name == "deploy"
    assert len(spec.tasks) == 2
    assert spec.tasks[0].name == "step1"
    assert spec.tasks[1].depends_on == ["step1"]


def test_pipeline_loader_load_with_pipelines_prefix(setup_project, tmp_project):
    """fix: ppsctl run pipelines/deploy.yaml 不应报 流水线文件未找到"""
    loader = PipelineLoader(tmp_project / "pipelines")
    spec = loader.load("pipelines/deploy.yaml")
    assert spec.name == "deploy"
    assert len(spec.tasks) == 2

    spec2 = loader.load("pipelines/simple.yaml")
    assert spec2.name == "simple"


def test_pipeline_loader_load_prefix_with_subdir(setup_project, tmp_project):
    """子目录中带 pipelines/ 前缀也应正常工作"""
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


def test_pipeline_loader_load_all(setup_project, tmp_project):
    loader = PipelineLoader(tmp_project / "pipelines")
    all_pipelines = loader.load_all()
    assert "deploy" in all_pipelines
    assert "simple" in all_pipelines


def test_pipeline_loader_not_found(setup_project, tmp_project):
    loader = PipelineLoader(tmp_project / "pipelines")
    with pytest.raises(FileNotFoundError):
        loader.load("nonexistent.yaml")


def test_agent_loader(setup_project, tmp_project):
    loader = AgentLoader(tmp_project / "agents")
    data = loader.load("staging-server")
    assert data["host"] == "127.0.0.1"
    assert data["port"] == 22
    assert data["username"] == "test"


def test_agent_loader_not_found(setup_project, tmp_project):
    loader = AgentLoader(tmp_project / "agents")
    with pytest.raises(FileNotFoundError):
        loader.load("nonexistent")


def test_agent_loader_load_all(setup_project, tmp_project):
    loader = AgentLoader(tmp_project / "agents")
    all_agents = loader.load_all()
    assert "staging-server" in all_agents


def test_credential_loader(setup_project, tmp_project):
    loader = CredentialLoader(tmp_project / "credentials")
    data = loader.load("default-cred")
    assert data["password"] == "testpass"


def test_credential_loader_not_found(setup_project, tmp_project):
    loader = CredentialLoader(tmp_project / "credentials")
    with pytest.raises(FileNotFoundError):
        loader.load("nonexistent")

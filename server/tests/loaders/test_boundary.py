from __future__ import annotations

import pytest

from taskpps.loaders.agent_loader import AgentLoader
from taskpps.loaders.credential_loader import CredentialLoader
from taskpps.loaders.pipeline_loader import PipelineLoader


class TestPipelineLoaderBoundary:
    def test_load_nonexistent_file(self, tmp_path):
        loader = PipelineLoader(base_dir=tmp_path)
        with pytest.raises(FileNotFoundError):
            loader.load("nonexistent.yaml")

    def test_load_empty_file(self, tmp_path):
        pipeline_file = tmp_path / "empty.yaml"
        pipeline_file.write_text("")
        loader = PipelineLoader(base_dir=tmp_path)
        with pytest.raises(ValueError):
            loader.load("empty.yaml")

    def test_load_minimal_pipeline(self, tmp_path):
        pipeline_file = tmp_path / "minimal.yaml"
        pipeline_file.write_text("name: minimal\n")
        loader = PipelineLoader(base_dir=tmp_path)
        pipeline = loader.load("minimal.yaml")
        assert pipeline.name == "minimal"

    def test_load_pipeline_with_tasks(self, tmp_path):
        pipeline_file = tmp_path / "with_tasks.yaml"
        pipeline_file.write_text(
            "name: build\ntasks:\n  - name: step1\n    command: echo hello\n  - name: step2\n    command: echo world\n"
        )
        loader = PipelineLoader(base_dir=tmp_path)
        pipeline = loader.load("with_tasks.yaml")
        assert len(pipeline.tasks) == 2

    def test_load_pipeline_with_env(self, tmp_path):
        pipeline_file = tmp_path / "with_env.yaml"
        pipeline_file.write_text(
            "name: env_test\nconfig:\n  env:\n    GLOBAL: value\ntasks:\n  - name: step1\n    command: echo $GLOBAL\n"
        )
        loader = PipelineLoader(base_dir=tmp_path)
        pipeline = loader.load("with_env.yaml")
        assert pipeline.config.env == {"GLOBAL": "value"}

    def test_load_pipeline_with_options(self, tmp_path):
        pipeline_file = tmp_path / "with_options.yaml"
        pipeline_file.write_text(
            "name: options_test\n"
            "options:\n"
            "  on_failure: continue\n"
            "  timeout: 120\n"
            "tasks:\n"
            "  - name: step1\n"
            "    command: echo hi\n"
        )
        loader = PipelineLoader(base_dir=tmp_path)
        pipeline = loader.load("with_options.yaml")
        assert pipeline.options.on_failure == "continue"

    def test_load_pipeline_with_depends_on(self, tmp_path):
        pipeline_file = tmp_path / "with_deps.yaml"
        pipeline_file.write_text(
            "name: dep_test\n"
            "tasks:\n"
            "  - name: step1\n"
            "    command: echo 1\n"
            "  - name: step2\n"
            "    command: echo 2\n"
            "    depends_on:\n"
            "      - step1\n"
        )
        loader = PipelineLoader(base_dir=tmp_path)
        pipeline = loader.load("with_deps.yaml")
        assert pipeline.tasks[1].depends_on == ["step1"]

    def test_load_nested_pipeline(self, tmp_path):
        subdir = tmp_path / "nested"
        subdir.mkdir()
        pipeline_file = subdir / "deploy.yaml"
        pipeline_file.write_text("name: nested_deploy\n")
        loader = PipelineLoader(base_dir=tmp_path)
        pipeline = loader.load("nested/deploy.yaml")
        assert pipeline.name == "nested_deploy"

    def test_path_traversal_prevented(self, tmp_path):
        loader = PipelineLoader(base_dir=tmp_path)
        with pytest.raises(FileNotFoundError):
            loader.load("../outside.yaml")

    def test_load_all_empty_dir(self, tmp_path):
        loader = PipelineLoader(base_dir=tmp_path)
        result = loader.load_all()
        assert result == {}

    def test_load_all_with_files(self, tmp_path):
        (tmp_path / "a.yaml").write_text("name: a\n")
        (tmp_path / "b.yaml").write_text("name: b\n")
        loader = PipelineLoader(base_dir=tmp_path)
        result = loader.load_all()
        assert len(result) == 2
        assert "a" in result
        assert "b" in result


class TestAgentLoaderBoundary:
    def test_load_nonexistent_file(self, tmp_path):
        loader = AgentLoader(base_dir=tmp_path)
        with pytest.raises(FileNotFoundError):
            loader.load("nonexistent")

    def test_load_minimal_agent(self, tmp_path):
        agent_file = tmp_path / "test.yaml"
        agent_file.write_text("id: test-agent\nhost: 127.0.0.1\n")
        loader = AgentLoader(base_dir=tmp_path)
        agent = loader.load("test")
        assert agent["id"] == "test-agent"
        assert agent["host"] == "127.0.0.1"

    def test_load_yml_extension(self, tmp_path):
        agent_file = tmp_path / "test.yml"
        agent_file.write_text("id: yml-agent\nhost: 192.168.1.1\n")
        loader = AgentLoader(base_dir=tmp_path)
        agent = loader.load("test")
        assert agent["id"] == "yml-agent"

    def test_load_empty_file(self, tmp_path):
        agent_file = tmp_path / "test.yaml"
        agent_file.write_text("")
        loader = AgentLoader(base_dir=tmp_path)
        with pytest.raises(ValueError):
            loader.load("test")

    def test_get_nonexistent(self, tmp_path):
        loader = AgentLoader(base_dir=tmp_path)
        assert loader.get("nonexistent") is None

    def test_get_field(self, tmp_path):
        agent_file = tmp_path / "test-agent.yaml"
        agent_file.write_text("id: test-agent\nhost: 127.0.0.1\nport: 22\n")
        loader = AgentLoader(base_dir=tmp_path)
        loader.load_all()
        host = loader.get_field("test-agent", "host")
        assert host == "127.0.0.1"

    def test_get_field_missing(self, tmp_path):
        agent_file = tmp_path / "test.yaml"
        agent_file.write_text("id: test-agent\nhost: 127.0.0.1\n")
        loader = AgentLoader(base_dir=tmp_path)
        with pytest.raises(KeyError):
            loader.get_field("test-agent", "nonexistent")

    def test_get_field_agent_not_found(self, tmp_path):
        loader = AgentLoader(base_dir=tmp_path)
        with pytest.raises(KeyError):
            loader.get_field("nonexistent", "host")

    def test_clear_cache(self, tmp_path):
        agent_file = tmp_path / "test.yaml"
        agent_file.write_text("id: test-agent\nhost: 127.0.0.1\n")
        loader = AgentLoader(base_dir=tmp_path)
        loader.load_all()
        loader.clear_cache()
        assert loader._cache is None

    def test_load_all_empty_dir(self, tmp_path):
        loader = AgentLoader(base_dir=tmp_path)
        result = loader.load_all()
        assert result == {}


class TestCredentialLoaderBoundary:
    def test_load_nonexistent_file(self, tmp_path):
        loader = CredentialLoader(base_dir=tmp_path)
        with pytest.raises(FileNotFoundError):
            loader.load("nonexistent")

    def test_load_minimal_credential(self, tmp_path):
        cred_file = tmp_path / "test.yaml"
        cred_file.write_text("id: test-cred\ntype: password\n")
        loader = CredentialLoader(base_dir=tmp_path)
        cred = loader.load("test")
        assert cred["id"] == "test-cred"
        assert cred["type"] == "password"

    def test_load_empty_file(self, tmp_path):
        cred_file = tmp_path / "test.yaml"
        cred_file.write_text("")
        loader = CredentialLoader(base_dir=tmp_path)
        with pytest.raises(ValueError):
            loader.load("test")

    def test_get_nonexistent(self, tmp_path):
        loader = CredentialLoader(base_dir=tmp_path)
        assert loader.get("nonexistent") is None

    def test_get_field(self, tmp_path):
        cred_file = tmp_path / "test-cred.yaml"
        cred_file.write_text("id: test-cred\ntype: password\nusername: admin\n")
        loader = CredentialLoader(base_dir=tmp_path)
        loader.load_all()
        username = loader.get_field("test-cred", "username")
        assert username == "admin"

    def test_get_field_missing(self, tmp_path):
        cred_file = tmp_path / "test.yaml"
        cred_file.write_text("id: test-cred\ntype: password\n")
        loader = CredentialLoader(base_dir=tmp_path)
        with pytest.raises(KeyError):
            loader.get_field("test-cred", "nonexistent")

    def test_get_field_credential_not_found(self, tmp_path):
        loader = CredentialLoader(base_dir=tmp_path)
        with pytest.raises(KeyError):
            loader.get_field("nonexistent", "type")

    def test_clear_cache(self, tmp_path):
        cred_file = tmp_path / "test.yaml"
        cred_file.write_text("id: test-cred\ntype: password\n")
        loader = CredentialLoader(base_dir=tmp_path)
        loader.load_all()
        loader.clear_cache()
        assert loader._cache is None

    def test_load_all_empty_dir(self, tmp_path):
        loader = CredentialLoader(base_dir=tmp_path)
        result = loader.load_all()
        assert result == {}

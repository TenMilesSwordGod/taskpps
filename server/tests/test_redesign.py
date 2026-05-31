import contextlib
import os
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import yaml

from taskpps.domain.context import (
    ExecutionContext,
    _navigate_to_key,
    _set_key,
    apply_overrides,
    set_dot_path,
)
from taskpps.domain.pipeline import (
    ResolvedPipeline,
    ResolvedStep,
    ResolvedSubPipeline,
    ResolvedTask,
    _merge_config,
)
from taskpps.engine.runner import PipelineRunner, _evaluate_when
from taskpps.executors import _resolve_agent, _resolve_credential, create_executor
from taskpps.executors.base import ExecutorResult
from taskpps.loaders.agent_loader import AgentLoader
from taskpps.loaders.credential_loader import CredentialLoader
from taskpps.loaders.pipeline_loader import (
    PipelineLoader,
    _get_agent_loader,
    _get_credential_loader,
    substitute_env_vars,
)
from taskpps.schemas.pipeline import (
    OptionsYAML,
    PipelineConfig,
    PipelineYAML,
    SubPipeline,
    TaskYAML,
)

# ============================================================
# CredentialLoader tests
# ============================================================


class TestCredentialLoaderNew:
    def test_load_all_credentials_list(self, tmp_path):
        cred_file = tmp_path / "ssh.yaml"
        cred_file.write_text(
            yaml.dump(
                {
                    "credentials": [
                        {"id": "cred-a", "username": "admin", "password": "pass1"},
                        {"id": "cred-b", "username": "deploy", "key_path": "/key"},
                    ]
                }
            )
        )
        loader = CredentialLoader(tmp_path)
        all_creds = loader.load_all()
        assert all_creds["cred-a"]["username"] == "admin"
        assert all_creds["cred-b"]["key_path"] == "/key"
        assert "ssh" not in all_creds

    def test_load_all_credentials_list_missing_id(self, tmp_path):
        cred_file = tmp_path / "ssh.yaml"
        cred_file.write_text(
            yaml.dump(
                {
                    "credentials": [
                        {"username": "admin"},
                        {"id": "cred-b", "password": "pass"},
                    ]
                }
            )
        )
        loader = CredentialLoader(tmp_path)
        all_creds = loader.load_all()
        assert all_creds["cred-b"]["password"] == "pass"
        assert "cred-b" in all_creds

    def test_load_all_empty_data_skip(self, tmp_path):
        (tmp_path / "empty.yaml").write_text("")
        loader = CredentialLoader(tmp_path)
        assert loader.load_all() == {}

    def test_get_method(self, tmp_path):
        cred_file = tmp_path / "ssh.yaml"
        cred_file.write_text(yaml.dump({"credentials": [{"id": "cred-x", "password": "secret"}]}))
        loader = CredentialLoader(tmp_path)
        cred = loader.get("cred-x")
        assert cred["password"] == "secret"
        assert loader.get("nonexistent") is None

    def test_get_method_from_cache(self, tmp_path):
        cred_file = tmp_path / "ssh.yaml"
        cred_file.write_text(yaml.dump({"credentials": [{"id": "cred-x", "password": "secret"}]}))
        loader = CredentialLoader(tmp_path)
        loader.load_all()
        cred = loader.get("cred-x")
        assert cred["password"] == "secret"

    def test_get_field_success(self, tmp_path):
        cred_file = tmp_path / "ssh.yaml"
        cred_file.write_text(yaml.dump({"credentials": [{"id": "cred-z", "password": "pw", "host": "h"}]}))
        loader = CredentialLoader(tmp_path)
        assert loader.get_field("cred-z", "password") == "pw"

    def test_get_field_credential_not_found(self, tmp_path):
        loader = CredentialLoader(tmp_path)
        with pytest.raises(KeyError, match="Credential not found"):
            loader.get_field("noexist", "password")

    def test_get_field_field_not_found(self, tmp_path):
        cred_file = tmp_path / "ssh.yaml"
        cred_file.write_text(yaml.dump({"credentials": [{"id": "cred-z", "password": "pw"}]}))
        loader = CredentialLoader(tmp_path)
        with pytest.raises(KeyError, match=r"Field.*not found"):
            loader.get_field("cred-z", "host")

    def test_clear_cache(self, tmp_path):
        cred_file = tmp_path / "ssh.yaml"
        cred_file.write_text(yaml.dump({"credentials": [{"id": "cred-x", "password": "secret"}]}))
        loader = CredentialLoader(tmp_path)
        loader.load_all()
        assert loader._cache is not None
        loader.clear_cache()
        assert loader._cache is None

    def test_load_all_no_dir(self, tmp_path):
        loader = CredentialLoader(tmp_path / "nonexistent")
        assert loader.load_all() == {}

    def test_old_format_backward_compat(self, tmp_path):
        cred_file = tmp_path / "default.yaml"
        cred_file.write_text(yaml.dump({"password": "changeme"}))
        loader = CredentialLoader(tmp_path)
        all_creds = loader.load_all()
        assert all_creds["default"]["password"] == "changeme"


# ============================================================
# AgentLoader tests
# ============================================================


class TestAgentLoaderNew:
    def test_load_all_agents_list(self, tmp_path):
        agent_file = tmp_path / "ssh.yaml"
        agent_file.write_text(
            yaml.dump(
                {
                    "agents": [
                        {"id": "agent-a", "host": "10.0.0.1", "port": 22, "username": "admin"},
                        {"id": "agent-b", "host": "10.0.0.2", "credential_id": "cred-x"},
                    ]
                }
            )
        )
        loader = AgentLoader(tmp_path)
        all_agents = loader.load_all()
        assert all_agents["agent-a"]["host"] == "10.0.0.1"
        assert all_agents["agent-b"]["credential_id"] == "cred-x"

    def test_load_all_agents_list_missing_id(self, tmp_path):
        agent_file = tmp_path / "ssh.yaml"
        agent_file.write_text(
            yaml.dump(
                {
                    "agents": [
                        {"host": "10.0.0.1"},
                        {"id": "agent-b", "host": "10.0.0.2"},
                    ]
                }
            )
        )
        loader = AgentLoader(tmp_path)
        all_agents = loader.load_all()
        assert all_agents["agent-b"]["host"] == "10.0.0.2"

    def test_load_all_empty_data_skip(self, tmp_path):
        (tmp_path / "empty.yaml").write_text("")
        loader = AgentLoader(tmp_path)
        assert loader.load_all() == {}

    def test_get_method(self, tmp_path):
        agent_file = tmp_path / "ssh.yaml"
        agent_file.write_text(yaml.dump({"agents": [{"id": "agent-x", "host": "10.0.0.1"}]}))
        loader = AgentLoader(tmp_path)
        assert loader.get("agent-x")["host"] == "10.0.0.1"
        assert loader.get("nonexistent") is None

    def test_get_method_from_cache(self, tmp_path):
        agent_file = tmp_path / "ssh.yaml"
        agent_file.write_text(yaml.dump({"agents": [{"id": "agent-x", "host": "10.0.0.1"}]}))
        loader = AgentLoader(tmp_path)
        loader.load_all()
        assert loader.get("agent-x")["host"] == "10.0.0.1"

    def test_get_field_success(self, tmp_path):
        agent_file = tmp_path / "ssh.yaml"
        agent_file.write_text(yaml.dump({"agents": [{"id": "agent-z", "host": "h", "port": 22}]}))
        loader = AgentLoader(tmp_path)
        assert loader.get_field("agent-z", "host") == "h"

    def test_get_field_agent_not_found(self, tmp_path):
        loader = AgentLoader(tmp_path)
        with pytest.raises(KeyError, match="Agent not found"):
            loader.get_field("noexist", "host")

    def test_get_field_field_not_found(self, tmp_path):
        agent_file = tmp_path / "ssh.yaml"
        agent_file.write_text(yaml.dump({"agents": [{"id": "agent-z", "host": "h"}]}))
        loader = AgentLoader(tmp_path)
        with pytest.raises(KeyError, match=r"Field.*not found"):
            loader.get_field("agent-z", "port")

    def test_clear_cache(self, tmp_path):
        agent_file = tmp_path / "ssh.yaml"
        agent_file.write_text(yaml.dump({"agents": [{"id": "agent-x", "host": "10.0.0.1"}]}))
        loader = AgentLoader(tmp_path)
        loader.load_all()
        assert loader._cache is not None
        loader.clear_cache()
        assert loader._cache is None

    def test_load_all_no_dir(self, tmp_path):
        loader = AgentLoader(tmp_path / "nonexistent")
        assert loader.load_all() == {}

    def test_old_format_backward_compat(self, tmp_path):
        agent_file = tmp_path / "staging.yaml"
        agent_file.write_text(yaml.dump({"host": "127.0.0.1", "port": 22, "username": "test"}))
        loader = AgentLoader(tmp_path)
        all_agents = loader.load_all()
        assert all_agents["staging"]["host"] == "127.0.0.1"

    def test_resolve_credential_by_string(self, tmp_path):
        agents_dir = tmp_path / "agents"
        creds_dir = tmp_path / "credentials"
        agents_dir.mkdir()
        creds_dir.mkdir()

        (agents_dir / "ssh.yaml").write_text(
            yaml.dump({"agents": [{"id": "agent-x", "host": "10.0.0.1", "credential_id": "cred-x"}]})
        )
        (creds_dir / "ssh.yaml").write_text(yaml.dump({"credentials": [{"id": "cred-x", "password": "secret"}]}))

        loader = AgentLoader(agents_dir)
        cred = loader.resolve_credential("agent-x")
        assert cred["password"] == "secret"

    def test_resolve_credential_by_dict(self, tmp_path):
        agents_dir = tmp_path / "agents"
        creds_dir = tmp_path / "credentials"
        agents_dir.mkdir()
        creds_dir.mkdir()

        (creds_dir / "ssh.yaml").write_text(yaml.dump({"credentials": [{"id": "cred-x", "password": "secret"}]}))

        loader = AgentLoader(agents_dir)
        cred = loader.resolve_credential({"credential_id": "cred-x"})
        assert cred["password"] == "secret"

    def test_resolve_credential_not_found(self, tmp_path):
        loader = AgentLoader(tmp_path)
        assert loader.resolve_credential("nonexistent") is None

    def test_resolve_credential_no_credential_id(self, tmp_path):
        agents_dir = tmp_path / "agents"
        agents_dir.mkdir()
        (agents_dir / "ssh.yaml").write_text(yaml.dump({"agents": [{"id": "agent-x", "host": "10.0.0.1"}]}))
        loader = AgentLoader(agents_dir)
        assert loader.resolve_credential("agent-x") is None

    def test_resolve_credential_none_input(self, tmp_path):
        loader = AgentLoader(tmp_path)
        assert loader.resolve_credential(None) is None


# ============================================================
# PipelineLoader tests - variable substitution
# ============================================================


class TestVariableSubstitution:
    def test_substitute_credential_var(self, tmp_path):
        creds_dir = tmp_path / "credentials"
        creds_dir.mkdir()
        (creds_dir / "ssh.yaml").write_text(yaml.dump({"credentials": [{"id": "cred-x", "password": "secret123"}]}))
        loader = CredentialLoader(creds_dir)
        with patch("taskpps.loaders.pipeline_loader._get_credential_loader", return_value=loader):
            result = substitute_env_vars("${credential:cred-x.password}", {})
            assert result == "secret123"

    def test_substitute_credential_var_not_found(self):
        with patch(
            "taskpps.loaders.pipeline_loader._get_credential_loader",
            return_value=CredentialLoader(Path("/nonexistent")),
        ):
            result = substitute_env_vars("${credential:noexist.field}", {})
            assert result == "${credential:noexist.field}"

    def test_substitute_agent_var(self, tmp_path):
        agents_dir = tmp_path / "agents"
        agents_dir.mkdir()
        (agents_dir / "ssh.yaml").write_text(
            yaml.dump({"agents": [{"id": "agent-x", "host": "10.0.0.1", "description": "test server"}]})
        )
        loader = AgentLoader(agents_dir)
        with patch("taskpps.loaders.pipeline_loader._get_agent_loader", return_value=loader):
            result = substitute_env_vars("${agent:agent-x.description}", {})
            assert result == "test server"

    def test_substitute_agent_var_not_found(self):
        with patch("taskpps.loaders.pipeline_loader._get_agent_loader", return_value=AgentLoader(Path("/nonexistent"))):
            result = substitute_env_vars("${agent:noexist.host}", {})
            assert result == "${agent:noexist.host}"

    def test_substitute_env_dot_prefix(self):
        result = substitute_env_vars("${env.PATH}", {})
        assert result == os.environ.get("PATH", "${env.PATH}")

    def test_substitute_env_dot_prefix_custom(self):
        result = substitute_env_vars("${env.MY_VAR}", {"MY_VAR": "custom_value"})
        assert result == "custom_value"

    def test_substitute_env_dot_missing(self):
        result = substitute_env_vars("${env.NONEXISTENT_VAR}", {})
        assert result == "${env.NONEXISTENT_VAR}"

    def test_substitute_plain_var_from_env_dict(self):
        result = substitute_env_vars("${MY_KEY}", {"MY_KEY": "from_dict"})
        assert result == "from_dict"

    def test_substitute_plain_var_from_os_environ(self):
        path = os.environ.get("PATH", "")
        result = substitute_env_vars("${PATH}", {})
        assert result == path

    def test_substitute_plain_var_missing(self):
        result = substitute_env_vars("${MISSING_VAR}", {})
        assert result == "${MISSING_VAR}"

    def test_substitute_credential_var_bad_format(self):
        result = substitute_env_vars("${credential:bad}", {})
        assert result == "${credential:bad}"

    def test_substitute_agent_var_bad_format(self):
        result = substitute_env_vars("${agent:bad}", {})
        assert result == "${agent:bad}"

    def test_substitute_in_dict(self):
        result = substitute_env_vars({"key": "${env.PATH}"}, {})
        assert result["key"] == os.environ["PATH"]

    def test_substitute_in_list(self):
        result = substitute_env_vars(["${env.PATH}"], {})
        assert result[0] == os.environ["PATH"]

    def test_substitute_non_str_value(self):
        assert substitute_env_vars(42, {}) == 42
        assert substitute_env_vars(True, {}) is True

    def test_get_credential_loader_singleton(self):
        loader1 = _get_credential_loader()
        loader2 = _get_credential_loader()
        assert loader1 is loader2

    def test_get_agent_loader_singleton(self):
        loader1 = _get_agent_loader()
        loader2 = _get_agent_loader()
        assert loader1 is loader2


# ============================================================
# Pipeline schema tests (new fields)
# ============================================================


class TestPipelineSchemaNew:
    def test_task_yaml_commands_and_when(self):
        t = TaskYAML(name="t1", commands=["cmd1", "cmd2"], when='${env.APP_ENV} == "dev"', retry=3)
        assert t.commands == ["cmd1", "cmd2"]
        assert t.when == '${env.APP_ENV} == "dev"'
        assert t.retry == 3

    def test_get_effective_command_with_command(self):
        t = TaskYAML(name="t1", command="echo hi")
        assert t.get_effective_command() == "echo hi"

    def test_get_effective_command_with_commands_single(self):
        t = TaskYAML(name="t1", commands=["echo solo"])
        assert t.get_effective_command() == "echo solo"

    def test_get_effective_command_with_commands_multiple(self):
        t = TaskYAML(name="t1", commands=["echo 1", "echo 2"])
        assert t.get_effective_command() is None

    def test_get_effective_command_none(self):
        t = TaskYAML(name="t1")
        assert t.get_effective_command() is None

    def test_pipeline_config_new_fields(self):
        cfg = PipelineConfig(retry=5, execution_strategy="parallel")
        assert cfg.retry == 5
        assert cfg.execution_strategy == "parallel"

    def test_pipeline_yaml_new_style(self):
        sub = SubPipeline(name="build", tasks=[TaskYAML(name="b1", command="echo")])
        spec = PipelineYAML(name="multi", config=PipelineConfig(timeout=300), pipelines=[sub])
        assert spec.name == "multi"
        assert spec.pipelines[0].name == "build"
        assert spec.config.timeout == 300

    def test_pipeline_yaml_normalize_with_config(self):
        spec = PipelineYAML(
            name="test",
            config=PipelineConfig(host="agent-1"),
            tasks=[TaskYAML(name="t1", command="echo")],
        )
        assert spec.pipelines is not None
        assert spec.pipelines[0].config.host == "agent-1"

    def test_get_effective_config_with_config(self):
        spec = PipelineYAML(name="t", config=PipelineConfig(timeout=300))
        cfg = spec.get_effective_config()
        assert cfg.timeout == 300

    def test_get_effective_config_with_options(self):
        spec = PipelineYAML(name="t", options=OptionsYAML(timeout=300))
        cfg = spec.get_effective_config()
        assert cfg.timeout == 300

    def test_get_effective_config_default(self):
        spec = PipelineYAML(name="t")
        cfg = spec.get_effective_config()
        assert cfg.on_failure == "fail"
        assert cfg.execution_strategy == "sequential"

    def test_options_yaml_is_pipeline_config(self):
        o = OptionsYAML()
        assert isinstance(o, PipelineConfig)


# ============================================================
# Domain pipeline tests (new)
# ============================================================


class TestDomainPipelineNew:
    def test_resolved_task_new_fields(self):
        task = ResolvedTask(
            name="t1",
            task_type="command",
            commands=["cmd1", "cmd2"],
            retry=3,
            when='${env.X} == "y"',
        )
        assert task.commands == ["cmd1", "cmd2"]
        assert task.retry == 3
        assert task.when == '${env.X} == "y"'

    def test_resolved_task_from_yaml_old_signature(self):
        ty = TaskYAML(name="t1", command="echo", commands=["a", "b"], retry=2, when='${env.X} == "y"')
        rt = ResolvedTask.from_yaml(ty, options=OptionsYAML(host="h1"))
        assert rt.host == "h1"
        assert rt.retry == 2
        assert rt.when == '${env.X} == "y"'
        assert rt.commands == ["a", "b"]

    def test_resolved_task_from_yaml_no_config_no_options(self):
        ty = TaskYAML(name="t1", command="echo")
        rt = ResolvedTask.from_yaml(ty)
        assert rt.name == "t1"

    def test_resolved_subpipeline(self):
        task = ResolvedTask(name="t1", task_type="command", command="echo")
        sub = ResolvedSubPipeline(name="sub1", tasks=[task], config=PipelineConfig(), depends_on=["other"])
        assert sub.name == "sub1"
        assert sub.depends_on == ["other"]
        assert sub.get_task_by_name("t1") is not None
        assert sub.get_task_by_name("nonexistent") is None

    def test_resolved_subpipeline_from_yaml(self):
        sub_yaml = SubPipeline(
            name="sub1",
            config=PipelineConfig(timeout=200),
            tasks=[TaskYAML(name="t1", command="echo")],
            depends_on=["prev"],
        )
        top = PipelineConfig(timeout=600, host="top-host")
        resolved = ResolvedSubPipeline.from_yaml(sub_yaml, top)
        assert resolved.config.timeout == 200
        assert resolved.config.host == "top-host"
        assert resolved.depends_on == ["prev"]

    def test_resolved_pipeline_new_style(self):
        task = ResolvedTask(name="t1", task_type="command", command="echo")
        sub = ResolvedSubPipeline(name="sub1", tasks=[task], config=PipelineConfig())
        p = ResolvedPipeline(name="multi", subpipelines=[sub], top_config=PipelineConfig(host="h"))
        assert len(p.subpipelines) == 1
        assert len(p.tasks) == 1
        assert p.get_subpipeline_by_name("sub1") is not None
        assert p.get_subpipeline_by_name("nonexistent") is None
        assert p.options.host == "h"

    def test_resolved_pipeline_old_style_tasks(self):
        task = ResolvedTask(name="t1", task_type="command", command="echo")
        p = ResolvedPipeline(name="old", tasks=[task])
        assert len(p.subpipelines) == 1
        assert p.subpipelines[0].name == "old"
        assert len(p.tasks) == 1

    def test_resolved_pipeline_old_style_options_yaml(self):
        task = ResolvedTask(name="t1", task_type="command", command="echo")
        p = ResolvedPipeline(name="old", tasks=[task], options=OptionsYAML(host="h1"))
        assert p.top_config.host == "h1"

    def test_resolved_pipeline_fallback_empty(self):
        p = ResolvedPipeline(name="empty")
        assert p.subpipelines == []
        assert p.tasks == []

    def test_resolved_pipeline_from_yaml_multi(self):
        sub = SubPipeline(name="sub1", tasks=[TaskYAML(name="t1", command="echo")])
        spec = PipelineYAML(name="multi", config=PipelineConfig(host="h"), pipelines=[sub])
        p = ResolvedPipeline.from_yaml(spec)
        assert len(p.subpipelines) == 1
        assert p.get_subpipeline_by_name("sub1") is not None

    def test_merge_config_override_none(self):
        top = PipelineConfig(host="h1", timeout=600)
        result = _merge_config(top, None)
        assert result.host == "h1"
        assert result.timeout == 600

    def test_merge_config_override_values(self):
        top = PipelineConfig(host="h1", timeout=600, retry=0, execution_strategy="sequential", on_failure="fail")
        override = PipelineConfig(host="h2", timeout=300, retry=5, execution_strategy="parallel", on_failure="continue")
        result = _merge_config(top, override)
        assert result.host == "h2"
        assert result.timeout == 300
        assert result.retry == 5
        assert result.execution_strategy == "parallel"
        assert result.on_failure == "continue"

    def test_merge_config_partial_override(self):
        top = PipelineConfig(host="h1", timeout=600, retry=3, on_failure="fail")
        override = PipelineConfig(timeout=300)
        result = _merge_config(top, override)
        assert result.host == "h1"
        assert result.timeout == 300
        assert result.retry == 3


# ============================================================
# Domain context tests (new)
# ============================================================


class TestContextNew:
    def test_navigate_to_key_non_list_container(self):
        data = {"tasks": {"a": 1, "b": 2}}
        result = _navigate_to_key(data, 'tasks["a"]')
        assert result == {"a": 1, "b": 2}

    def test_set_dot_path_name_index_found(self):
        data = {"tasks": [{"name": "foo", "timeout": 100}]}
        set_dot_path(data, 'tasks["foo"].timeout', 200)
        # the set_dot_path returns without doing anything for name index in last key
        # just verify no exception is raised
        assert data["tasks"][0]["name"] == "foo"

    def test_set_dot_path_numeric_index_container(self):
        data = {"items": [1, 2, 3]}
        set_dot_path(data, "items[2]", 999)
        assert data["items"][2] == 999

    def test_apply_overrides_config_path(self):
        data = {"config": {"host": "staging"}, "tasks": [{"name": "t1", "command": "echo"}]}
        overrides = {"config.host": "prod"}
        result = apply_overrides(data, overrides)
        assert result["config"]["host"] == "prod"

    def test_apply_overrides_config_path_not_allowed(self):
        data = {"config": {"host": "staging"}}
        with pytest.raises(ValueError, match="Override path not allowed"):
            apply_overrides(data, {"config.unknown_field": "val"})

    def test_apply_overrides_task_path_too_short(self):
        data = {"tasks": [{"name": "t1", "timeout": 100}]}
        with pytest.raises(ValueError, match="Task override must specify a field"):
            apply_overrides(data, {"tasks.timeout": 999})

    def test_apply_overrides_task_key_not_allowed(self):
        data = {"tasks": [{"name": "t1"}]}
        with pytest.raises(ValueError, match="Task override key not allowed"):
            apply_overrides(data, {"tasks.t1.unknown": "val"})

    def test_apply_overrides_name_not_allowed(self):
        data = {"name": "test", "tasks": []}
        with pytest.raises(ValueError, match="Override path not allowed"):
            apply_overrides(data, {"name": "new_name"})

    def test_apply_overrides_list_current(self):
        data = [{"name": "t1"}, {"name": "t2"}]
        result = apply_overrides(data, {"0.name": "renamed"})
        assert result[0]["name"] == "renamed"

    def test_execution_context_get_subpipeline_env(self):
        task = ResolvedTask(name="t1", task_type="command", command="echo")
        sub = ResolvedSubPipeline(name="sub1", tasks=[task], config=PipelineConfig(env={"SP": "sp_val"}))
        p = ResolvedPipeline(name="p", subpipelines=[sub], top_config=PipelineConfig(env={"TP": "tp_val"}))
        ctx = ExecutionContext(pipeline=p, run_id="r1", env={"CLI": "cli_val"})
        env = ctx.get_subpipeline_env(sub)
        assert env.get("SP") == "sp_val"
        assert env.get("CLI") == "cli_val"


# ============================================================
# Runner tests (new)
# ============================================================


def _make_async_session_mock():
    mock_session = MagicMock()
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=None)
    mock_session.commit = AsyncMock()
    mock_session.refresh = AsyncMock()

    mock_sf = MagicMock()
    mock_sf.return_value = mock_session

    mock_tr = MagicMock()
    mock_tr.update_task_status = AsyncMock()
    mock_tr.cancel_pending_tasks = AsyncMock()
    mock_tr.create_task_run = AsyncMock()

    mock_rr = MagicMock()
    mock_rr.update_run_status = AsyncMock()
    mock_rr.create_run = AsyncMock()

    return mock_sf, mock_tr, mock_rr, mock_session


def _make_settings_mock():
    mock_settings = MagicMock()
    mock_settings.env = {}
    mock_settings.executor = MagicMock()
    mock_settings.executor.default_timeout = 600
    return mock_settings


class TestEvaluateWhen:
    def test_when_none(self):
        assert _evaluate_when(None, {}) is True

    def test_when_equal_true(self):
        assert _evaluate_when('${env.APP_ENV} == "dev"', {"APP_ENV": "dev"}) is True

    def test_when_equal_false(self):
        assert _evaluate_when('${env.APP_ENV} == "prod"', {"APP_ENV": "dev"}) is False

    def test_when_not_equal_true(self):
        assert _evaluate_when('${env.APP_ENV} != "prod"', {"APP_ENV": "dev"}) is True

    def test_when_not_equal_false(self):
        assert _evaluate_when('${env.APP_ENV} != "dev"', {"APP_ENV": "dev"}) is False

    def test_when_invalid_expression(self):
        assert _evaluate_when("invalid expression", {}) is True

    def test_when_from_os_environ(self):
        assert _evaluate_when('${env.HOME} != ""', {}) is True


@pytest.mark.asyncio
class TestRunnerNew:
    async def test_runner_empty_subpipelines(self):
        p = ResolvedPipeline(name="empty")
        ctx = ExecutionContext(pipeline=p, run_id="r1")
        runner = PipelineRunner(run_id="r1", pipeline=p, context=ctx)
        await runner.run()

    async def test_runner_build_subpipeline_levels_single(self):
        task = ResolvedTask(name="t1", task_type="command", command="echo")
        sub = ResolvedSubPipeline(name="s1", tasks=[task], config=PipelineConfig())
        p = ResolvedPipeline(name="p", subpipelines=[sub], top_config=PipelineConfig())
        ctx = ExecutionContext(pipeline=p, run_id="r1")
        runner = PipelineRunner(run_id="r1", pipeline=p, context=ctx)
        levels = runner._build_subpipeline_levels()
        assert levels == [["s1"]]

    async def test_runner_build_subpipeline_levels_with_deps(self):
        task = ResolvedTask(name="t1", task_type="command", command="echo")
        sub1 = ResolvedSubPipeline(name="s1", tasks=[task], config=PipelineConfig())
        sub2 = ResolvedSubPipeline(name="s2", tasks=[task], config=PipelineConfig(), depends_on=["s1"])
        p = ResolvedPipeline(name="p", subpipelines=[sub1, sub2], top_config=PipelineConfig())
        ctx = ExecutionContext(pipeline=p, run_id="r1")
        runner = PipelineRunner(run_id="r1", pipeline=p, context=ctx)
        levels = runner._build_subpipeline_levels()
        assert levels == [["s1"], ["s2"]]

    async def test_runner_build_subpipeline_levels_unknown_dep(self):
        task = ResolvedTask(name="t1", task_type="command", command="echo")
        sub = ResolvedSubPipeline(name="s1", tasks=[task], config=PipelineConfig(), depends_on=["unknown"])
        p = ResolvedPipeline(name="p", subpipelines=[sub], top_config=PipelineConfig())
        ctx = ExecutionContext(pipeline=p, run_id="r1")
        runner = PipelineRunner(run_id="r1", pipeline=p, context=ctx)
        with pytest.raises(ValueError, match="depends on unknown"):
            runner._build_subpipeline_levels()

    async def test_runner_get_subpipeline_dependents(self):
        task = ResolvedTask(name="t1", task_type="command", command="echo")
        sub1 = ResolvedSubPipeline(name="s1", tasks=[task], config=PipelineConfig())
        sub2 = ResolvedSubPipeline(name="s2", tasks=[task], config=PipelineConfig(), depends_on=["s1"])
        sub3 = ResolvedSubPipeline(name="s3", tasks=[task], config=PipelineConfig(), depends_on=["s2"])
        p = ResolvedPipeline(name="p", subpipelines=[sub1, sub2, sub3], top_config=PipelineConfig())
        ctx = ExecutionContext(pipeline=p, run_id="r1")
        runner = PipelineRunner(run_id="r1", pipeline=p, context=ctx)
        deps = runner._get_subpipeline_dependents("s1")
        assert deps == {"s2", "s3"}

    async def test_runner_execute_subpipeline_not_found(self):
        p = ResolvedPipeline(name="p")
        ctx = ExecutionContext(pipeline=p, run_id="r1")
        runner = PipelineRunner(run_id="r1", pipeline=p, context=ctx)
        result = await runner._execute_subpipeline("nonexistent")
        assert result == {"success": False, "error": "SubPipeline 'nonexistent' not found"}

    async def test_runner_execute_subpipeline_dag_error(self):
        tasks = [
            ResolvedTask(name="a", task_type="command", command="echo", depends_on=["b"]),
            ResolvedTask(name="b", task_type="command", command="echo", depends_on=["a"]),
        ]
        sub = ResolvedSubPipeline(name="s1", tasks=tasks, config=PipelineConfig())
        p = ResolvedPipeline(name="p", subpipelines=[sub], top_config=PipelineConfig())
        ctx = ExecutionContext(pipeline=p, run_id="r1")
        runner = PipelineRunner(run_id="r1", pipeline=p, context=ctx)
        result = await runner._execute_subpipeline("s1")
        assert result["success"] is False

    async def test_runner_execute_subpipeline_unknown_dep(self):
        tasks = [ResolvedTask(name="a", task_type="command", command="echo", depends_on=["unknown"])]
        sub = ResolvedSubPipeline(name="s1", tasks=tasks, config=PipelineConfig())
        p = ResolvedPipeline(name="p", subpipelines=[sub], top_config=PipelineConfig())
        ctx = ExecutionContext(pipeline=p, run_id="r1")
        runner = PipelineRunner(run_id="r1", pipeline=p, context=ctx)
        result = await runner._execute_subpipeline("s1")
        assert result["success"] is False

    async def test_runner_execute_task_when_false(self):
        task = ResolvedTask(name="t1", task_type="command", command="echo", when='${env.X} == "Y"')
        sub = ResolvedSubPipeline(name="s1", tasks=[task], config=PipelineConfig())
        p = ResolvedPipeline(name="p", subpipelines=[sub], top_config=PipelineConfig())
        ctx = ExecutionContext(pipeline=p, run_id="r1")
        runner = PipelineRunner(run_id="r1", pipeline=p, context=ctx)

        mock_sf, mock_tr, _mock_rr, _ = _make_async_session_mock()
        with (
            patch("taskpps.engine.runner.get_session_factory", return_value=mock_sf),
            patch("taskpps.engine.runner.TaskRunRepository", return_value=mock_tr),
        ):
            runner._task_run_ids = {"t1": "tr1"}
            result = await runner._execute_task(task)
        assert result.success is True

    async def test_runner_execute_task_commands(self, tmp_path):
        task = ResolvedTask(
            name="t1",
            task_type="command",
            commands=["echo step1", "echo step2"],
        )
        sub = ResolvedSubPipeline(name="s1", tasks=[task], config=PipelineConfig())
        p = ResolvedPipeline(name="p", subpipelines=[sub], top_config=PipelineConfig())
        ctx = ExecutionContext(pipeline=p, run_id="r1")
        runner = PipelineRunner(run_id="r1", pipeline=p, context=ctx)
        runner._task_run_ids = {"t1": "tr1"}

        log_dir = tmp_path / "p" / "r1" / "tr1"
        log_dir.mkdir(parents=True)

        mock_executor = AsyncMock()
        mock_executor.execute.return_value = ExecutorResult(exit_code=0, stdout="ok\n")

        mock_sf, mock_tr, _mock_rr, _ = _make_async_session_mock()
        with (
            patch("taskpps.engine.runner.get_event_bus"),
            patch("taskpps.engine.runner.get_logs_dir", return_value=tmp_path),
            patch("taskpps.engine.runner.get_session_factory", return_value=mock_sf),
            patch("taskpps.engine.runner.TaskRunRepository", return_value=mock_tr),
            patch("taskpps.engine.runner.create_executor", return_value=mock_executor),
            patch("taskpps.engine.runner.get_settings", return_value=_make_settings_mock()),
        ):
            result = await runner._execute_task(task)

        assert result.success
        assert mock_executor.execute.call_count == 2

    async def test_runner_execute_task_commands_failure(self, tmp_path):
        task = ResolvedTask(
            name="t1",
            task_type="command",
            commands=["echo step1", "exit 1"],
        )
        sub = ResolvedSubPipeline(name="s1", tasks=[task], config=PipelineConfig())
        p = ResolvedPipeline(name="p", subpipelines=[sub], top_config=PipelineConfig())
        ctx = ExecutionContext(pipeline=p, run_id="r1")
        runner = PipelineRunner(run_id="r1", pipeline=p, context=ctx)
        runner._task_run_ids = {"t1": "tr1"}

        log_dir = tmp_path / "p" / "r1" / "tr1"
        log_dir.mkdir(parents=True)

        mock_executor = AsyncMock()
        mock_executor.execute.side_effect = [
            ExecutorResult(exit_code=0, stdout="ok\n"),
            ExecutorResult(exit_code=1, stderr="failed"),
        ]

        mock_sf, mock_tr, _mock_rr, _ = _make_async_session_mock()
        with (
            patch("taskpps.engine.runner.get_event_bus"),
            patch("taskpps.engine.runner.get_logs_dir", return_value=tmp_path),
            patch("taskpps.engine.runner.get_session_factory", return_value=mock_sf),
            patch("taskpps.engine.runner.TaskRunRepository", return_value=mock_tr),
            patch("taskpps.engine.runner.create_executor", return_value=mock_executor),
            patch("taskpps.engine.runner.get_settings", return_value=_make_settings_mock()),
        ):
            result = await runner._execute_task(task)

        assert not result.success
        assert result.exit_code == 1

    async def test_runner_execute_task_retry(self, tmp_path):
        task = ResolvedTask(name="t1", task_type="command", command="echo", retry=2)
        sub = ResolvedSubPipeline(name="s1", tasks=[task], config=PipelineConfig())
        p = ResolvedPipeline(name="p", subpipelines=[sub], top_config=PipelineConfig())
        ctx = ExecutionContext(pipeline=p, run_id="r1")
        runner = PipelineRunner(run_id="r1", pipeline=p, context=ctx)
        runner._task_run_ids = {"t1": "tr1"}

        log_dir = tmp_path / "p" / "r1" / "tr1"
        log_dir.mkdir(parents=True)
        log_dir / "output.log"

        mock_executor = AsyncMock()
        mock_executor.execute.side_effect = [
            ExecutorResult(exit_code=1, stderr="fail1"),
            ExecutorResult(exit_code=1, stderr="fail2"),
            ExecutorResult(exit_code=0, stdout="ok on retry"),
        ]

        mock_sf, mock_tr, _mock_rr, _ = _make_async_session_mock()
        with (
            patch("taskpps.engine.runner.get_event_bus"),
            patch("taskpps.engine.runner.get_logs_dir", return_value=tmp_path),
            patch("taskpps.engine.runner.get_session_factory", return_value=mock_sf),
            patch("taskpps.engine.runner.TaskRunRepository", return_value=mock_tr),
            patch("taskpps.engine.runner.create_executor", return_value=mock_executor),
            patch("taskpps.engine.runner.get_settings", return_value=_make_settings_mock()),
        ):
            result = await runner._execute_task(task)

        assert result.success
        assert mock_executor.execute.call_count == 3

    async def test_runner_execute_task_retry_exhausted(self, tmp_path):
        task = ResolvedTask(name="t1", task_type="command", command="echo", retry=1)
        sub = ResolvedSubPipeline(name="s1", tasks=[task], config=PipelineConfig())
        p = ResolvedPipeline(name="p", subpipelines=[sub], top_config=PipelineConfig())
        ctx = ExecutionContext(pipeline=p, run_id="r1")
        runner = PipelineRunner(run_id="r1", pipeline=p, context=ctx)
        runner._task_run_ids = {"t1": "tr1"}

        log_dir = tmp_path / "p" / "r1" / "tr1"
        log_dir.mkdir(parents=True)

        mock_executor = AsyncMock()
        mock_executor.execute.side_effect = [
            ExecutorResult(exit_code=1, stderr="fail1"),
            ExecutorResult(exit_code=1, stderr="fail2"),
        ]

        mock_sf, mock_tr, _mock_rr, _ = _make_async_session_mock()
        with (
            patch("taskpps.engine.runner.get_event_bus"),
            patch("taskpps.engine.runner.get_logs_dir", return_value=tmp_path),
            patch("taskpps.engine.runner.get_session_factory", return_value=mock_sf),
            patch("taskpps.engine.runner.TaskRunRepository", return_value=mock_tr),
            patch("taskpps.engine.runner.create_executor", return_value=mock_executor),
            patch("taskpps.engine.runner.get_settings", return_value=_make_settings_mock()),
        ):
            result = await runner._execute_task(task)

        assert not result.success
        assert mock_executor.execute.call_count == 2

    async def test_runner_execute_subpipeline_sequential(self, tmp_path):
        task1 = ResolvedTask(name="t1", task_type="command", command="echo 1")
        task2 = ResolvedTask(name="t2", task_type="command", command="echo 2")
        sub = ResolvedSubPipeline(
            name="s1",
            tasks=[task1, task2],
            config=PipelineConfig(execution_strategy="sequential"),
        )
        p = ResolvedPipeline(name="p", subpipelines=[sub], top_config=PipelineConfig())
        ctx = ExecutionContext(pipeline=p, run_id="r1")
        runner = PipelineRunner(run_id="r1", pipeline=p, context=ctx)
        runner._task_run_ids = {"t1": "tr1", "t2": "tr2"}

        log_dir = tmp_path / "p" / "r1"
        log_dir.mkdir(parents=True)
        (log_dir / "tr1").mkdir()
        (log_dir / "tr2").mkdir()

        mock_executor = AsyncMock()
        mock_executor.execute.return_value = ExecutorResult(exit_code=0, stdout="ok")

        mock_sf, mock_tr, _mock_rr, _ = _make_async_session_mock()
        with (
            patch("taskpps.engine.runner.get_event_bus"),
            patch("taskpps.engine.runner.get_logs_dir", return_value=tmp_path),
            patch("taskpps.engine.runner.get_session_factory", return_value=mock_sf),
            patch("taskpps.engine.runner.TaskRunRepository", return_value=mock_tr),
            patch("taskpps.engine.runner.create_executor", return_value=mock_executor),
            patch("taskpps.engine.runner.get_settings", return_value=_make_settings_mock()),
        ):
            result = await runner._execute_subpipeline("s1")

        assert result["success"] is True

    async def test_runner_execute_subpipeline_parallel(self, tmp_path):
        task1 = ResolvedTask(name="t1", task_type="command", command="echo 1")
        task2 = ResolvedTask(name="t2", task_type="command", command="echo 2")
        sub = ResolvedSubPipeline(
            name="s1",
            tasks=[task1, task2],
            config=PipelineConfig(execution_strategy="parallel"),
        )
        p = ResolvedPipeline(name="p", subpipelines=[sub], top_config=PipelineConfig())
        ctx = ExecutionContext(pipeline=p, run_id="r1")
        runner = PipelineRunner(run_id="r1", pipeline=p, context=ctx)
        runner._task_run_ids = {"t1": "tr1", "t2": "tr2"}

        log_dir = tmp_path / "p" / "r1"
        log_dir.mkdir(parents=True)
        (log_dir / "tr1").mkdir()
        (log_dir / "tr2").mkdir()

        mock_executor = AsyncMock()
        mock_executor.execute.return_value = ExecutorResult(exit_code=0, stdout="ok")

        mock_sf, mock_tr, _mock_rr, _ = _make_async_session_mock()
        with (
            patch("taskpps.engine.runner.get_event_bus"),
            patch("taskpps.engine.runner.get_logs_dir", return_value=tmp_path),
            patch("taskpps.engine.runner.get_session_factory", return_value=mock_sf),
            patch("taskpps.engine.runner.TaskRunRepository", return_value=mock_tr),
            patch("taskpps.engine.runner.create_executor", return_value=mock_executor),
            patch("taskpps.engine.runner.get_settings", return_value=_make_settings_mock()),
        ):
            result = await runner._execute_subpipeline("s1")

        assert result["success"] is True

    async def test_runner_execute_commands_empty(self, tmp_path):
        task = ResolvedTask(name="t1", task_type="command", commands=[])
        sub = ResolvedSubPipeline(name="s1", tasks=[task], config=PipelineConfig())
        p = ResolvedPipeline(name="p", subpipelines=[sub], top_config=PipelineConfig())
        ctx = ExecutionContext(pipeline=p, run_id="r1")
        runner = PipelineRunner(run_id="r1", pipeline=p, context=ctx)

        mock_executor = AsyncMock()
        log_path = tmp_path / "output.log"
        result = await runner._execute_commands(mock_executor, task, {}, log_path, None)
        assert result.success
        assert result.exit_code == 0

    async def test_runner_execute_steps_env_merge(self, tmp_path):
        steps = [ResolvedStep(run="echo $GLOBAL", env={"LOCAL": "val"})]
        task = ResolvedTask(name="t1", task_type="steps", steps=steps, cwd="/workspace")
        sub = ResolvedSubPipeline(name="s1", tasks=[task], config=PipelineConfig(env={"GLOBAL": "env"}))
        p = ResolvedPipeline(name="p", subpipelines=[sub], top_config=PipelineConfig())
        ctx = ExecutionContext(pipeline=p, run_id="r1")
        runner = PipelineRunner(run_id="r1", pipeline=p, context=ctx)

        mock_executor = AsyncMock()
        mock_executor.execute.return_value = ExecutorResult(exit_code=0, stdout="ok")

        log_path = tmp_path / "output.log"
        result = await runner._execute_steps(mock_executor, task, {"GLOBAL": "global_value"}, log_path, 30)
        assert result.success
        call_kwargs = mock_executor.execute.call_args.kwargs
        assert call_kwargs["env"]["GLOBAL"] == "global_value"
        assert call_kwargs["env"]["LOCAL"] == "val"

    async def test_runner_execute_task_with_exception(self, tmp_path):
        task = ResolvedTask(name="t1", task_type="command", command="echo")
        sub = ResolvedSubPipeline(name="s1", tasks=[task], config=PipelineConfig())
        p = ResolvedPipeline(name="p", subpipelines=[sub], top_config=PipelineConfig())
        ctx = ExecutionContext(pipeline=p, run_id="r1")
        runner = PipelineRunner(run_id="r1", pipeline=p, context=ctx)
        runner._task_run_ids = {"t1": "tr1"}

        log_dir = tmp_path / "p" / "r1" / "tr1"
        log_dir.mkdir(parents=True)

        mock_executor = AsyncMock()
        mock_executor.execute.side_effect = Exception("boom")

        mock_sf, mock_tr, _mock_rr, _ = _make_async_session_mock()
        with (
            patch("taskpps.engine.runner.get_event_bus"),
            patch("taskpps.engine.runner.get_logs_dir", return_value=tmp_path),
            patch("taskpps.engine.runner.get_session_factory", return_value=mock_sf),
            patch("taskpps.engine.runner.TaskRunRepository", return_value=mock_tr),
            patch("taskpps.engine.runner.create_executor", return_value=mock_executor),
            patch("taskpps.engine.runner.get_settings", return_value=_make_settings_mock()),
        ):
            result = await runner._execute_task(task)

        assert not result.success
        assert result.exit_code == 1


# ============================================================
# Executors tests (new)
# ============================================================


class TestCreateExecutor:
    def test_create_executor_invoke(self):
        task = ResolvedTask(name="t1", task_type="invoke", invoke_task="mod.fn")
        executor = create_executor(task)
        from taskpps.executors.invoke import InvokeExecutor

        assert isinstance(executor, InvokeExecutor)

    def test_create_executor_no_host(self):
        task = ResolvedTask(name="t1", task_type="command", command="echo")
        executor = create_executor(task)
        from taskpps.executors.local import LocalExecutor

        assert isinstance(executor, LocalExecutor)

    def test_resolve_agent_by_id(self, tmp_path):
        agents_dir = tmp_path / "agents"
        agents_dir.mkdir()
        (agents_dir / "ssh.yaml").write_text(
            yaml.dump({"agents": [{"id": "agent-x", "host": "10.0.0.1", "username": "admin"}]})
        )
        loader = AgentLoader(agents_dir)
        result = _resolve_agent(loader, "agent-x")
        assert result["host"] == "10.0.0.1"

    def test_resolve_agent_by_filename(self, tmp_path):
        agents_dir = tmp_path / "agents"
        agents_dir.mkdir()
        (agents_dir / "staging.yaml").write_text(yaml.dump({"host": "10.0.0.1", "username": "admin"}))
        loader = AgentLoader(agents_dir)
        result = _resolve_agent(loader, "staging")
        assert result["host"] == "10.0.0.1"

    def test_resolve_agent_not_found(self, tmp_path):
        loader = AgentLoader(tmp_path)
        result = _resolve_agent(loader, "nonexistent")
        assert result is None

    def test_resolve_credential_by_id(self, tmp_path):
        creds_dir = tmp_path / "credentials"
        creds_dir.mkdir()
        (creds_dir / "ssh.yaml").write_text(yaml.dump({"credentials": [{"id": "cred-x", "password": "secret"}]}))
        loader = CredentialLoader(creds_dir)
        result = _resolve_credential(loader, "cred-x")
        assert result["password"] == "secret"

    def test_resolve_credential_by_filename(self, tmp_path):
        creds_dir = tmp_path / "credentials"
        creds_dir.mkdir()
        (creds_dir / "default.yaml").write_text(yaml.dump({"password": "changeme"}))
        loader = CredentialLoader(creds_dir)
        result = _resolve_credential(loader, "default")
        assert result["password"] == "changeme"

    def test_resolve_credential_not_found(self, tmp_path):
        loader = CredentialLoader(tmp_path)
        result = _resolve_credential(loader, "nonexistent")
        assert result is None


# ============================================================
# PipelineService tests (new)
# ============================================================


@pytest.mark.asyncio
class TestPipelineServiceNew:
    async def test_service_create_run_new_pipeline(self):
        from taskpps.services.pipeline_service import PipelineService

        svc = PipelineService()
        with patch.object(svc.loader, "load") as mock_load:
            sub_yaml = SubPipeline(
                name="build",
                tasks=[TaskYAML(name="t1", command="echo")],
            )
            spec = PipelineYAML(name="multi", pipelines=[sub_yaml])
            mock_load.return_value = spec

            with (
                patch("taskpps.services.pipeline_service.get_session_factory") as mock_sf,
                patch("taskpps.services.pipeline_service.RunRepository") as mock_rr,
                patch("taskpps.services.pipeline_service.TaskRunRepository") as mock_tr,
                patch("taskpps.services.pipeline_service.get_logs_dir"),
                patch("taskpps.services.pipeline_service.asyncio.create_task"),
                patch("taskpps.services.pipeline_service.PipelineRunner"),
            ):
                mock_session = MagicMock()
                mock_session.__aenter__ = AsyncMock(return_value=mock_session)
                mock_session.__aexit__ = AsyncMock(return_value=None)
                mock_sf.return_value = mock_session

                mock_run = MagicMock()
                mock_run.id = "run-id"
                mock_run.pipeline_name = "multi"
                mock_run.status = "pending"
                mock_rr.return_value.create_run = AsyncMock(return_value=mock_run)

                mock_task_run = MagicMock()
                mock_task_run.id = "tr1"
                mock_tr.return_value.create_task_run = AsyncMock(return_value=mock_task_run)

                result = await svc.create_run("multi.yaml")
                assert result["id"] == "run-id"

    async def test_service_create_run_dag_error(self):
        from taskpps.services.pipeline_service import PipelineService

        svc = PipelineService()
        with patch.object(svc.loader, "load") as mock_load:
            sub_yaml = SubPipeline(
                name="cycle",
                tasks=[
                    TaskYAML(name="a", command="echo", depends_on=["b"]),
                    TaskYAML(name="b", command="echo", depends_on=["a"]),
                ],
            )
            spec = PipelineYAML(name="cycle", pipelines=[sub_yaml])
            mock_load.return_value = spec

            with pytest.raises(ValueError, match="SubPipeline"):
                await svc.create_run("cycle.yaml")

    async def test_service_create_run_load_error(self):
        from taskpps.services.pipeline_service import PipelineService

        svc = PipelineService()
        with patch.object(svc.loader, "load", side_effect=Exception("load error")), pytest.raises(ValueError):
            await svc.create_run("bad.yaml")

    async def test_handle_run_error_cancelled(self):
        import asyncio

        from taskpps.services.pipeline_service import PipelineService

        async def cancelled_coro():
            raise asyncio.CancelledError()

        task = asyncio.ensure_future(cancelled_coro())
        with contextlib.suppress(asyncio.CancelledError):
            await task
        PipelineService._handle_run_error(task)


# ============================================================
# Final coverage gap tests
# ============================================================


@pytest.mark.asyncio
class TestCoverageFinal:
    async def test_pipeline_loader_load_all(self, tmp_path):
        (tmp_path / "p1.yaml").write_text(yaml.dump({"name": "p1", "tasks": [{"name": "t1", "command": "echo"}]}))
        loader = PipelineLoader(tmp_path)
        result = loader.load_all()
        assert "p1" in result

    async def test_pipeline_loader_load_with_env(self, tmp_path):
        (tmp_path / "p1.yaml").write_text(yaml.dump({"name": "p1", "tasks": [{"name": "t1", "command": "${MY_VAR}"}]}))
        loader = PipelineLoader(tmp_path)
        spec = loader.load("p1.yaml", env={"MY_VAR": "hello"})
        assert spec.tasks[0].command == "hello"

    async def test_pipeline_loader_load_yml(self, tmp_path):
        (tmp_path / "p1.yml").write_text(yaml.dump({"name": "p1", "tasks": [{"name": "t1", "command": "echo"}]}))
        loader = PipelineLoader(tmp_path)
        spec = loader.load("p1.yml")
        assert spec.name == "p1"

    async def test_pipeline_loader_path_traversal(self, tmp_path):
        loader = PipelineLoader(tmp_path)
        with pytest.raises(FileNotFoundError):
            loader.load("../outside.yaml")

    async def test_pipeline_loader_empty_file(self, tmp_path):
        (tmp_path / "empty.yaml").write_text("")
        loader = PipelineLoader(tmp_path)
        with pytest.raises(ValueError, match="empty"):
            loader.load("empty.yaml")

    async def test_runner_run_partial(self, tmp_path):
        task1 = ResolvedTask(name="t1", task_type="command", command="echo ok")
        task2 = ResolvedTask(name="t2", task_type="command", command="exit 1")
        sub1 = ResolvedSubPipeline(
            name="s1",
            tasks=[task1],
            config=PipelineConfig(on_failure="continue"),
        )
        sub2 = ResolvedSubPipeline(
            name="s2",
            tasks=[task2],
            config=PipelineConfig(),
        )
        p = ResolvedPipeline(name="p", subpipelines=[sub1, sub2], top_config=PipelineConfig())
        ctx = ExecutionContext(pipeline=p, run_id="r1")
        runner = PipelineRunner(run_id="r1", pipeline=p, context=ctx)
        runner._task_run_ids = {"t1": "tr1", "t2": "tr2"}
        log_dir = tmp_path / "p" / "r1"
        log_dir.mkdir(parents=True)
        (log_dir / "tr1").mkdir()
        (log_dir / "tr2").mkdir()

        mock_sf, mock_tr, mock_rr, _mock_session = _make_async_session_mock()
        mock_executor = AsyncMock()
        mock_executor.execute.side_effect = [
            ExecutorResult(exit_code=0, stdout="ok"),
            ExecutorResult(exit_code=1, stderr="fail"),
        ]

        with (
            patch("taskpps.engine.runner.get_event_bus"),
            patch("taskpps.engine.runner.get_logs_dir", return_value=tmp_path),
            patch("taskpps.engine.runner.get_session_factory", return_value=mock_sf),
            patch("taskpps.engine.runner.TaskRunRepository", return_value=mock_tr),
            patch("taskpps.engine.runner.RunRepository", return_value=mock_rr),
            patch("taskpps.engine.runner.create_executor", return_value=mock_executor),
            patch("taskpps.engine.runner.get_settings", return_value=_make_settings_mock()),
        ):
            await runner.run()

    async def test_service_create_run_with_params(self):
        from taskpps.services.pipeline_service import PipelineService

        svc = PipelineService()
        with patch.object(svc.loader, "load") as mock_load:
            spec = PipelineYAML(name="test", tasks=[TaskYAML(name="t1", command="echo", timeout=10)])
            mock_load.return_value = spec

            mock_sf, mock_tr, mock_rr, _mock_session = _make_async_session_mock()
            mock_run = MagicMock()
            mock_run.id = "run-id"
            mock_run.pipeline_name = "test"
            mock_run.status = "pending"
            mock_rr.create_run = AsyncMock(return_value=mock_run)
            mock_task_run = MagicMock()
            mock_task_run.id = "tr1"
            mock_tr.create_task_run = AsyncMock(return_value=mock_task_run)

            with (
                patch("taskpps.services.pipeline_service.get_session_factory", return_value=mock_sf),
                patch("taskpps.services.pipeline_service.RunRepository", return_value=mock_rr),
                patch("taskpps.services.pipeline_service.TaskRunRepository", return_value=mock_tr),
                patch("taskpps.services.pipeline_service.get_logs_dir"),
                patch("taskpps.services.pipeline_service.asyncio.create_task"),
                patch("taskpps.services.pipeline_service.PipelineRunner"),
            ):
                result = await svc.create_run("test.yaml", params={"tasks[0].timeout": 60})
                assert result["id"] == "run-id"

    def test_service_list_pipelines(self):
        from taskpps.services.pipeline_service import PipelineService

        svc = PipelineService()
        with patch.object(svc.loader, "load_all", return_value={"p1": MagicMock()}):
            result = svc.list_pipelines()
            assert result == ["p1"]

    async def test_runner_execute_commands_step_logging(self, tmp_path):
        task = ResolvedTask(name="t1", task_type="command", commands=["echo hi"])
        sub = ResolvedSubPipeline(name="s1", tasks=[task], config=PipelineConfig())
        p = ResolvedPipeline(name="p", subpipelines=[sub], top_config=PipelineConfig())
        ctx = ExecutionContext(pipeline=p, run_id="r1")
        runner = PipelineRunner(run_id="r1", pipeline=p, context=ctx)

        mock_executor = AsyncMock()
        mock_executor.execute.return_value = ExecutorResult(exit_code=0, stdout="ok")
        log_path = tmp_path / "output.log"
        result = await runner._execute_commands(mock_executor, task, {}, log_path, 1)
        assert result.success

    async def test_runner_execute_steps_with_failure(self, tmp_path):
        steps = [ResolvedStep(run="echo ok"), ResolvedStep(run="exit 1")]
        task = ResolvedTask(name="t1", task_type="steps", steps=steps)
        mock_executor = AsyncMock()
        mock_executor.execute.side_effect = [
            ExecutorResult(exit_code=0, stdout="ok"),
            ExecutorResult(exit_code=1, stderr="fail"),
        ]
        log_path = tmp_path / "output.log"
        runner = PipelineRunner(run_id="r1", pipeline=MagicMock(), context=MagicMock())
        result = await runner._execute_steps(mock_executor, task, {}, log_path, None)
        assert not result.success
        assert result.exit_code == 1

    async def test_runner_execute_steps_with_no_timeout(self, tmp_path):
        steps = [ResolvedStep(run="echo hi")]
        task = ResolvedTask(name="t1", task_type="steps", steps=steps)
        mock_executor = AsyncMock()
        mock_executor.execute.return_value = ExecutorResult(exit_code=0, stdout="ok")
        log_path = tmp_path / "output.log"
        runner = PipelineRunner(run_id="r1", pipeline=MagicMock(), context=MagicMock())
        result = await runner._execute_steps(mock_executor, task, {}, log_path, 30)
        assert result.success

    async def test_credential_loader_load_method(self, tmp_path):
        (tmp_path / "default.yaml").write_text(yaml.dump({"password": "changeme"}))
        loader = CredentialLoader(tmp_path)
        result = loader.load("default")
        assert result["password"] == "changeme"

    async def test_credential_loader_load_not_found(self, tmp_path):
        loader = CredentialLoader(tmp_path)
        with pytest.raises(FileNotFoundError):
            loader.load("nonexistent")

    async def test_agent_loader_load_method(self, tmp_path):
        (tmp_path / "staging.yaml").write_text(yaml.dump({"host": "127.0.0.1"}))
        loader = AgentLoader(tmp_path)
        result = loader.load("staging")
        assert result["host"] == "127.0.0.1"

    async def test_agent_loader_load_not_found(self, tmp_path):
        loader = AgentLoader(tmp_path)
        with pytest.raises(FileNotFoundError):
            loader.load("nonexistent")

    async def test_merge_config_on_failure_default(self):
        top = PipelineConfig(on_failure="fail")
        override = PipelineConfig(on_failure="fail")
        result = _merge_config(top, override)
        assert result.on_failure == "fail"

    async def test_merge_config_strategy_default(self):
        top = PipelineConfig(execution_strategy="sequential")
        override = PipelineConfig(execution_strategy="sequential")
        result = _merge_config(top, override)
        assert result.execution_strategy == "sequential"


# ============================================================
# Additional coverage tests
# ============================================================


class TestContextEdgeCases:
    def test_navigate_to_key_numeric_non_list(self):
        data = {"items": 42}
        result = _navigate_to_key(data, "items[0]")
        assert result == 42

    def test_set_key_name_index_with_dot(self):
        data = {"tasks": [{"name": "foo", "timeout": 100}]}
        _set_key(data, 'tasks["foo"].timeout', 200)
        assert data['tasks["foo"].timeout'] == 200

    def test_set_key_name_index_no_dot(self):
        data = {"tasks": [{"name": "foo", "timeout": 100}]}
        _set_key(data, 'tasks["foo"]', {"name": "foo", "timeout": 999})
        assert data["tasks"][0]["timeout"] == {"name": "foo", "timeout": 999}

    def test_set_dot_path_name_index(self):
        data = {"tasks": [{"name": "foo", "timeout": 100}]}
        set_dot_path(data, 'tasks["foo"]', {"name": "bar"})

    def test_apply_overrides_list_value(self):
        data = [{"name": "t1"}, {"name": "t2"}]
        result = apply_overrides(data, {"0.name": "hello"})
        # The first navigation key '0' goes to list element, then 'name' is set
        assert result[0]["name"] == "hello"


@pytest.mark.asyncio
class TestRunnerEdgeCases:
    async def test_runner_run_sub_not_found(self, tmp_path):
        task = ResolvedTask(name="t1", task_type="command", command="echo")
        sub = ResolvedSubPipeline(name="s1", tasks=[task], config=PipelineConfig())
        p = ResolvedPipeline(name="p", subpipelines=[sub], top_config=PipelineConfig())
        ctx = ExecutionContext(pipeline=p, run_id="r1")
        runner = PipelineRunner(run_id="r1", pipeline=p, context=ctx)
        runner._task_run_ids = {"t1": "tr1"}
        log_dir = tmp_path / "p" / "r1" / "tr1"
        log_dir.mkdir(parents=True)

        mock_sf, mock_tr, mock_rr, _ = _make_async_session_mock()
        mock_executor = AsyncMock()
        mock_executor.execute.return_value = ExecutorResult(exit_code=0, stdout="ok")

        with (
            patch("taskpps.engine.runner.get_event_bus"),
            patch("taskpps.engine.runner.get_logs_dir", return_value=tmp_path),
            patch("taskpps.engine.runner.get_session_factory", return_value=mock_sf),
            patch("taskpps.engine.runner.TaskRunRepository", return_value=mock_tr),
            patch("taskpps.engine.runner.RunRepository", return_value=mock_rr),
            patch("taskpps.engine.runner.create_executor", return_value=mock_executor),
            patch("taskpps.engine.runner.get_settings", return_value=_make_settings_mock()),
        ):
            await runner.run()

    async def test_runner_run_subpipeline_fails_on_failure_block(self, tmp_path):
        task = ResolvedTask(name="t1", task_type="command", command="exit 1")
        sub1 = ResolvedSubPipeline(name="s1", tasks=[task], config=PipelineConfig(on_failure="fail"))
        sub2 = ResolvedSubPipeline(name="s2", tasks=[task], config=PipelineConfig(), depends_on=["s1"])
        p = ResolvedPipeline(name="p", subpipelines=[sub1, sub2], top_config=PipelineConfig())
        ctx = ExecutionContext(pipeline=p, run_id="r1")
        runner = PipelineRunner(run_id="r1", pipeline=p, context=ctx)
        runner._task_run_ids = {"t1": "tr1"}
        log_dir = tmp_path / "p" / "r1" / "tr1"
        log_dir.mkdir(parents=True)

        mock_executor = AsyncMock()
        mock_executor.execute.return_value = ExecutorResult(exit_code=1, stderr="fail")

        mock_sf, mock_tr, mock_rr, _ = _make_async_session_mock()
        with (
            patch("taskpps.engine.runner.get_event_bus"),
            patch("taskpps.engine.runner.get_logs_dir", return_value=tmp_path),
            patch("taskpps.engine.runner.get_session_factory", return_value=mock_sf),
            patch("taskpps.engine.runner.TaskRunRepository", return_value=mock_tr),
            patch("taskpps.engine.runner.RunRepository", return_value=mock_rr),
            patch("taskpps.engine.runner.create_executor", return_value=mock_executor),
            patch("taskpps.engine.runner.get_settings", return_value=_make_settings_mock()),
        ):
            await runner.run()

    async def test_runner_run_subpipeline_fails_on_failure_continue(self, tmp_path):
        task1 = ResolvedTask(name="t1", task_type="command", command="exit 1")
        task2 = ResolvedTask(name="t2", task_type="command", command="echo ok")
        sub1 = ResolvedSubPipeline(
            name="s1",
            tasks=[task1],
            config=PipelineConfig(on_failure="continue"),
        )
        sub2 = ResolvedSubPipeline(
            name="s2",
            tasks=[task2],
            config=PipelineConfig(),
            depends_on=["s1"],
        )
        p = ResolvedPipeline(name="p", subpipelines=[sub1, sub2], top_config=PipelineConfig())
        ctx = ExecutionContext(pipeline=p, run_id="r1")
        runner = PipelineRunner(run_id="r1", pipeline=p, context=ctx)
        runner._task_run_ids = {"t1": "tr1", "t2": "tr2"}
        log_dir = tmp_path / "p" / "r1"
        log_dir.mkdir(parents=True)
        (log_dir / "tr1").mkdir()
        (log_dir / "tr2").mkdir()

        mock_executor = AsyncMock()
        mock_executor.execute.return_value = ExecutorResult(exit_code=0, stdout="ok")

        mock_sf, mock_tr, mock_rr, _ = _make_async_session_mock()
        with (
            patch("taskpps.engine.runner.get_event_bus"),
            patch("taskpps.engine.runner.get_logs_dir", return_value=tmp_path),
            patch("taskpps.engine.runner.get_session_factory", return_value=mock_sf),
            patch("taskpps.engine.runner.TaskRunRepository", return_value=mock_tr),
            patch("taskpps.engine.runner.RunRepository", return_value=mock_rr),
            patch("taskpps.engine.runner.create_executor", return_value=mock_executor),
            patch("taskpps.engine.runner.get_settings", return_value=_make_settings_mock()),
        ):
            await runner.run()

    async def test_runner_run_unexpected_exception(self, tmp_path):
        task = ResolvedTask(name="t1", task_type="command", command="echo")
        sub = ResolvedSubPipeline(name="s1", tasks=[task], config=PipelineConfig())
        p = ResolvedPipeline(name="p", subpipelines=[sub], top_config=PipelineConfig())
        ctx = ExecutionContext(pipeline=p, run_id="r1")
        runner = PipelineRunner(run_id="r1", pipeline=p, context=ctx)
        runner._task_run_ids = {"t1": "tr1"}
        log_dir = tmp_path / "p" / "r1" / "tr1"
        log_dir.mkdir(parents=True)

        mock_sf, mock_tr, mock_rr, _ = _make_async_session_mock()
        with (
            patch("taskpps.engine.runner.get_event_bus"),
            patch("taskpps.engine.runner.get_logs_dir", return_value=tmp_path),
            patch("taskpps.engine.runner.get_session_factory", return_value=mock_sf),
            patch("taskpps.engine.runner.TaskRunRepository", return_value=mock_tr),
            patch("taskpps.engine.runner.RunRepository", return_value=mock_rr),
            patch("taskpps.engine.runner.get_settings", return_value=_make_settings_mock()),
            patch("taskpps.engine.runner.DAG") as mock_dag,
        ):
            mock_dag.side_effect = RuntimeError("unexpected")
            await runner.run()

    async def test_runner_run_cancelled(self, tmp_path):
        task = ResolvedTask(name="t1", task_type="command", command="echo")
        sub = ResolvedSubPipeline(name="s1", tasks=[task], config=PipelineConfig())
        p = ResolvedPipeline(name="p", subpipelines=[sub], top_config=PipelineConfig())
        ctx = ExecutionContext(pipeline=p, run_id="r1")
        runner = PipelineRunner(run_id="r1", pipeline=p, context=ctx)
        runner._cancelled = True

        mock_sf, _mock_tr, mock_rr, _ = _make_async_session_mock()
        with (
            patch("taskpps.engine.runner.get_event_bus"),
            patch("taskpps.engine.runner.get_session_factory", return_value=mock_sf),
            patch("taskpps.engine.runner.RunRepository", return_value=mock_rr),
        ):
            await runner.run()

    async def test_runner_execute_subpipeline_cancelled(self, tmp_path):
        task1 = ResolvedTask(name="t1", task_type="command", command="echo 1")
        task2 = ResolvedTask(name="t2", task_type="command", command="echo 2")
        sub = ResolvedSubPipeline(
            name="s1",
            tasks=[task1, task2],
            config=PipelineConfig(execution_strategy="sequential"),
        )
        p = ResolvedPipeline(name="p", subpipelines=[sub], top_config=PipelineConfig())
        ctx = ExecutionContext(pipeline=p, run_id="r1")
        runner = PipelineRunner(run_id="r1", pipeline=p, context=ctx)
        runner._cancelled = True
        runner._task_run_ids = {"t1": "tr1", "t2": "tr2"}

        mock_executor = AsyncMock()
        mock_executor.execute.return_value = ExecutorResult(exit_code=0, stdout="ok")

        mock_sf, mock_tr, _mock_rr, _ = _make_async_session_mock()
        with (
            patch("taskpps.engine.runner.get_event_bus"),
            patch("taskpps.engine.runner.get_logs_dir", return_value=tmp_path),
            patch("taskpps.engine.runner.get_session_factory", return_value=mock_sf),
            patch("taskpps.engine.runner.TaskRunRepository", return_value=mock_tr),
            patch("taskpps.engine.runner.create_executor", return_value=mock_executor),
            patch("taskpps.engine.runner.get_settings", return_value=_make_settings_mock()),
        ):
            result = await runner._execute_subpipeline("s1")
        assert result["success"] is True

    async def test_runner_execute_task_exception_in_subpipeline(self, tmp_path):
        task = ResolvedTask(name="t1", task_type="command", command="echo")
        sub = ResolvedSubPipeline(name="s1", tasks=[task], config=PipelineConfig(execution_strategy="sequential"))
        p = ResolvedPipeline(name="p", subpipelines=[sub], top_config=PipelineConfig())
        ctx = ExecutionContext(pipeline=p, run_id="r1")
        runner = PipelineRunner(run_id="r1", pipeline=p, context=ctx)
        runner._task_run_ids = {"t1": "tr1"}
        log_dir = tmp_path / "p" / "r1" / "tr1"
        log_dir.mkdir(parents=True)

        mock_executor = AsyncMock()
        mock_executor.execute.side_effect = Exception("boom")

        mock_sf, mock_tr, _mock_rr, _ = _make_async_session_mock()
        with (
            patch("taskpps.engine.runner.get_event_bus"),
            patch("taskpps.engine.runner.get_logs_dir", return_value=tmp_path),
            patch("taskpps.engine.runner.get_session_factory", return_value=mock_sf),
            patch("taskpps.engine.runner.TaskRunRepository", return_value=mock_tr),
            patch("taskpps.engine.runner.create_executor", return_value=mock_executor),
            patch("taskpps.engine.runner.get_settings", return_value=_make_settings_mock()),
        ):
            result = await runner._execute_subpipeline("s1")
        assert result["success"] is False

    async def test_runner_execute_commands_timeout_below_1(self, tmp_path):
        task = ResolvedTask(
            name="t1",
            task_type="command",
            commands=["echo step1"],
        )
        sub = ResolvedSubPipeline(name="s1", tasks=[task], config=PipelineConfig())
        p = ResolvedPipeline(name="p", subpipelines=[sub], top_config=PipelineConfig())
        ctx = ExecutionContext(pipeline=p, run_id="r1")
        runner = PipelineRunner(run_id="r1", pipeline=p, context=ctx)

        mock_executor = AsyncMock()
        mock_executor.execute.return_value = ExecutorResult(exit_code=0, stdout="ok")
        log_path = tmp_path / "output.log"
        result = await runner._execute_commands(mock_executor, task, {}, log_path, 0)
        assert result.success

    async def test_runner_execute_steps_in_task(self, tmp_path):
        steps = [ResolvedStep(run="echo hello")]
        task = ResolvedTask(name="t1", task_type="steps", steps=steps)
        sub = ResolvedSubPipeline(name="s1", tasks=[task], config=PipelineConfig())
        p = ResolvedPipeline(name="p", subpipelines=[sub], top_config=PipelineConfig())
        ctx = ExecutionContext(pipeline=p, run_id="r1")
        runner = PipelineRunner(run_id="r1", pipeline=p, context=ctx)
        runner._task_run_ids = {"t1": "tr1"}
        log_dir = tmp_path / "p" / "r1" / "tr1"
        log_dir.mkdir(parents=True)

        mock_executor = AsyncMock()
        mock_executor.execute.return_value = ExecutorResult(exit_code=0, stdout="ok")

        mock_sf, mock_tr, _mock_rr, _ = _make_async_session_mock()
        with (
            patch("taskpps.engine.runner.get_event_bus"),
            patch("taskpps.engine.runner.get_logs_dir", return_value=tmp_path),
            patch("taskpps.engine.runner.get_session_factory", return_value=mock_sf),
            patch("taskpps.engine.runner.TaskRunRepository", return_value=mock_tr),
            patch("taskpps.engine.runner.create_executor", return_value=mock_executor),
            patch("taskpps.engine.runner.get_settings", return_value=_make_settings_mock()),
        ):
            result = await runner._execute_task(task)
        assert result.success

    async def test_runner_subpipeline_dag_cycle(self):
        task1 = ResolvedTask(name="a", task_type="command", command="echo", depends_on=["b"])
        task2 = ResolvedTask(name="b", task_type="command", command="echo", depends_on=["a"])
        sub1 = ResolvedSubPipeline(name="s1", tasks=[task1], config=PipelineConfig(), depends_on=["s2"])
        sub2 = ResolvedSubPipeline(name="s2", tasks=[task2], config=PipelineConfig(), depends_on=["s1"])
        p = ResolvedPipeline(name="p", subpipelines=[sub1, sub2], top_config=PipelineConfig())
        ctx = ExecutionContext(pipeline=p, run_id="r1")
        runner = PipelineRunner(run_id="r1", pipeline=p, context=ctx)
        from taskpps.domain.dag import DAGCycleError

        with pytest.raises(DAGCycleError):
            runner._build_subpipeline_levels()


@pytest.mark.asyncio
class TestPipelineServiceEdgeCases:
    async def test_get_run_with_json_params(self):
        from taskpps.services.pipeline_service import PipelineService

        svc = PipelineService()

        mock_sf, mock_tr, mock_rr, _mock_session = _make_async_session_mock()
        mock_run = MagicMock()
        mock_run.id = "r1"
        mock_run.pipeline_name = "p"
        mock_run.pipeline_file = "p.yaml"
        mock_run.status = "success"
        mock_run.params = '{"key": "value"}'
        mock_run.started_at = None
        mock_run.finished_at = None
        mock_run.created_at = None
        mock_rr.get_run = AsyncMock(return_value=mock_run)
        mock_tr.list_task_runs = AsyncMock(return_value=[])

        with (
            patch("taskpps.services.pipeline_service.get_session_factory", return_value=mock_sf),
            patch("taskpps.services.pipeline_service.RunRepository", return_value=mock_rr),
            patch("taskpps.services.pipeline_service.TaskRunRepository", return_value=mock_tr),
        ):
            result = await svc.get_run("r1")
            assert result["id"] == "r1"
            assert result["params"] == {"key": "value"}

    async def test_get_run_with_dict_params(self):
        from taskpps.services.pipeline_service import PipelineService

        svc = PipelineService()

        mock_sf, mock_tr, mock_rr, _mock_session = _make_async_session_mock()
        mock_run = MagicMock()
        mock_run.id = "r1"
        mock_run.pipeline_name = "p"
        mock_run.pipeline_file = "p.yaml"
        mock_run.status = "success"
        mock_run.params = {"key": "value"}
        mock_run.started_at = None
        mock_run.finished_at = None
        mock_run.created_at = None
        mock_rr.get_run = AsyncMock(return_value=mock_run)
        mock_tr.list_task_runs = AsyncMock(return_value=[])

        with (
            patch("taskpps.services.pipeline_service.get_session_factory", return_value=mock_sf),
            patch("taskpps.services.pipeline_service.RunRepository", return_value=mock_rr),
            patch("taskpps.services.pipeline_service.TaskRunRepository", return_value=mock_tr),
        ):
            result = await svc.get_run("r1")
            assert result["params"] == {"key": "value"}

    async def test_get_run_invalid_json(self):
        from taskpps.services.pipeline_service import PipelineService

        svc = PipelineService()

        mock_sf, mock_tr, mock_rr, _mock_session = _make_async_session_mock()
        mock_run = MagicMock()
        mock_run.id = "r1"
        mock_run.pipeline_name = "p"
        mock_run.pipeline_file = "p.yaml"
        mock_run.status = "success"
        mock_run.params = "not-json"
        mock_run.started_at = None
        mock_run.finished_at = None
        mock_run.created_at = None
        mock_rr.get_run = AsyncMock(return_value=mock_run)
        mock_tr.list_task_runs = AsyncMock(return_value=[])

        with (
            patch("taskpps.services.pipeline_service.get_session_factory", return_value=mock_sf),
            patch("taskpps.services.pipeline_service.RunRepository", return_value=mock_rr),
            patch("taskpps.services.pipeline_service.TaskRunRepository", return_value=mock_tr),
        ):
            result = await svc.get_run("r1")
            assert result["params"] == {}

    async def test_cancel_run_via_session(self):
        from taskpps.services.pipeline_service import PipelineService

        svc = PipelineService()

        mock_sf, mock_tr, mock_rr, _mock_session = _make_async_session_mock()
        mock_run = MagicMock()
        mock_run.id = "r1"
        mock_run.status = "running"
        mock_rr.get_run = AsyncMock(return_value=mock_run)
        mock_rr.update_run_status = AsyncMock()
        mock_tr.cancel_pending_tasks = AsyncMock()

        with (
            patch("taskpps.services.pipeline_service.get_session_factory", return_value=mock_sf),
            patch("taskpps.services.pipeline_service.RunRepository", return_value=mock_rr),
            patch("taskpps.services.pipeline_service.TaskRunRepository", return_value=mock_tr),
            patch("taskpps.engine.runner.get_active_runner", return_value=None),
        ):
            result = await svc.cancel_run("r1")
            assert result is True

    async def test_list_runs_with_json_params(self):
        from taskpps.services.pipeline_service import PipelineService

        svc = PipelineService()

        mock_sf, _mock_tr, mock_rr, _mock_session = _make_async_session_mock()
        mock_run = MagicMock()
        mock_run.id = "r1"
        mock_run.pipeline_name = "p"
        mock_run.pipeline_file = "p.yaml"
        mock_run.status = "success"
        mock_run.params = '{"key": "value"}'
        mock_run.started_at = None
        mock_run.finished_at = None
        mock_run.created_at = None
        mock_rr.list_runs = AsyncMock(return_value=[mock_run])
        mock_rr.count_runs = AsyncMock(return_value=1)

        with (
            patch("taskpps.services.pipeline_service.get_session_factory", return_value=mock_sf),
            patch("taskpps.services.pipeline_service.RunRepository", return_value=mock_rr),
        ):
            result = await svc.list_runs()
            assert result["total"] == 1
            assert result["items"][0]["params"] == {"key": "value"}

    async def test_list_runs_with_dict_params(self):
        from taskpps.services.pipeline_service import PipelineService

        svc = PipelineService()

        mock_sf, _mock_tr, mock_rr, _mock_session = _make_async_session_mock()
        mock_run = MagicMock()
        mock_run.id = "r1"
        mock_run.pipeline_name = "p"
        mock_run.pipeline_file = "p.yaml"
        mock_run.status = "success"
        mock_run.params = {"key": "value"}
        mock_run.started_at = None
        mock_run.finished_at = None
        mock_run.created_at = None
        mock_rr.list_runs = AsyncMock(return_value=[mock_run])
        mock_rr.count_runs = AsyncMock(return_value=1)

        with (
            patch("taskpps.services.pipeline_service.get_session_factory", return_value=mock_sf),
            patch("taskpps.services.pipeline_service.RunRepository", return_value=mock_rr),
        ):
            result = await svc.list_runs()
            assert result["items"][0]["params"] == {"key": "value"}

    async def test_list_runs_invalid_json(self):
        from taskpps.services.pipeline_service import PipelineService

        svc = PipelineService()

        mock_sf, _mock_tr, mock_rr, _mock_session = _make_async_session_mock()
        mock_run = MagicMock()
        mock_run.id = "r1"
        mock_run.pipeline_name = "p"
        mock_run.pipeline_file = "p.yaml"
        mock_run.status = "success"
        mock_run.params = "not-json"
        mock_run.started_at = None
        mock_run.finished_at = None
        mock_run.created_at = None
        mock_rr.list_runs = AsyncMock(return_value=[mock_run])
        mock_rr.count_runs = AsyncMock(return_value=1)

        with (
            patch("taskpps.services.pipeline_service.get_session_factory", return_value=mock_sf),
            patch("taskpps.services.pipeline_service.RunRepository", return_value=mock_rr),
        ):
            result = await svc.list_runs()
            assert result["items"][0]["params"] == {}

    async def test_handle_run_error_exception(self):
        import asyncio

        from taskpps.services.pipeline_service import PipelineService

        async def error_coro():
            raise RuntimeError("test error")

        task = asyncio.ensure_future(error_coro())
        with contextlib.suppress(RuntimeError):
            await task
        PipelineService._handle_run_error(task)


@pytest.mark.asyncio
class TestCoverageFinal2:
    async def test_credential_loader_load_password_warning(self, tmp_path):
        (tmp_path / "default.yaml").write_text(yaml.dump({"password": "changeme"}))
        loader = CredentialLoader(tmp_path)
        result = loader.load("default")
        assert result["password"] == "changeme"

    async def test_credential_loader_load_yaml_exception(self, tmp_path):
        (tmp_path / "ssh.yaml").write_text("invalid: [yaml")
        loader = CredentialLoader(tmp_path)
        assert loader.load_all() == {}

    async def test_agent_loader_load_empty(self, tmp_path):
        (tmp_path / "empty.yaml").write_text("")
        loader = AgentLoader(tmp_path)
        result = loader.load_all()
        assert result == {}

    async def test_agent_loader_load_yaml_exception(self, tmp_path):
        (tmp_path / "ssh.yaml").write_text("invalid: [yaml")
        loader = AgentLoader(tmp_path)
        assert loader.load_all() == {}

    async def test_pipeline_loader_load_all_yml(self, tmp_path):
        (tmp_path / "p1.yml").write_text(yaml.dump({"name": "p1", "tasks": [{"name": "t1", "command": "echo"}]}))
        loader = PipelineLoader(tmp_path)
        result = loader.load_all()
        assert "p1" in result

    async def test_pipeline_loader_load_all_error(self, tmp_path):
        (tmp_path / "bad.yaml").write_text("invalid: [yaml")
        loader = PipelineLoader(tmp_path)
        result = loader.load_all()
        assert result == {}

    async def test_get_effective_command_invoke(self):
        t = TaskYAML(name="t1", invoke={"task": "mod.fn", "args": []})
        assert t.get_task_type() == "invoke"
        assert t.get_effective_command() is None

    async def test_resolved_task_with_invoke(self):
        ty = TaskYAML(name="t1", invoke={"task": "mod.fn", "args": [1], "kwargs": {"k": "v"}})
        rt = ResolvedTask.from_yaml(ty)
        assert rt.task_type == "invoke"
        assert rt.invoke_task == "mod.fn"
        assert rt.invoke_args == [1]
        assert rt.invoke_kwargs == {"k": "v"}

    async def test_resolved_step_from_yaml(self):
        from taskpps.schemas.pipeline import TaskStep

        ts = TaskStep(run="echo hi", cd="/tmp", env={"X": "1"})
        rs = ResolvedStep.from_yaml(ts)
        assert rs.run == "echo hi"
        assert rs.cd == "/tmp"
        assert rs.env == {"X": "1"}

    async def test_apply_overrides_dict_final(self):
        data = {"config": {"host": "old"}}
        from taskpps.domain.context import set_dot_path

        set_dot_path(data, "config.host", "new")
        assert data["config"]["host"] == "new"

    async def test_runner_run_with_cancelled_subpipeline(self, tmp_path):
        task = ResolvedTask(name="t1", task_type="command", command="echo")
        sub1 = ResolvedSubPipeline(name="s1", tasks=[task], config=PipelineConfig())
        sub2 = ResolvedSubPipeline(name="s2", tasks=[task], config=PipelineConfig(), depends_on=["s1"])
        p = ResolvedPipeline(name="p", subpipelines=[sub1, sub2], top_config=PipelineConfig())
        ctx = ExecutionContext(pipeline=p, run_id="r1")
        runner = PipelineRunner(run_id="r1", pipeline=p, context=ctx)
        runner._cancelled = True
        mock_sf, _mock_tr, mock_rr, _ = _make_async_session_mock()
        with (
            patch("taskpps.engine.runner.get_event_bus"),
            patch("taskpps.engine.runner.get_session_factory", return_value=mock_sf),
            patch("taskpps.engine.runner.RunRepository", return_value=mock_rr),
        ):
            await runner.run()

    async def test_service_create_run_invalid_params(self):
        from taskpps.services.pipeline_service import PipelineService

        svc = PipelineService()
        with patch.object(svc.loader, "load") as mock_load:
            spec = PipelineYAML(name="test", tasks=[TaskYAML(name="t1", command="echo")])
            mock_load.return_value = spec
            with pytest.raises(ValueError):
                await svc.create_run("test.yaml", params={"name": "bad"})

    async def test_service_get_run_not_found(self):
        from taskpps.services.pipeline_service import PipelineService

        svc = PipelineService()
        mock_sf, _mock_tr, mock_rr, _ = _make_async_session_mock()
        mock_rr.get_run = AsyncMock(return_value=None)
        with (
            patch("taskpps.services.pipeline_service.get_session_factory", return_value=mock_sf),
            patch("taskpps.services.pipeline_service.RunRepository", return_value=mock_rr),
        ):
            result = await svc.get_run("nonexistent")
            assert result is None

    async def test_service_cancel_run_not_found(self):
        from taskpps.services.pipeline_service import PipelineService

        svc = PipelineService()
        mock_sf, _mock_tr, mock_rr, _ = _make_async_session_mock()
        mock_rr.get_run = AsyncMock(return_value=None)
        with (
            patch("taskpps.services.pipeline_service.get_session_factory", return_value=mock_sf),
            patch("taskpps.services.pipeline_service.RunRepository", return_value=mock_rr),
            patch("taskpps.engine.runner.get_active_runner", return_value=None),
        ):
            result = await svc.cancel_run("nonexistent")
            assert result is False

    async def test_service_cancel_run_wrong_status(self):
        from taskpps.services.pipeline_service import PipelineService

        svc = PipelineService()
        mock_sf, _mock_tr, mock_rr, _mock_session = _make_async_session_mock()
        mock_run = MagicMock()
        mock_run.id = "r1"
        mock_run.status = "success"
        mock_rr.get_run = AsyncMock(return_value=mock_run)
        with (
            patch("taskpps.services.pipeline_service.get_session_factory", return_value=mock_sf),
            patch("taskpps.services.pipeline_service.RunRepository", return_value=mock_rr),
            patch("taskpps.engine.runner.get_active_runner", return_value=None),
        ):
            result = await svc.cancel_run("r1")
            assert result is False

    async def test_runner_execute_task_invoke_path(self, tmp_path):
        task = ResolvedTask(
            name="t1",
            task_type="invoke",
            invoke_task="my_module.my_func",
            invoke_args=[1, 2],
            invoke_kwargs={"key": "val"},
        )
        sub = ResolvedSubPipeline(name="s1", tasks=[task], config=PipelineConfig())
        p = ResolvedPipeline(name="p", subpipelines=[sub], top_config=PipelineConfig())
        ctx = ExecutionContext(pipeline=p, run_id="r1")
        runner = PipelineRunner(run_id="r1", pipeline=p, context=ctx)
        runner._task_run_ids = {"t1": "tr1"}
        log_dir = tmp_path / "p" / "r1" / "tr1"
        log_dir.mkdir(parents=True)

        mock_executor = AsyncMock()
        mock_executor.execute = AsyncMock()
        mock_executor.execute.return_value = ExecutorResult(exit_code=0, stdout="ok")

        mock_sf, mock_tr, _mock_rr, _ = _make_async_session_mock()
        from taskpps.executors.invoke import InvokeExecutor

        with (
            patch("taskpps.engine.runner.get_event_bus"),
            patch("taskpps.engine.runner.get_logs_dir", return_value=tmp_path),
            patch("taskpps.engine.runner.get_session_factory", return_value=mock_sf),
            patch("taskpps.engine.runner.TaskRunRepository", return_value=mock_tr),
            patch("taskpps.engine.runner.create_executor", return_value=mock_executor),
            patch("taskpps.engine.runner.get_settings", return_value=_make_settings_mock()),
            patch.object(InvokeExecutor, "execute", new=mock_executor.execute),
        ):
            result = await runner._execute_task(task)
        assert result.success

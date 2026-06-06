from __future__ import annotations

import pytest
from pydantic import ValidationError

from taskpps.schemas.agent import AgentCheckRequest, AgentExecRequest
from taskpps.schemas.pipeline import InvokeSpec, OptionsYAML, PipelineYAML, TaskYAML, GitSpec, PipelineConfig
from taskpps.schemas.run import CleanRequest, CreateRunRequest
from taskpps.schemas.trigger import CreateTriggerRequest
from taskpps.models.trigger import TriggerType


class TestTaskYAMLBoundary:
    def test_name_required(self):
        with pytest.raises(ValidationError):
            TaskYAML()

    def test_empty_name(self):
        t = TaskYAML(name="")
        assert t.name == ""

    def test_depends_on_empty(self):
        t = TaskYAML(name="test", command="echo hi")
        assert t.depends_on == []

    def test_depends_on_list(self):
        t = TaskYAML(name="test", command="echo hi", depends_on=["step1", "step2"])
        assert t.depends_on == ["step1", "step2"]

    def test_retry_default(self):
        t = TaskYAML(name="test", command="echo hi")
        assert t.retry == 0

    def test_retry_set(self):
        t = TaskYAML(name="test", command="echo hi", retry=3)
        assert t.retry == 3

    def test_retry_negative(self):
        t = TaskYAML(name="test", command="echo hi", retry=-1)
        assert t.retry == -1

    def test_type_detection_command(self):
        t = TaskYAML(name="test", command="echo hi")
        assert t.get_task_type() == "command"

    def test_type_detection_invoke(self):
        t = TaskYAML(name="test", invoke=InvokeSpec(task="mod.fn"))
        assert t.get_task_type() == "invoke"

    def test_type_detection_steps(self):
        t = TaskYAML(name="test", steps=[])
        assert t.get_task_type() == "steps"

    def test_type_detection_git(self):
        t = TaskYAML(name="test", git=GitSpec(repo="https://github.com/test/repo"))
        assert t.get_task_type() == "git"

    def test_type_detection_no_command_no_invoke(self):
        t = TaskYAML(name="test")
        assert t.get_task_type() == "command"

    def test_get_effective_command_none(self):
        t = TaskYAML(name="test")
        assert t.get_effective_command() is None

    def test_get_effective_command_single(self):
        t = TaskYAML(name="test", command="echo hi")
        assert t.get_effective_command() == "echo hi"

    def test_get_effective_command_commands_single(self):
        t = TaskYAML(name="test", commands=["echo hi"])
        assert t.get_effective_command() == "echo hi"

    def test_get_effective_command_commands_multiple(self):
        t = TaskYAML(name="test", commands=["echo 1", "echo 2"])
        assert t.get_effective_command() is None


class TestOptionsYAMLBoundary:
    def test_on_failure_values(self):
        o = OptionsYAML(on_failure="continue")
        assert o.on_failure == "continue"

    def test_on_failure_default(self):
        o = OptionsYAML()
        assert o.on_failure == "fail"

    def test_timeout_default(self):
        o = OptionsYAML()
        assert o.timeout is None

    def test_timeout_set(self):
        o = OptionsYAML(timeout=300)
        assert o.timeout == 300

    def test_host_default(self):
        o = OptionsYAML()
        assert o.host is None

    def test_env_default(self):
        o = OptionsYAML()
        assert o.env == {}

    def test_env_set(self):
        o = OptionsYAML(env={"A": "1", "B": "2"})
        assert o.env == {"A": "1", "B": "2"}


class TestPipelineConfigBoundary:
    def test_defaults(self):
        c = PipelineConfig()
        assert c.host is None
        assert c.credential is None
        assert c.env == {}
        assert c.timeout is None
        assert c.retry == 0
        assert c.on_failure == "fail"
        assert c.execution_strategy == "sequential"


class TestPipelineYAMLBoundary:
    def test_name_required(self):
        with pytest.raises(ValidationError):
            PipelineYAML()

    def test_tasks_default(self):
        p = PipelineYAML(name="test")
        assert p.tasks is None

    def test_options_default(self):
        p = PipelineYAML(name="test")
        assert p.options is None

    def test_multiple_tasks(self):
        p = PipelineYAML(
            name="build",
            tasks=[
                TaskYAML(name="step1", command="echo 1"),
                TaskYAML(name="step2", command="echo 2"),
                TaskYAML(name="step3", command="echo 3"),
            ],
        )
        assert p.tasks is not None
        assert len(p.tasks) == 3

    def test_get_effective_config_none(self):
        p = PipelineYAML(name="test")
        cfg = p.get_effective_config()
        assert isinstance(cfg, PipelineConfig)


class TestCreateRunRequestBoundary:
    def test_pipeline_required(self):
        with pytest.raises(ValidationError):
            CreateRunRequest()

    def test_params_default(self):
        req = CreateRunRequest(pipeline="test")
        assert req.params == {}

    def test_params_complex(self):
        req = CreateRunRequest(
            pipeline="test",
            params={"nested": {"key": "value"}, "list": [1, 2, 3]},
        )
        assert req.params["nested"]["key"] == "value"


class TestCleanRequestBoundary:
    def test_defaults(self):
        req = CleanRequest()
        assert req.force is False
        assert req.older_than is None

    def test_older_than_set(self):
        req = CleanRequest(older_than=30)
        assert req.older_than == 30

    def test_keep_set(self):
        req = CleanRequest(keep=10)
        assert req.keep == 10


class TestCreateTriggerRequestBoundary:
    def test_pipeline_file_required(self):
        with pytest.raises(ValidationError):
            CreateTriggerRequest()

    def test_type_default(self):
        req = CreateTriggerRequest(pipeline_file="deploy.yaml")
        assert req.type == TriggerType.CRON

    def test_config_default(self):
        req = CreateTriggerRequest(pipeline_file="deploy.yaml")
        assert req.config == {}

    def test_enabled_default(self):
        req = CreateTriggerRequest(pipeline_file="deploy.yaml")
        assert req.enabled is True

    def test_enabled_false(self):
        req = CreateTriggerRequest(
            type=TriggerType.CRON,
            config={"schedule": "* * * * *"},
            pipeline_file="deploy.yaml",
            enabled=False,
        )
        assert req.enabled is False


class TestInvokeSpecBoundary:
    def test_task_required(self):
        with pytest.raises(ValidationError):
            InvokeSpec()

    def test_args_default(self):
        spec = InvokeSpec(task="mod.fn")
        assert spec.args == []

    def test_kwargs_default(self):
        spec = InvokeSpec(task="mod.fn")
        assert spec.kwargs == {}

    def test_args_set(self):
        spec = InvokeSpec(task="mod.fn", args=[1, 2, 3])
        assert spec.args == [1, 2, 3]

    def test_kwargs_set(self):
        spec = InvokeSpec(task="mod.fn", kwargs={"key": "val"})
        assert spec.kwargs == {"key": "val"}


class TestAgentCheckRequestBoundary:
    def test_defaults(self):
        req = AgentCheckRequest()
        assert req.agent_id is None
        assert req.file_filter is None
        assert req.timeout == 5

    def test_with_agent_id(self):
        req = AgentCheckRequest(agent_id="agent-1", timeout=10)
        assert req.agent_id == "agent-1"
        assert req.timeout == 10


class TestAgentExecRequestBoundary:
    def test_command_required(self):
        with pytest.raises(ValidationError):
            AgentExecRequest()

    def test_defaults(self):
        req = AgentExecRequest(command="echo hi")
        assert req.timeout == 60
        assert req.cwd == ""
        assert req.env is None

    def test_full(self):
        req = AgentExecRequest(
            command="echo $KEY",
            timeout=30,
            cwd="/tmp",
            env={"KEY": "VALUE"},
        )
        assert req.command == "echo $KEY"
        assert req.timeout == 30
        assert req.cwd == "/tmp"
        assert req.env == {"KEY": "VALUE"}
from __future__ import annotations

import pytest
from pydantic import ValidationError

from taskpps.models.trigger import TriggerType
from taskpps.schemas.agent import AgentCheckRequest, AgentExecRequest
from taskpps.schemas.pipeline import GitSpec, InvokeSpec, OptionsYAML, PipelineConfig, PipelineYAML, TaskYAML
from taskpps.schemas.run import CleanRequest, CreateRunRequest
from taskpps.schemas.trigger import CreateTriggerRequest


class TestTaskYAMLBoundary:
    def test_name_required(self):
        with pytest.raises(ValidationError):
            TaskYAML()

    def test_empty_name(self):
        t = TaskYAML(name="")
        assert t.name == ""

    @pytest.mark.zentao("TC-S0681", domain="server/schemas", priority="P1")
    def test_depends_on_empty(self):
        t = TaskYAML(name="test", command="echo hi")
        assert t.depends_on == []

    @pytest.mark.zentao("TC-S0682", domain="server/schemas", priority="P1")
    def test_depends_on_list(self):
        t = TaskYAML(name="test", command="echo hi", depends_on=["step1", "step2"])
        assert t.depends_on == ["step1", "step2"]

    @pytest.mark.zentao("TC-S0683", domain="server/schemas", priority="P1")
    def test_retry_default(self):
        t = TaskYAML(name="test", command="echo hi")
        assert t.retry == 0

    @pytest.mark.zentao("TC-S0684", domain="server/schemas", priority="P1")
    def test_retry_set(self):
        t = TaskYAML(name="test", command="echo hi", retry=3)
        assert t.retry == 3

    @pytest.mark.zentao("TC-S0685", domain="server/schemas", priority="P1")
    def test_retry_negative(self):
        t = TaskYAML(name="test", command="echo hi", retry=-1)
        assert t.retry == -1

    @pytest.mark.zentao("TC-S0686", domain="server/schemas", priority="P2")
    def test_type_detection_command(self):
        t = TaskYAML(name="test", command="echo hi")
        assert t.get_task_type() == "command"

    @pytest.mark.zentao("TC-S0687", domain="server/schemas", priority="P1")
    def test_type_detection_invoke(self):
        t = TaskYAML(name="test", invoke=InvokeSpec(task="mod.fn"))
        assert t.get_task_type() == "invoke"

    @pytest.mark.zentao("TC-S0688", domain="server/schemas", priority="P2")
    def test_type_detection_steps(self):
        t = TaskYAML(name="test", steps=[])
        assert t.get_task_type() == "steps"

    @pytest.mark.zentao("TC-S0689", domain="server/schemas", priority="P1")
    def test_type_detection_git(self):
        t = TaskYAML(name="test", git=GitSpec(repo="https://github.com/test/repo"))
        assert t.get_task_type() == "git"

    @pytest.mark.zentao("TC-S0690", domain="server/schemas", priority="P1")
    def test_type_detection_no_command_no_invoke(self):
        t = TaskYAML(name="test")
        assert t.get_task_type() == "command"

    @pytest.mark.zentao("TC-S0691", domain="server/schemas", priority="P2")
    def test_get_effective_command_none(self):
        t = TaskYAML(name="test")
        assert t.get_effective_command() is None

    @pytest.mark.zentao("TC-S0692", domain="server/schemas", priority="P2")
    def test_get_effective_command_single(self):
        t = TaskYAML(name="test", command="echo hi")
        assert t.get_effective_command() == "echo hi"

    @pytest.mark.zentao("TC-S0693", domain="server/schemas", priority="P2")
    def test_get_effective_command_commands_single(self):
        t = TaskYAML(name="test", commands=["echo hi"])
        assert t.get_effective_command() == "echo hi"

    @pytest.mark.zentao("TC-S0694", domain="server/schemas", priority="P2")
    def test_get_effective_command_commands_multiple(self):
        t = TaskYAML(name="test", commands=["echo 1", "echo 2"])
        assert t.get_effective_command() is None


class TestOptionsYAMLBoundary:
    @pytest.mark.zentao("TC-S0695", domain="server/schemas", priority="P1")
    def test_on_failure_values(self):
        o = OptionsYAML(on_failure="continue")
        assert o.on_failure == "continue"

    @pytest.mark.zentao("TC-S0696", domain="server/schemas", priority="P1")
    def test_on_failure_default(self):
        o = OptionsYAML()
        assert o.on_failure == "fail"

    @pytest.mark.zentao("TC-S0697", domain="server/schemas", priority="P1")
    def test_timeout_default(self):
        o = OptionsYAML()
        assert o.timeout is None

    @pytest.mark.zentao("TC-S0698", domain="server/schemas", priority="P1")
    def test_timeout_set(self):
        o = OptionsYAML(timeout=300)
        assert o.timeout == 300

    @pytest.mark.zentao("TC-S0699", domain="server/schemas", priority="P2")
    def test_host_default(self):
        o = OptionsYAML()
        assert o.host is None

    @pytest.mark.zentao("TC-S0700", domain="server/schemas", priority="P1")
    def test_env_default(self):
        o = OptionsYAML()
        assert o.env == {}

    @pytest.mark.zentao("TC-S0701", domain="server/schemas", priority="P1")
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

    @pytest.mark.zentao("TC-S0702", domain="server/schemas", priority="P2")
    def test_tasks_default(self):
        p = PipelineYAML(name="test")
        assert p.tasks is None

    @pytest.mark.zentao("TC-S0703", domain="server/schemas", priority="P2")
    def test_options_default(self):
        p = PipelineYAML(name="test")
        assert p.options is None

    @pytest.mark.zentao("TC-S0704", domain="server/schemas", priority="P2")
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

    @pytest.mark.zentao("TC-S0705", domain="server/schemas", priority="P1")
    def test_get_effective_config_none(self):
        p = PipelineYAML(name="test")
        cfg = p.get_effective_config()
        assert isinstance(cfg, PipelineConfig)


class TestCreateRunRequestBoundary:
    @pytest.mark.zentao("TC-S0706", domain="server/schemas", priority="P2")
    def test_pipeline_required(self):
        with pytest.raises(ValidationError):
            CreateRunRequest()

    @pytest.mark.zentao("TC-S0707", domain="server/schemas", priority="P2")
    def test_params_default(self):
        req = CreateRunRequest(pipeline="test")
        assert req.params == {}

    @pytest.mark.zentao("TC-S0708", domain="server/schemas", priority="P2")
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

    @pytest.mark.zentao("TC-S0709", domain="server/schemas", priority="P2")
    def test_older_than_set(self):
        req = CleanRequest(older_than=30)
        assert req.older_than == 30

    @pytest.mark.zentao("TC-S0710", domain="server/schemas", priority="P2")
    def test_keep_set(self):
        req = CleanRequest(keep=10)
        assert req.keep == 10


class TestCreateTriggerRequestBoundary:
    @pytest.mark.zentao("TC-S0711", domain="server/schemas", priority="P2")
    def test_pipeline_file_required(self):
        with pytest.raises(ValidationError):
            CreateTriggerRequest()

    @pytest.mark.zentao("TC-S0712", domain="server/schemas", priority="P2")
    def test_type_default(self):
        req = CreateTriggerRequest(pipeline_file="deploy.yaml")
        assert req.type == TriggerType.CRON

    @pytest.mark.zentao("TC-S0713", domain="server/schemas", priority="P1")
    def test_config_default(self):
        req = CreateTriggerRequest(pipeline_file="deploy.yaml")
        assert req.config == {}

    @pytest.mark.zentao("TC-S0714", domain="server/schemas", priority="P2")
    def test_enabled_default(self):
        req = CreateTriggerRequest(pipeline_file="deploy.yaml")
        assert req.enabled is True

    @pytest.mark.zentao("TC-S0715", domain="server/schemas", priority="P2")
    def test_enabled_false(self):
        req = CreateTriggerRequest(
            type=TriggerType.CRON,
            config={"schedule": "* * * * *"},
            pipeline_file="deploy.yaml",
            enabled=False,
        )
        assert req.enabled is False


class TestInvokeSpecBoundary:
    @pytest.mark.zentao("TC-S0716", domain="server/schemas", priority="P2")
    def test_task_required(self):
        with pytest.raises(ValidationError):
            InvokeSpec()

    @pytest.mark.zentao("TC-S0717", domain="server/schemas", priority="P2")
    def test_args_default(self):
        spec = InvokeSpec(task="mod.fn")
        assert spec.args == []

    @pytest.mark.zentao("TC-S0718", domain="server/schemas", priority="P2")
    def test_kwargs_default(self):
        spec = InvokeSpec(task="mod.fn")
        assert spec.kwargs == {}

    @pytest.mark.zentao("TC-S0719", domain="server/schemas", priority="P2")
    def test_args_set(self):
        spec = InvokeSpec(task="mod.fn", args=[1, 2, 3])
        assert spec.args == [1, 2, 3]

    @pytest.mark.zentao("TC-S0720", domain="server/schemas", priority="P2")
    def test_kwargs_set(self):
        spec = InvokeSpec(task="mod.fn", kwargs={"key": "val"})
        assert spec.kwargs == {"key": "val"}


class TestAgentCheckRequestBoundary:
    def test_defaults(self):
        req = AgentCheckRequest()
        assert req.agent_id is None
        assert req.file_filter is None
        assert req.timeout == 5

    @pytest.mark.zentao("TC-S0721", domain="server/schemas", priority="P2")
    def test_with_agent_id(self):
        req = AgentCheckRequest(agent_id="agent-1", timeout=10)
        assert req.agent_id == "agent-1"
        assert req.timeout == 10


class TestAgentExecRequestBoundary:
    @pytest.mark.zentao("TC-S0722", domain="server/schemas", priority="P2")
    def test_command_required(self):
        with pytest.raises(ValidationError):
            AgentExecRequest()

    def test_defaults(self):
        req = AgentExecRequest(command="echo hi")
        assert req.timeout == 60
        assert req.cwd == ""
        assert req.env is None

    @pytest.mark.zentao("TC-S0723", domain="server/schemas", priority="P2")
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


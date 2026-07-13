from __future__ import annotations

from taskpps.models.project import Project
from taskpps.models.run import PipelineRun, TaskRun, TaskType
from taskpps.models.trigger import Trigger, TriggerType


class TestPipelineRun:
    def test_create_with_required_fields(self):
        run = PipelineRun(pipeline_name="test-pipeline")
        assert run.id is not None
        assert len(run.id) == 12
        assert run.pipeline_name == "test-pipeline"
        assert run.created_at is not None

    def test_create_with_all_fields(self):
        run = PipelineRun(
            pipeline_name="full",
            pipeline_file="deploy.yaml",
            pipeline_id="deploy",
            pipeline_version="abc12345",
            project_id="proj001",
            params='{"key": "val"}',
        )
        assert run.pipeline_file == "deploy.yaml"
        assert run.pipeline_id == "deploy"
        assert run.pipeline_version == "abc12345"
        assert run.project_id == "proj001"
        assert run.params == '{"key": "val"}'

    def test_project_id_default_none(self):
        run = PipelineRun(pipeline_name="test")
        assert run.project_id is None

    def test_unique_ids(self):
        r1 = PipelineRun(pipeline_name="p1")
        r2 = PipelineRun(pipeline_name="p2")
        assert r1.id != r2.id


class TestTaskRun:
    def test_create_with_required_fields(self):
        task = TaskRun(run_id="abc123", task_name="step1")
        assert task.id is not None
        assert len(task.id) == 12
        assert task.run_id == "abc123"
        assert task.task_name == "step1"
        assert task.task_type == TaskType.COMMAND

    def test_create_with_all_fields(self):
        task = TaskRun(
            run_id="abc123",
            task_name="step1",
            subpipeline_name="sub1",
            task_type=TaskType.STEPS,
            log_path="/logs/step1.log",
            exit_code=0,
        )
        assert task.subpipeline_name == "sub1"
        assert task.task_type == TaskType.STEPS
        assert task.log_path == "/logs/step1.log"

    def test_unique_ids(self):
        t1 = TaskRun(run_id="r1", task_name="a")
        t2 = TaskRun(run_id="r1", task_name="b")
        assert t1.id != t2.id


class TestTrigger:
    def test_create_with_required_fields(self):
        trigger = Trigger(type=TriggerType.CRON, config="{}", definition_id="test.yaml")
        assert trigger.id is not None
        assert trigger.type == TriggerType.CRON
        assert trigger.definition_id == "test.yaml"

    def test_create_with_all_fields(self):
        trigger = Trigger(
            type=TriggerType.WEBHOOK,
            config='{"url": "https://example.com"}',
            definition_id="webhook.yaml",
            project_id="proj001",
            enabled=False,
        )
        assert trigger.type == TriggerType.WEBHOOK
        assert trigger.project_id == "proj001"
        assert trigger.enabled is False

    def test_project_id_default_none(self):
        trigger = Trigger(type=TriggerType.CRON, config="{}", definition_id="test.yaml")
        assert trigger.project_id is None


class TestProject:
    def test_create_with_required_fields(self):
        project = Project(workdir="/opt/project-a")
        assert project.id is not None
        assert len(project.id) == 12
        assert project.workdir == "/opt/project-a"
        assert project.name == ""
        assert project.active is True
        assert project.registered_at is not None

    def test_create_with_all_fields(self):
        project = Project(
            name="my-project",
            workdir="/opt/project-b",
            active=False,
        )
        assert project.name == "my-project"
        assert project.workdir == "/opt/project-b"
        assert project.active is False

    def test_unique_ids(self):
        p1 = Project(workdir="/a")
        p2 = Project(workdir="/b")
        assert p1.id != p2.id

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from taskpps.models.run import PipelineRun, TaskRun, RunStatus, TaskStatus, TaskType


class TestRunStatus:
    def test_all_statuses_defined(self):
        assert RunStatus.PENDING == "pending"
        assert RunStatus.RUNNING == "running"
        assert RunStatus.SUCCESS == "success"
        assert RunStatus.FAILED == "failed"
        assert RunStatus.CANCELLED == "cancelled"
        assert RunStatus.PARTIAL == "partial"

    def test_status_comparison(self):
        assert RunStatus.PENDING != RunStatus.SUCCESS
        assert RunStatus.RUNNING == RunStatus.RUNNING


class TestTaskStatus:
    def test_all_statuses_defined(self):
        assert TaskStatus.PENDING == "pending"
        assert TaskStatus.RUNNING == "running"
        assert TaskStatus.SUCCESS == "success"
        assert TaskStatus.FAILED == "failed"
        assert TaskStatus.SKIPPED == "skipped"
        assert TaskStatus.CANCELLED == "cancelled"


class TestTaskType:
    def test_all_types_defined(self):
        assert TaskType.COMMAND == "command"
        assert TaskType.INVOKE == "invoke"
        assert TaskType.STEPS == "steps"
        assert TaskType.GIT == "git"
        assert TaskType.NEXUS == "nexus"
        assert TaskType.SSH == "ssh"


class TestPipelineRunModel:
    def test_run_defaults(self):
        run = PipelineRun(pipeline_name="test")
        assert run.pipeline_name == "test"
        assert run.pipeline_file == ""
        assert run.pipeline_id == ""
        assert run.pipeline_version == ""
        assert run.status == RunStatus.PENDING
        assert run.params == "{}"
        assert run.started_at is None
        assert run.finished_at is None

    def test_run_with_values(self):
        run = PipelineRun(
            pipeline_name="test",
            pipeline_file="deploy.yaml",
            pipeline_id="test-deploy",
            pipeline_version="abc123",
            params='{"key": "value"}',
        )
        assert run.pipeline_name == "test"
        assert run.pipeline_file == "deploy.yaml"
        assert run.pipeline_id == "test-deploy"
        assert run.pipeline_version == "abc123"
        assert run.params == '{"key": "value"}'

    def test_run_set_status(self):
        run = PipelineRun(pipeline_name="test")
        run.status = RunStatus.RUNNING
        assert run.status == RunStatus.RUNNING

    def test_run_set_timestamps(self):
        now = datetime.now(timezone.utc)
        run = PipelineRun(pipeline_name="test", started_at=now)
        assert run.started_at == now


class TestTaskRunModel:
    def test_task_run_defaults(self):
        task = TaskRun(run_id="run-1", task_name="build")
        assert task.run_id == "run-1"
        assert task.task_name == "build"
        assert task.subpipeline_name == ""
        assert task.task_type == TaskType.COMMAND
        assert task.status == TaskStatus.PENDING
        assert task.exit_code is None
        assert task.log_path == ""
        assert task.started_at is None
        assert task.finished_at is None

    def test_task_run_with_type(self):
        task = TaskRun(run_id="run-1", task_name="deploy", task_type=TaskType.INVOKE)
        assert task.task_type == TaskType.INVOKE

    def test_task_run_set_status(self):
        task = TaskRun(run_id="run-1", task_name="build")
        task.status = TaskStatus.RUNNING
        assert task.status == TaskStatus.RUNNING
        task.status = TaskStatus.SUCCESS
        task.exit_code = 0
        assert task.exit_code == 0

    def test_task_run_nonzero_exit_code(self):
        task = TaskRun(run_id="run-1", task_name="build")
        task.status = TaskStatus.FAILED
        task.exit_code = 1
        assert task.exit_code == 1

    def test_task_run_negative_exit_code(self):
        task = TaskRun(run_id="run-1", task_name="build")
        task.exit_code = -9
        assert task.exit_code == -9

    def test_task_run_with_log_path(self):
        task = TaskRun(
            run_id="run-1",
            task_name="build",
            log_path="/tmp/.taskpps/logs/build.log",
        )
        assert task.log_path == "/tmp/.taskpps/logs/build.log"
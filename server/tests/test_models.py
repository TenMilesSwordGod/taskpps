from taskpps.models.run import PipelineRun, RunStatus, TaskRun, TaskStatus, TaskType
from taskpps.models.trigger import Trigger, TriggerType


def test_pipeline_run_defaults():
    run = PipelineRun(pipeline_name="test")
    assert run.id is not None
    assert run.status == RunStatus.PENDING
    assert run.params == "{}"
    assert run.started_at is None
    assert run.finished_at is None
    assert run.created_at is not None


def test_task_run_defaults():
    task = TaskRun(run_id="abc", task_name="step1")
    assert task.id is not None
    assert task.status == TaskStatus.PENDING
    assert task.task_type == TaskType.COMMAND
    assert task.exit_code is None
    assert task.log_path == ""


def test_run_status_values():
    assert RunStatus.PENDING == "pending"
    assert RunStatus.RUNNING == "running"
    assert RunStatus.SUCCESS == "success"
    assert RunStatus.FAILED == "failed"
    assert RunStatus.CANCELLED == "cancelled"
    assert RunStatus.PARTIAL == "partial"


def test_task_status_values():
    assert TaskStatus.PENDING == "pending"
    assert TaskStatus.RUNNING == "running"
    assert TaskStatus.SUCCESS == "success"
    assert TaskStatus.FAILED == "failed"
    assert TaskStatus.SKIPPED == "skipped"
    assert TaskStatus.CANCELLED == "cancelled"


def test_task_type_values():
    assert TaskType.COMMAND == "command"
    assert TaskType.INVOKE == "invoke"


def test_trigger_defaults():
    trigger = Trigger(type=TriggerType.CRON, config="{}", pipeline_file="test.yaml")
    assert trigger.id is not None
    assert trigger.enabled is True
    assert trigger.created_at is not None


def test_trigger_type_values():
    assert TriggerType.CRON == "cron"
    assert TriggerType.WEBHOOK == "webhook"

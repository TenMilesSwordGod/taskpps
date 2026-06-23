from datetime import datetime
from typing import Any

from pydantic import BaseModel

from taskpps.models.run import RunStatus, TaskStatus, TaskType


class CreateRunRequest(BaseModel):
    pipeline: str
    params: dict[str, Any] = {}
    project_id: str | None = None


class TaskRunResponse(BaseModel):
    id: str
    run_id: str
    task_name: str
    subpipeline_name: str = ""
    task_type: TaskType
    status: TaskStatus
    exit_code: int | None = None
    error: str | None = None
    log_path: str = ""
    started_at: datetime | None = None
    finished_at: datetime | None = None
    created_at: datetime
    duration_ms: int | None = None

    model_config = {"from_attributes": True}


class RunResponse(BaseModel):
    id: str
    pipeline_name: str
    pipeline_file: str = ""
    pipeline_id: str = ""
    pipeline_version: str = ""
    project_id: str | None = None
    project_name: str | None = None
    display_name: str = ""
    version_changed: bool = False
    status: RunStatus
    error: str | None = None
    params: dict[str, Any] = {}
    console_log_path: str = ""
    started_at: datetime | None = None
    finished_at: datetime | None = None
    created_at: datetime
    tasks: list[TaskRunResponse] = []
    task_summary: dict[str, int] = {}
    duration_ms: int | None = None

    model_config = {"from_attributes": True}

    @classmethod
    def from_orm_with_parsed_params(cls, obj):
        import json

        data = {
            "id": obj.id,
            "pipeline_name": obj.pipeline_name,
            "pipeline_file": obj.pipeline_file,
            "pipeline_id": getattr(obj, "pipeline_id", ""),
            "pipeline_version": getattr(obj, "pipeline_version", ""),
            "project_id": getattr(obj, "project_id", None),
            "project_name": getattr(obj, "project_name", None),
            "display_name": getattr(obj, "display_name", ""),
            "version_changed": False,
            "status": obj.status,
            "error": getattr(obj, "error", None),
            "params": json.loads(obj.params) if isinstance(obj.params, str) else (obj.params or {}),
            "console_log_path": getattr(obj, "console_log_path", ""),
            "started_at": obj.started_at,
            "finished_at": obj.finished_at,
            "created_at": obj.created_at,
            "tasks": obj.tasks if hasattr(obj, "_tasks_loaded") else [],
            "task_summary": getattr(obj, "task_summary", {}),
        }
        return cls(**data)


class RunStatsResponse(BaseModel):
    total: int
    pending: int = 0
    running: int = 0
    success: int = 0
    failed: int = 0
    cancelled: int = 0
    partial: int = 0


class RunListResponse(BaseModel):
    items: list[RunResponse]
    total: int


class CleanRequest(BaseModel):
    older_than: int | None = None
    keep: int | None = None
    force: bool = False


class CleanResponse(BaseModel):
    deleted_runs: int
    deleted_logs: int


class RetryRequest(BaseModel):
    tasks: list[str] | None = None
    subpipeline: str | None = None
    include_upstream: bool = False
    command_overrides: dict[str, str] | None = None
    retry_execution_strategy: str = "parallel"


class RetryRecordResponse(BaseModel):
    id: str
    run_id: str
    task_run_id: str
    task_name: str
    subpipeline_name: str = ""
    retry_version: int
    status: TaskStatus
    command: str = ""
    original_command: str = ""
    log_path: str = ""
    exit_code: int | None = None
    error: str | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class RetryVersionsResponse(BaseModel):
    task_retries: dict[str, list[RetryRecordResponse]]
    selected: dict[str, str | None]


class RetryCommandResponse(BaseModel):
    retry_id: str
    task_name: str
    original_command: str
    resolved_command: str
    variables: dict[str, str] = {}
    editable: bool = True
    status: TaskStatus


class UpdateRetryCommandRequest(BaseModel):
    command: str


class SelectReportRequest(BaseModel):
    task_name: str
    selected_retry_id: str | None = None


class BatchSelectReportRequest(BaseModel):
    selections: dict[str, str]


class DependencyNode(BaseModel):
    name: str
    depends_on: list[str]
    level: int
    upstream_of_target: bool = False
    mandatory_if_upstream: bool = False


class DependencyTreeResponse(BaseModel):
    target: str
    subpipeline: str
    tree: list[DependencyNode]

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel

from taskpps.models.run import RunStatus, TaskStatus, TaskType


class CreateRunRequest(BaseModel):
    pipeline: str
    params: Dict[str, Any] = {}


class TaskRunResponse(BaseModel):
    id: str
    run_id: str
    task_name: str
    subpipeline_name: str = ""
    task_type: TaskType
    status: TaskStatus
    exit_code: Optional[int] = None
    log_path: str = ""
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class RunResponse(BaseModel):
    id: str
    pipeline_name: str
    pipeline_file: str = ""
    pipeline_id: str = ""
    pipeline_version: str = ""
    version_changed: bool = False
    status: RunStatus
    params: Dict[str, Any] = {}
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    created_at: datetime
    tasks: List[TaskRunResponse] = []

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
            "version_changed": False,
            "status": obj.status,
            "params": json.loads(obj.params) if isinstance(obj.params, str) else (obj.params or {}),
            "started_at": obj.started_at,
            "finished_at": obj.finished_at,
            "created_at": obj.created_at,
            "tasks": obj.tasks if hasattr(obj, '_tasks_loaded') else [],
        }
        return cls(**data)


class RunListResponse(BaseModel):
    items: List[RunResponse]
    total: int


class CleanRequest(BaseModel):
    older_than: Optional[int] = None
    keep: Optional[int] = None
    force: bool = False


class CleanResponse(BaseModel):
    deleted_runs: int
    deleted_logs: int

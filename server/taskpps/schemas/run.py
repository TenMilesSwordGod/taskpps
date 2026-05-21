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
    status: RunStatus
    params: str = "{}"
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    created_at: datetime
    tasks: List[TaskRunResponse] = []

    model_config = {"from_attributes": True}


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

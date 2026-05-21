import enum
import uuid
from datetime import datetime
from typing import Optional

from sqlmodel import Field, SQLModel


class RunStatus(str, enum.Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    CANCELLED = "cancelled"
    PARTIAL = "partial"


class TaskStatus(str, enum.Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"
    CANCELLED = "cancelled"


class TaskType(str, enum.Enum):
    COMMAND = "command"
    INVOKE = "invoke"


class PipelineRun(SQLModel, table=True):
    __tablename__ = "runs"

    id: str = Field(default_factory=lambda: uuid.uuid4().hex[:12], primary_key=True)
    pipeline_name: str
    pipeline_file: str = ""
    status: RunStatus = RunStatus.PENDING
    params: str = "{}"
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)


class TaskRun(SQLModel, table=True):
    __tablename__ = "task_runs"

    id: str = Field(default_factory=lambda: uuid.uuid4().hex[:12], primary_key=True)
    run_id: str = Field(foreign_key="runs.id")
    task_name: str
    task_type: TaskType = TaskType.COMMAND
    status: TaskStatus = TaskStatus.PENDING
    exit_code: Optional[int] = None
    log_path: str = ""
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)

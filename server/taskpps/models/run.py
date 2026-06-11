import enum
import uuid
from datetime import datetime, timezone

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
    STEPS = "steps"
    GIT = "git"
    NEXUS = "nexus"
    SSH = "ssh"


class PipelineRun(SQLModel, table=True):
    __tablename__ = "runs"

    id: str = Field(default_factory=lambda: uuid.uuid4().hex[:12], primary_key=True)
    pipeline_name: str
    pipeline_file: str = ""
    pipeline_id: str = ""
    pipeline_version: str = ""
    project_id: str | None = None
    status: RunStatus = RunStatus.PENDING
    error: str | None = Field(default=None)
    params: str = "{}"
    started_at: datetime | None = None
    finished_at: datetime | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class TaskRun(SQLModel, table=True):
    __tablename__ = "task_runs"

    id: str = Field(default_factory=lambda: uuid.uuid4().hex[:12], primary_key=True)
    run_id: str = Field(foreign_key="runs.id")
    task_name: str
    subpipeline_name: str = ""
    task_type: TaskType = TaskType.COMMAND
    status: TaskStatus = TaskStatus.PENDING
    exit_code: int | None = None
    error: str | None = Field(default=None)
    log_path: str = ""
    started_at: datetime | None = None
    finished_at: datetime | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

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
    PLUGIN = "plugin"


class PipelineRun(SQLModel, table=True):
    __tablename__ = "runs"

    id: str = Field(default_factory=lambda: uuid.uuid4().hex[:12], primary_key=True)
    pipeline_name: str
    pipeline_file: str = Field(default="", index=True)
    pipeline_id: str = Field(default="", index=True)
    pipeline_version: str = ""
    project_id: str | None = Field(default=None, index=True)
    definition_id: str | None = Field(default=None, foreign_key="pipeline_definitions.id")
    display_name: str = ""
    status: RunStatus = RunStatus.PENDING
    error: str | None = Field(default=None)
    # 触发本次运行的登录用户 username（来自 JWT sub）；历史数据/系统触发为 None
    operator: str | None = Field(default=None, index=True)
    snapshot_content: str | None = Field(default=None)
    params: str = "{}"
    started_at: datetime | None = None
    finished_at: datetime | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), index=True)


class TaskRun(SQLModel, table=True):
    __tablename__ = "task_runs"

    id: str = Field(default_factory=lambda: uuid.uuid4().hex[:12], primary_key=True)
    run_id: str = Field(foreign_key="runs.id", ondelete="CASCADE", index=True)
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
    selected_retry_id: str | None = Field(default=None)


class TaskRetryRecord(SQLModel, table=True):
    __tablename__ = "task_retry_records"

    id: str = Field(default_factory=lambda: uuid.uuid4().hex[:12], primary_key=True)
    run_id: str = Field(foreign_key="runs.id", ondelete="CASCADE", index=True)
    task_run_id: str = Field(foreign_key="task_runs.id", ondelete="CASCADE", index=True)
    task_name: str = Field(index=True)
    subpipeline_name: str = ""
    retry_version: int
    status: TaskStatus = TaskStatus.PENDING
    command: str = ""
    original_command: str = ""
    log_path: str = ""
    exit_code: int | None = None
    error: str | None = Field(default=None)
    started_at: datetime | None = None
    finished_at: datetime | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

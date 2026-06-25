from datetime import datetime, timezone

from sqlalchemy import UniqueConstraint
from sqlmodel import Field, SQLModel


class Artifact(SQLModel, table=True):
    __tablename__ = "artifacts"
    __table_args__ = (
        UniqueConstraint("run_id", "task_name", "path", name="uq_artifact_run_task_path"),
    )

    id: str = Field(default_factory=lambda: __import__("uuid").uuid4().hex[:12], primary_key=True)
    run_id: str = Field(foreign_key="runs.id", ondelete="CASCADE", index=True)
    task_name: str = Field(default="default", index=True)
    path: str
    size: int = 0
    content_type: str = "application/octet-stream"
    mtime: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

import uuid
from datetime import datetime, timezone

from sqlmodel import Field, SQLModel


class PipelineDefinition(SQLModel, table=True):
    __tablename__ = "pipeline_definitions"

    id: str = Field(default_factory=lambda: uuid.uuid4().hex[:12], primary_key=True)
    project_id: str = Field(foreign_key="projects.id", index=True)
    file_path: str = Field(index=True)
    name: str = ""
    content: str = "{}"
    raw_content: str = ""
    file_hash: str = ""
    active: bool = True
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

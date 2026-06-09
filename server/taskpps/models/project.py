import uuid
from datetime import datetime, timezone

from sqlmodel import Field, SQLModel


class Project(SQLModel, table=True):
    __tablename__ = "projects"

    id: str = Field(default_factory=lambda: uuid.uuid4().hex[:12], primary_key=True)
    name: str = ""
    workdir: str
    registered_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    last_used_at: datetime | None = None
    active: bool = True

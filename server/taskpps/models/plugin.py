import uuid
from datetime import datetime, timezone

from sqlmodel import Field, SQLModel


class Plugin(SQLModel, table=True):
    __tablename__ = "plugin"

    id: str = Field(default_factory=lambda: uuid.uuid4().hex[:12], primary_key=True)
    name: str = Field(index=True, unique=True)
    type: str = Field(default="")
    version: str = Field(default="")
    enabled: bool = Field(default=False)
    help_msg: str = Field(default="")
    config: str = Field(default="{}")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

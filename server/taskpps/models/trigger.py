import enum
import uuid
from datetime import datetime, timezone

from sqlmodel import Field, SQLModel


class TriggerType(str, enum.Enum):
    CRON = "cron"
    WEBHOOK = "webhook"


class Trigger(SQLModel, table=True):
    __tablename__ = "triggers"

    id: str = Field(default_factory=lambda: uuid.uuid4().hex[:12], primary_key=True)
    type: TriggerType = TriggerType.CRON
    config: str = "{}"
    definition_id: str = ""
    project_id: str | None = None
    enabled: bool = True
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

import enum
import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlmodel import Field, SQLModel


class TriggerType(str, enum.Enum):
    CRON = "cron"
    WEBHOOK = "webhook"


class Trigger(SQLModel, table=True):
    __tablename__ = "triggers"

    id: str = Field(default_factory=lambda: uuid.uuid4().hex[:12], primary_key=True)
    type: TriggerType = TriggerType.CRON
    config: str = "{}"
    pipeline_file: str = ""
    enabled: bool = True
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

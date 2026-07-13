from datetime import datetime
from typing import Any

from pydantic import BaseModel

from taskpps.models.trigger import TriggerType


class CreateTriggerRequest(BaseModel):
    type: TriggerType = TriggerType.CRON
    config: dict[str, Any] = {}
    definition_id: str
    project_id: str | None = None
    enabled: bool = True


class TriggerResponse(BaseModel):
    id: str
    type: TriggerType
    config: dict[str, Any] = {}
    definition_id: str
    project_id: str | None = None
    enabled: bool
    created_at: datetime

    model_config = {"from_attributes": True}

    @classmethod
    def from_orm_with_parsed_config(cls, obj):
        import json

        data = {
            "id": obj.id,
            "type": obj.type,
            "config": json.loads(obj.config) if isinstance(obj.config, str) else obj.config,
            "definition_id": obj.definition_id,
            "project_id": getattr(obj, "project_id", None),
            "enabled": obj.enabled,
            "created_at": obj.created_at,
        }
        return cls(**data)

from datetime import datetime
from typing import Any, Dict, Optional

from pydantic import BaseModel

from taskpps.models.trigger import TriggerType


class CreateTriggerRequest(BaseModel):
    type: TriggerType = TriggerType.CRON
    config: Dict[str, Any] = {}
    pipeline_file: str
    enabled: bool = True


class TriggerResponse(BaseModel):
    id: str
    type: TriggerType
    config: str = "{}"
    pipeline_file: str
    enabled: bool
    created_at: datetime

    model_config = {"from_attributes": True}

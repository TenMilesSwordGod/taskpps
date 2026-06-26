from datetime import datetime

from pydantic import BaseModel


class PluginResponse(BaseModel):
    id: str
    name: str
    type: str
    version: str
    enabled: bool
    help_msg: str
    config: str
    status: str = "unknown"
    created_at: datetime | None = None
    updated_at: datetime | None = None

    model_config = {"from_attributes": True}

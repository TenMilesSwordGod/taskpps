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
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}

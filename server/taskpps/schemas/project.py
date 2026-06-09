from datetime import datetime

from pydantic import BaseModel


class CreateProjectRequest(BaseModel):
    workdir: str
    name: str = ""


class ProjectResponse(BaseModel):
    id: str
    name: str
    workdir: str
    registered_at: datetime
    last_used_at: datetime | None = None
    active: bool = True

    model_config = {"from_attributes": True}

from datetime import datetime

from pydantic import BaseModel


class ArtifactItem(BaseModel):
    task_name: str
    path: str
    size: int
    mtime: datetime
    content_type: str


class ArtifactListResponse(BaseModel):
    run_id: str
    default: list[ArtifactItem] = []
    artifacts: list[ArtifactItem] = []


class PromoteRequest(BaseModel):
    task_name: str
    path: str
    move: bool = False


class PromoteResponse(BaseModel):
    artifact: ArtifactItem


class UploadResponse(BaseModel):
    uploaded: list[ArtifactItem]


class ArtifactRef(BaseModel):
    """Parsed ${artifact:...} reference."""

    run_id: str | None = None
    subpipeline: str | None = None
    task_name: str
    path: str

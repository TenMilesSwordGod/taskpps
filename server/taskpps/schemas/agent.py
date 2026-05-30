from typing import List, Optional

from pydantic import BaseModel


class AgentCheckRequest(BaseModel):
    agent_id: Optional[str] = None
    file_filter: Optional[str] = None
    timeout: int = 5


class AgentCheckResult(BaseModel):
    agent_id: str
    name: str
    type: str
    host: str
    port: int
    source_file: str
    status: str
    latency_ms: int
    error: Optional[str] = None


class AgentCheckSummary(BaseModel):
    total: int
    connected: int
    failed: int


class AgentCheckResponse(BaseModel):
    results: List[AgentCheckResult]
    summary: AgentCheckSummary
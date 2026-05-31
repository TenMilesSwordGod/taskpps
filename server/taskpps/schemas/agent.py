from pydantic import BaseModel


class AgentCheckRequest(BaseModel):
    agent_id: str | None = None
    file_filter: str | None = None
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
    error: str | None = None


class AgentCheckSummary(BaseModel):
    total: int
    connected: int
    failed: int


class AgentCheckResponse(BaseModel):
    results: list[AgentCheckResult]
    summary: AgentCheckSummary

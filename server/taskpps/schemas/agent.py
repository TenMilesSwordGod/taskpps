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


class AgentStatus(BaseModel):
    agent_id: str
    connected: bool
    hostname: str = ""
    agent_version: str = ""
    agent_pid: int = 0
    connected_at: float = 0
    last_heartbeat: float = 0
    running_commands: int = 0


class AgentDeployRequest(BaseModel):
    agent_id: str
    timeout: int = 30


class AgentExecRequest(BaseModel):
    command: str
    timeout: int = 60
    cwd: str = ""
    env: dict[str, str] | None = None


class AgentExecResult(BaseModel):
    agent_id: str
    exit_code: int
    stdout: str = ""
    stderr: str = ""
    duration_ms: int = 0
    error: str | None = None


class AgentDeployResult(BaseModel):
    success: bool
    agent_id: str
    agent_pid: int = 0
    error: str | None = None

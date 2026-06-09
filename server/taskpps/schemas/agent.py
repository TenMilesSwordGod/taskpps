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
    # 远端系统信息（SSH 认证成功后通过 uname 获取）
    system: str = ""  # 操作系统内核名（Linux/Darwin/Windows）
    arch: str = ""  # CPU 架构（x86_64/aarch64/...）
    platform: str = ""  # system/arch 简写
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
    platform: str = ""
    system: str = ""
    arch: str = ""
    ip: str = ""
    agent_version: str = ""
    agent_pid: int = 0
    connected_at: float = 0
    last_heartbeat: float = 0
    running_commands: int = 0


class AgentWithConfig(BaseModel):
    """合并 agent yaml 配置与实时连接状态"""

    agent_id: str
    name: str = ""
    type: str = ""
    host: str = ""
    port: int = 0
    source_file: str = ""
    connected: bool = False
    # 实时状态字段（未连接时为空）
    hostname: str = ""
    platform: str = ""
    system: str = ""
    arch: str = ""
    ip: str = ""
    agent_version: str = ""
    agent_pid: int = 0
    connected_at: float = 0
    last_heartbeat: float = 0
    running_commands: int = 0
    # 网络可达性：unknown / reachable / unreachable
    net_status: str = "unknown"


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


class CpuInfo(BaseModel):
    model: str = ""
    cores: int = 0
    threads: int = 0


class MemoryInfo(BaseModel):
    total: str = ""
    used: str = ""
    free: str = ""
    percent: int = -1  # -1 表示未知


class DiskInfo(BaseModel):
    mount: str = ""
    filesystem: str = ""
    size: str = ""
    used: str = ""
    avail: str = ""
    percent: int = -1


class AgentHostInfo(BaseModel):
    agent_id: str
    hostname: str = ""
    kernel: str = ""
    os_release: str = ""
    uptime: str = ""
    cpu: CpuInfo = CpuInfo()
    memory: MemoryInfo = MemoryInfo()
    disks: list[DiskInfo] = []
    error: str | None = None
    source: str = ""  # "ssh" / "agent" / "none"

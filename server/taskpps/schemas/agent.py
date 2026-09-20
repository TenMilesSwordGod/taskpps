from pydantic import BaseModel, field_validator

from taskpps.schemas.common import RESOURCE_ID_PATTERN


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
    queued_commands: int = 0
    max_parallel: int = 1


class AgentWithConfig(BaseModel):
    """合并 agent yaml 配置与实时连接状态"""

    agent_id: str
    name: str = ""
    description: str = ""
    type: str = ""
    host: str = ""
    port: int = 0
    source_file: str = ""
    connected: bool = False
    # 所属项目信息
    project_id: str = ""
    project_name: str = ""
    # 配置回填字段（编辑弹窗需要，不包含任何凭据密文）
    username: str = ""
    credential_id: str = ""
    execution_agent: bool = True
    agent_auto_bootstrap: bool = True
    # agent 回连服务端的地址（留空则服务端自动探测）；远端无法反连探测 IP 时靠它覆盖
    server_ws_host: str = ""
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
    queued_commands: int = 0
    max_parallel: int = 1
    # 网络可达性：unknown / reachable / unreachable
    net_status: str = "unknown"
    # 最近一次命令执行完成时间（Unix 时间戳，秒）
    last_execution_time: float = 0


def _validate_resource_id(v: str) -> str:
    import re

    if not re.match(RESOURCE_ID_PATTERN, v or ""):
        raise ValueError("ID 只能包含字母、数字、下划线、点和短横线，且以字母或数字开头")
    return v


class AgentConfigCreateRequest(BaseModel):
    """新建 agent 配置（仅暴露网页表单字段，其余 YAML 高级字段保持未知不写）。"""

    project_id: str
    id: str
    name: str = ""
    description: str = ""
    type: str = "ssh-username-password"
    host: str = ""
    port: int = 22
    username: str = "root"
    credential_id: str = ""
    max_parallel: int = 1
    execution_agent: bool = True
    agent_auto_bootstrap: bool = True
    # v2 (2026-09): 暴露给网页表单。服务端自动探测的 IP 对远端主机可能不可达，
    # 没有这个字段时用户只能手改 YAML，部署会一直等待握手直到超时。
    server_ws_host: str = ""

    @field_validator("id")
    @classmethod
    def _check_id(cls, v: str) -> str:
        return _validate_resource_id(v)

    @field_validator("port")
    @classmethod
    def _check_port(cls, v: int) -> int:
        if not 1 <= v <= 65535:
            raise ValueError("端口必须在 1-65535 之间")
        return v


class AgentConfigUpdateRequest(BaseModel):
    """编辑 agent 配置：只提交需要变更的字段，未知 YAML 字段由服务层保留。"""

    name: str | None = None
    description: str | None = None
    type: str | None = None
    host: str | None = None
    port: int | None = None
    username: str | None = None
    credential_id: str | None = None
    max_parallel: int | None = None
    execution_agent: bool | None = None
    agent_auto_bootstrap: bool | None = None
    # v2 (2026-09): 与 create 对齐，编辑时允许覆盖/清空回连地址
    server_ws_host: str | None = None

    @field_validator("port")
    @classmethod
    def _check_port(cls, v: int | None) -> int | None:
        if v is not None and not 1 <= v <= 65535:
            raise ValueError("端口必须在 1-65535 之间")
        return v


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


class AgentCompleteRequest(BaseModel):
    """Web REPL 补全请求：光标所在行的当前输入。"""

    line: str
    cursor: int = 0
    cwd: str = ""


class AgentCompleteResult(BaseModel):
    """补全结果：prefix 是 agent 端解析的被补全 token，candidates 以 prefix 开头。"""

    request_id: str = ""
    prefix: str = ""
    candidates: list[str] = []
    error: str = ""


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


class PendingCommandItem(BaseModel):
    """正在执行或等待执行的命令信息"""

    command_id: str
    command: str = ""
    cwd: str = ""
    timeout: int = 0
    run_id: str = ""
    task_name: str = ""
    started_at: float = 0
    duration_s: float = 0
    status: str = "queued"  # "queued" | "running"

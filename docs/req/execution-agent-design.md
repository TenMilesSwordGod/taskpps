# Execution Agent 设计 — 需求文档

> 版本: v1.1\
> 日期: 2026-06-05\
> 状态: 📝 需求设计

---

## 一、背景与动机

### 1.1 当前问题

当前 Taskpps 通过 `SSHExecutor` 在远程主机上执行命令，实现方式为每次任务执行时通过 Paramiko 建立 SSH 连接，在线程池中同步执行。这种方式存在以下问题：

| 问题 | 说明 | 影响 |
| :--- | :--- | :--- |
| **exit_code=-1 频发** | 进程被信号杀死、SSH 连接中断、`exit_code is None` 等场景均返回 -1，无法区分根因 | 排查困难，日志缺少信号名称 |
| **SSH 连接无超时控制** | `SSHExecutor.execute()` 接收 `timeout` 参数但未使用，远程命令可能无限挂起 | 资源泄漏，流水线卡死 |
| **无进程生命周期管理** | 远程命令通过 `channel.exec_command()` 启动后，若 SSH 连接断开，远程进程变成孤儿进程 | 远程主机资源泄漏 |
| **输出读取不完整** | `select.select` + `exit_status_ready` 的判断逻辑可能在 channel 关闭时丢失尾部数据 | 日志截断 |
| **每次新建连接** | 每个任务都重新建立 SSH 连接，无连接复用/池化 | 延迟高，资源浪费 |
| **粗暴的取消机制** | `cancel()` 直接关闭 channel 和 client，远程进程不会被终止 | 远程孤儿进程 |
| **LocalExecutor 和 SSHExecutor 行为不一致** | timeout/cancel 处理方式完全不同，调试困难 | 用户体验不一致 |

### 1.2 设计目标

引入 **Execution Agent**（执行代理），类比 Jenkins Agent / GitLab Runner，在远程主机上运行一个轻量级 agent 进程，Taskpps Server 通过长连接协议向 agent 下发命令，agent 在本地执行并回传 stdout/stderr/exit_code。

#### 核心目标

1. **可靠的任务执行** — agent 在本地管理子进程生命周期，不会因网络抖动产生孤儿进程
2. **完整的超时/取消支持** — agent 本地对子进程实施 timeout 和 SIGTERM/SIGKILL 升级策略
3. **精确的 exit_code 报告** — agent 直接获取 OS 级 exit_code，可区分正常退出 vs 信号杀死，携带信号名称
4. **实时日志流式回传** — stdout/stderr 逐行实时推送到 Server
5. **自动部署 (bootstrap)** — Server 首次连接 agent 时，可通过 SSH 自动拷贝 agent 二进制到目标主机
6. **向后兼容** — 旧 `SSHExecutor` 标记 `@deprecated`，保留但不再推荐使用

---

## 二、架构设计

### 2.1 整体架构

```
┌─────────────────────┐          WebSocket / TCP         ┌─────────────────────┐
│   Taskpps Server    │ ◄──────────────────────────────► │   Execution Agent   │
│                     │    (长连接，双向消息)                │                     │
│  ┌───────────────┐  │                                  │  ┌───────────────┐  │
│  │ AgentManager  │  │  1. handshake / register         │  │  Agent Core   │  │
│  │ (连接池管理)    │  │  2. exec_command → stdout/stderr │  │  (进程管理)     │  │
│  │               │  │  3. cancel → SIGTERM/SIGKILL      │  │               │  │
│  │ AgentExecutor │  │  4. heartbeat ↔ pong             │  │  LocalExecutor│  │
│  │ (新 Executor)  │  │  5. exit_code + signal_name      │  │  (复用现有)    │  │
│  └───────────────┘  │                                  │  └───────────────┘  │
│                     │                                  │                     │
│  ┌───────────────┐  │        Bootstrap (SSH)           │  ┌───────────────┐  │
│  │ AgentBootstrap│──┼─────────────────────────────────►│  │  agent binary │  │
│  │ (首次部署)     │  │   scp agent → remote /tmp/       │  │  (Go 编译)     │  │
│  └───────────────┘  │   ssh remote "agent --daemon"    │  └───────────────┘  │
└─────────────────────┘                                  └─────────────────────┘
```

### 2.2 组件说明

| 组件 | 位置 | 语言 | 职责 |
| :--- | :--- | :--- | :--- |
| **AgentManager** | Server (Python) | Python | 管理到各 Agent 的 WebSocket 连接池，提供 send/cancel 接口 |
| **AgentExecutor** | Server (Python) | Python | 新的 `BaseExecutor` 子类，替代 `SSHExecutor`，通过 AgentManager 下发命令 |
| **AgentBootstrap** | Server (Python) | Python | 首次连接时通过 SSH 部署 agent 二进制到远程主机 |
| **Execution Agent** | Agent Host (独立进程) | Go | 在远程主机运行，接收命令、管理子进程、回传日志 |
| **Agent CLI** | CLI (Go) | Go | `ppsctl agent deploy/start/stop/status` 管理命令 |

### 2.3 通信协议

采用 **WebSocket**（首选）或 **TCP** 作为传输层，消息格式使用 **JSON**。

#### 消息方向

```
Server → Agent:
  - handshake_request   { agent_id, secret, version }
  - exec_command        { command_id, command, env, cwd, timeout }
  - cancel_command      { command_id }
  - heartbeat_request   { }

Agent → Server:
  - handshake_response  { agent_id, hostname, version, pid }
  - stdout_chunk        { command_id, data }
  - stderr_chunk        { command_id, data }
  - exec_result         { command_id, exit_code, signal_name, duration_ms }
  - heartbeat_response  { }
```

#### 消息结构定义

```python
# Server → Agent

class HandshakeRequest:
    agent_id: str
    secret: str          # 预共享密钥，用于认证
    version: str         # 协议版本

class ExecCommand:
    command_id: str      # UUID，用于关联回传消息
    command: str         # 要执行的 shell 命令
    env: dict[str, str]  # 环境变量
    cwd: str             # 工作目录
    timeout: int | None  # 超时秒数

class CancelCommand:
    command_id: str

# Agent → Server

class HandshakeResponse:
    agent_id: str
    hostname: str
    agent_version: str
    agent_pid: int

class StdoutChunk:
    command_id: str
    data: str            # 增量文本

class StderrChunk:
    command_id: str
    data: str

class ExecResult:
    command_id: str
    exit_code: int       # OS 级 exit_code，-N 表示被信号 N 杀死
    signal_name: str | None  # 如 "SIGKILL", "SIGTERM", None=正常退出
    duration_ms: int
    error: str | None    # agent 侧错误信息（如 timeout）
```

---

## 三、项目结构

### 3.1 新增 `execution_agent/` 目录

在项目根目录下新建 `execution_agent/` 文件夹，与 `cli/` 和 `server/` 平级，使用 Go 语言独立开发。

```
taskpps/
├── cli/                    # Go CLI 工具 (ppsctl)
│   ├── go.mod
│   ├── main.go
│   ├── cmd/
│   ├── client/
│   ├── config/
│   ├── models/
│   └── tui/
├── execution_agent/        # 【新增】Go 执行代理 (taskpps-agent)
│   ├── go.mod              # module github.com/xxx/taskpps/execution_agent
│   ├── go.sum
│   ├── main.go             # 入口，解析 CLI 参数
│   ├── cmd/
│   │   ├── root.go         # 根命令
│   │   ├── run.go          # 启动 agent (前台/daemon)
│   │   ├── stop.go         # 停止 agent
│   │   └── status.go       # 查看 agent 状态
│   ├── agent/
│   │   ├── agent.go        # Agent 核心结构体，生命周期管理
│   │   ├── wsclient.go     # WebSocket 客户端，连接/重连/心跳
│   │   ├── executor.go     # 命令执行：os/exec 子进程管理
│   │   ├── process.go      # 进程树管理：递归 kill
│   │   └── protocol.go     # 消息协议定义 (JSON)
│   ├── config/
│   │   └── config.go       # Agent 配置结构体
│   ├── logger/
│   │   └── logger.go       # 本地日志模块
│   └── build/
│       └── build.sh        # 交叉编译脚本
├── server/                 # Python 后端服务
│   ├── pyproject.toml
│   └── taskpps/
├── examples/
├── docs/
│   └── req/
├── .gitignore
├── AGENTS.md
└── README.md
```

### 3.2 Go Module 与依赖

```go
// execution_agent/go.mod
module github.com/xxx/taskpps/execution_agent

go 1.19

require (
    github.com/gorilla/websocket v1.5.x   // WebSocket 客户端
    github.com/spf13/cobra v1.x           // CLI 框架
    github.com/google/uuid v1.x           // UUID 生成
)
```

### 3.3 编译与分发

```bash
# 本地编译
cd execution_agent
go build -o taskpps-agent .

# 交叉编译 (用于 bootstrap 部署到不同架构)
GOOS=linux   GOARCH=amd64 go build -o build/taskpps-agent-linux-amd64 .
GOOS=linux   GOARCH=arm64 go build -o build/taskpps-agent-linux-arm64 .
GOOS=darwin  GOARCH=amd64 go build -o build/taskpps-agent-darwin-amd64 .
GOOS=darwin  GOARCH=arm64 go build -o build/taskpps-agent-darwin-arm64 .
```

编译产物为单一静态二进制文件，zero-dependency，可直接拷贝到目标主机运行。

---

## 四、Execution Agent 详细设计

### 4.1 Agent 生命周期

```
                   ┌──────────┐
                   │ 部署阶段   │
                   │ (bootstrap)│
                   └────┬─────┘
                        │
                        ▼
                   ┌──────────┐   连接断开/报错
                   │ 运行中    │──── 自动重连 ────┐
                   │ (daemon) │                   │
                   └────┬─────┘                   │
                        │                         │
              ┌─────────┼─────────┐               │
              ▼         ▼         ▼               │
         ┌────────┐ ┌────────┐ ┌────────┐         │
         │ exec   │ │ cancel │ │ heartbeat        │
         │ command│ │ command│ │                  │
         └───┬────┘ └───┬────┘ └────────┘         │
             │          │                          │
             ▼          ▼                          │
         ┌────────────────┐                       │
         │ LocalExecutor  │                       │
         │ (复用现有逻辑)   │                       │
         │ stdout/stderr  │                       │
         │ exit_code      │                       │
         └────────────────┘                       │
                                                  │
         ┌────────────────────────────────────────┘
         │  (重连成功，继续服务)
         ▼
```

### 4.2 Agent 核心功能

Agent 使用 **Go 语言** 编写（与 CLI 技术栈一致），编译为单二进制文件，zero-dependency 部署。

#### 功能列表

| 功能 | 说明 |
| :--- | :--- |
| **WebSocket 客户端** | 主动连接到 Taskpps Server，维持长连接 |
| **TLS 加密** | 支持 TLS/SSL 加密通信 |
| **预共享密钥认证** | handshake 时携带 agent_id + secret 进行身份验证 |
| **命令执行** | 接收 `exec_command`，使用 `os/exec` 在本地 fork 子进程 |
| **实时输出流** | stdout/stderr 逐行/分块回传，不缓存完整输出 |
| **超时控制** | 若 `timeout > 0`，到期后 SIGTERM → 5s → SIGKILL，回传 `signal_name=SIGKILL` |
| **取消控制** | 接收 `cancel_command`，SIGTERM → 5s → SIGKILL |
| **心跳保活** | 定时发送 heartbeat，检测连接状态 |
| **自动重连** | 连接断开后自动重连（指数退避，最大间隔 60s）|
| **信号名称报告** | exit_code 为负数时，回传 `signal_name`（SIGKILL/SIGTERM/SIGSEGV 等）|
| **并发命令支持** | 支持同时执行多个命令（受 agent 配置的 max_parallel 限制）|
| **Daemon 模式** | 支持 `--daemon` 后台运行，`--pid-file` 记录 PID |

### 4.3 Agent 命令行接口

```bash
# 启动 agent（前台）
taskpps-agent --server wss://taskpps.example.com:28765 \
              --agent-id prod-server \
              --secret <pre-shared-key>

# 启动 agent（后台 daemon）
taskpps-agent --server wss://taskpps.example.com:28765 \
              --agent-id prod-server \
              --secret <pre-shared-key> \
              --daemon \
              --pid-file /var/run/taskpps-agent.pid \
              --log-file /var/log/taskpps-agent.log

# 停止 agent
taskpps-agent --stop --pid-file /var/run/taskpps-agent.pid

# 查看 agent 状态
taskpps-agent --status --pid-file /var/run/taskpps-agent.pid
```

### 4.4 Agent 本地子进程管理

Agent 内部复用与 **LocalExecutor** 等价的逻辑：

1. 使用 Go 的 `os/exec` 启动子进程
2. stdout / stderr 通过 pipe 读取，逐行发送到 Server
3. 维护子进程 PID，支持进程树递归 kill（同 Python 版 `_kill_process_tree`）
4. 超时检测使用 `context.WithTimeout` 或 timer goroutine
5. 取消时 SIGTERM → 5s wait → SIGKILL
6. 进程结束后通过 `cmd.ProcessState` 获取 OS 级 exit_code

```go
// Go 侧 exit_code 获取
func (a *Agent) executeCommand(req ExecCommand) {
    cmd := exec.CommandContext(ctx, shell, "-c", req.Command)
    cmd.Env = mergeEnv(req.Env)
    cmd.Dir = req.Cwd

    stdoutPipe, _ := cmd.StdoutPipe()
    stderrPipe, _ := cmd.StderrPipe()

    cmd.Start()

    // 并发读取 stdout/stderr，stream 回 server
    go streamStdout(stdoutPipe, req.CommandID)
    go streamStderr(stderrPipe, req.CommandID)

    cmd.Wait()

    exitCode := cmd.ProcessState.ExitCode()  // -1 表示被信号杀死
    signalName := signalNameFromState(cmd.ProcessState)

    sendExecResult(req.CommandID, exitCode, signalName)
}
```

---

## 五、Server 侧设计

### 5.1 AgentManager

`AgentManager` 是 Server 侧管理所有 Agent WebSocket 连接的中心组件。

```python
class AgentManager:
    """管理到所有 Execution Agent 的 WebSocket 连接池"""

    def __init__(self):
        self._connections: dict[str, AgentConnection] = {}  # agent_id → connection

    async def connect(self, agent_id: str) -> AgentConnection:
        """建立到指定 Agent 的 WebSocket 连接（含自动重连）"""

    async def send_command(self, agent_id: str, command_id: str,
                           command: str, env: dict, cwd: str,
                           timeout: int | None) -> None:
        """向 Agent 发送 exec_command"""

    async def cancel_command(self, agent_id: str, command_id: str) -> None:
        """向 Agent 发送 cancel_command"""

    async def get_result(self, agent_id: str, command_id: str) -> ExecResult:
        """等待并获取命令执行结果"""

    def subscribe_output(self, agent_id: str, command_id: str,
                         on_stdout: Callable, on_stderr: Callable) -> None:
        """订阅命令的实时输出"""

    async def disconnect(self, agent_id: str) -> None:
        """断开指定 Agent 连接"""

    async def disconnect_all(self) -> None:
        """断开所有连接（shutdown 时调用）"""
```

### 5.2 AgentExecutor（新 Executor）

`AgentExecutor` 替代 `SSHExecutor`，实现 `BaseExecutor` 接口。

```python
class AgentExecutor(BaseExecutor):
    """通过 Execution Agent 在远程主机执行命令"""

    def __init__(self, agent_id: str, manager: AgentManager):
        self._agent_id = agent_id
        self._manager = manager
        self._command_id: str | None = None
        self._cancelled = False

    async def execute(
        self,
        command: str,
        env: dict[str, str],
        log_path: Path,
        timeout: int | None = None,
        cwd: str | None = None,
    ) -> ExecutorResult:
        """
        使用 Execution Agent 执行命令：

        1. 生成 command_id (UUID)
        2. 发送 exec_command 到 Agent
        3. 订阅 stdout/stderr 实时写入 log_path
        4. 等待 exec_result（带 timeout 监控）
        5. 若 timeout 触发，发送 cancel_command
        6. 返回 ExecutorResult(exit_code, signal_name, ...)
        """
        ...

    async def cancel(self) -> None:
        """取消当前执行的命令"""
        self._cancelled = True
        if self._command_id:
            await self._manager.cancel_command(self._agent_id, self._command_id)
```

### 5.3 部署策略：自动部署优先（Jenkins 模式）

#### 设计原则

类比 Jenkins 的 Agent 注册方式：Jenkins Master 通过 SSH 连接到 Agent 机器，自动拷贝 `remoting.jar`，启动 agent 进程，agent 自动回连 Master 完成注册。**全程无需人工在 Agent 机器上操作**。

Taskpps 采用相同策略：

| 特性 | Jenkins | Taskpps |
| :--- | :--- | :--- |
| 二进制 | `remoting.jar` | `taskpps-agent`（Go 静态编译） |
| 传输方式 | SSH + SCP | SSH + SFTP/SCP |
| 启动 | `java -jar remoting.jar ...` | `taskpps-agent --daemon ...` |
| 注册 | Agent 主动连接 Master | Agent WebSocket 连接 Server → handshake 自动注册 |
| 凭据 | Master 存储 SSH 凭据 | `agents/*.yaml` → `credential_id` 引用凭据 |

#### 自动部署流程（Server 侧触发）

当 `create_executor()` 发现某个 Agent 尚未连接时，**自动触发 AgentBootstrap**：

```
create_executor(task) 被调用 (task.host = "prod-server")
  │
  ▼
AgentManager.get_connection("prod-server")
  │
  ├── 已连接? ──yes──► 正常使用 AgentExecutor
  │
  └── 未连接
        │
        ▼
      AgentBootstrap.bootstrap("prod-server")  ← 自动触发
        │
        ├── 1. 加载 Agent 配置 (host, port, credential_id)
        ├── 2. 解析 SSH 凭据 (username, password/key)
        ├── 3. SSH 连接到 Agent 机器
        ├── 4. which taskpps-agent → 检查是否已有 agent 二进制
        │     ├── 已有且版本匹配 → 跳到步骤 6
        │     └── 没有/版本不匹配 → 继续
        ├── 5. SFTP 上传 taskpps-agent 二进制 + chmod +x
        ├── 6. SSH 启动 agent daemon
        │     taskpps-agent --server ws://<server>:28765 \
        │                   --agent-id prod-server \
        │                   --secret <agent_secret> \
        │                   --daemon
        └── 7. 等待 agent WebSocket 连接 + handshake
              │
              ├── 成功 → AgentManager 注册连接 → 返回 AgentExecutor
              └── 超时/失败 → 抛出异常，回退 SSHExecutor
```

#### AgentBootstrap 组件

```python
class AgentBootstrap:
    """通过 SSH 自动部署 Execution Agent 到远程主机（Jenkins 模式）"""

    def __init__(self, agent_loader: AgentLoader, credential_loader: CredentialLoader):
        self._agent_loader = agent_loader
        self._credential_loader = credential_loader

    async def bootstrap(self, agent_id: str) -> BootstrapResult:
        """
        自动部署流程（Server 内部自动触发）：

        1. 从 AgentLoader 获取 agent 配置 (host, port, credential_id, agent_secret, ...)
        2. 从 CredentialLoader 解析 SSH 凭据
        3. 通过 SSH 检查远程主机架构 (uname -m)
        4. 检查是否已有正确版本的 agent 二进制
        5. 若无，通过 SFTP 上传对应架构的 taskpps-agent 二进制
        6. 通过 SSH 启动 agent daemon
        7. 等待 agent WebSocket 连接 + handshake 完成注册
        8. 返回 BootstrapResult(success=True, agent_pid=xxx)
        """

    async def _ssh_exec(self, agent_id: str, command: str, timeout: int = 30) -> tuple[int, str, str]:
        """通过 SSH 在 Agent 主机执行命令，返回 (exit_code, stdout, stderr)"""

    async def _sftp_upload(self, agent_id: str, local_path: str, remote_path: str) -> None:
        """通过 SFTP 上传文件到 Agent 主机"""

    async def check_agent_status(self, agent_id: str) -> AgentBootstrapStatus:
        """
        检查 Agent 主机当前状态，返回：
        - not_installed: 未安装 agent 二进制
        - installed_outdated: 已安装但版本过旧
        - installed_ready: 已安装且版本匹配
        - agent_running: agent 进程正在运行
        """

    async def install_or_upgrade(self, agent_id: str) -> None:
        """安装或升级 agent 二进制"""

    async def start_agent_daemon(self, agent_id: str) -> int:
        """在远程主机启动 agent daemon，返回远程 PID"""

    async def wait_for_handshake(self, agent_id: str, timeout: float = 30.0) -> bool:
        """等待 agent WebSocket 连接并完成 handshake，返回是否成功"""
```

#### 自动部署时序图

```
Server (Python)                            Agent Host (Linux/amd64)
  │                                              │
  │  [create_executor 发现 agent 未连接]           │
  │                                              │
  │──── paramiko SSH connect ──────────────────► │
  │       (使用 credential 中的 username/password) │
  │                                              │
  │──── uname -m ────────────────────────────►  │
  │ ◄── x86_64 ──────────────────────────────────│
  │                                              │
  │──── which taskpps-agent ─────────────────►  │
  │ ◄── not found ──────────────────────────────│
  │                                              │
  │──── SFTP: upload build/taskpps-agent-       │
  │       linux-amd64 → /usr/local/bin/    ──►  │
  │       taskpps-agent                          │
  │                                              │
  │──── chmod 755 /usr/local/bin/taskpps-agent ─►│
  │                                              │
  │──── taskpps-agent --daemon               ──► │ agent 进程启动
  │       --server ws://10.0.0.1:28765            │ (后台 daemon)
  │       --agent-id prod-server                 │
  │       --secret xxxxxxxx                      │
  │       --pid-file /var/run/taskpps-agent.pid  │
  │                                              │
  │ ◄── WebSocket connect ws://10.0.0.1:28765 ───│ agent 主动连接
  │──── handshake {agent_id, secret} ────────►  │
  │ ◄── handshake_response {hostname, pid} ─────│
  │                                              │
  │  ✅ 注册完成，连接就绪，返回 AgentExecutor      │
```

#### 降级与回退策略

```
自动部署流程
  │
  ├── agent_auto_bootstrap: false ──► 跳过，使用 SSHExecutor
  │
  ├── SSH 连接失败 ──► WARN 日志 + 回退 SSHExecutor
  │
  ├── SFTP 上传失败 ──► ERROR 日志 + 提示使用 ppsctl agent deploy 手动部署
  │
  ├── Agent 启动失败 ──► ERROR 日志 + 回退 SSHExecutor
  │
  └── Handshake 超时 ──► ERROR 日志 + 回退 SSHExecutor
```

#### 手动部署（CLI 兜底）

当自动部署不可用时（如 Agent 机器无 SSH、特殊网络环境等），提供 CLI 手动部署：

```bash
# 由运维人员在能访问 Agent 机器的地方执行
ppsctl agent deploy prod-server

# 该命令内部流程：
# 1. 从 Server API 获取 agent 配置 (server地址、secret 等)
# 2. 从 Server 下载对应架构的 taskpps-agent 二进制
# 3. 通过 SCP/手动方式拷贝到目标机器
# 4. SSH 启动 agent daemon
```

### 5.4 Executor 工厂变更

`create_executor()` 增加 Agent 优先逻辑（自动 Bootstrap 集成）：

```python
def create_executor(task: ResolvedTask) -> BaseExecutor:
    # ... 省略 invoke/git/nexus 逻辑 ...

    if task.host:
        agent = AgentLoader().get(task.host)
        if agent is None:
            raise AgentNotFoundError(task.host)

        # 优先使用 Execution Agent
        if agent.get("execution_agent", True):  # 新字段，默认启用
            manager = get_agent_manager()

            # 检查 Agent 连接状态
            if not manager.is_connected(task.host):
                # 自动 Bootstrap：SSH 部署 + 启动 agent
                if agent.get("agent_auto_bootstrap", True):
                    bootstrap = get_agent_bootstrap()
                    try:
                        result = await bootstrap.bootstrap(task.host)
                        if not result.success:
                            raise AgentBootstrapError(f"Agent '{task.host}' bootstrap failed: {result.error}")
                    except AgentBootstrapError as e:
                        logger.error("自动部署 Agent '%s' 失败: %s，回退 SSHExecutor", task.host, e)
                        return SSHExecutor(...)
                else:
                    logger.warning("Agent '%s' 未连接且未启用自动部署，回退使用 SSHExecutor (@deprecated)", task.host)
                    return SSHExecutor(...)

            return AgentExecutor(agent_id=task.host, manager=manager)
        else:
            # 回退到旧 SSHExecutor（@deprecated）
            logger.warning("Agent '%s' 未启用 Execution Agent，回退使用 SSHExecutor (@deprecated)", task.host)
            return SSHExecutor(...)

    return LocalExecutor()
```

### 5.5 新的 Agent YAML 配置字段

```yaml
# agents/prod.yaml
agents:
  - id: prod-server
    name: "生产环境服务器"
    type: ssh-username-password
    host: 10.0.0.50
    port: 22
    credential_id: prod-cred
    max_parallel: 3

    # === 新增字段 ===
    execution_agent: true                # 是否启用 Execution Agent（默认 true）
    server_ws_port: 28765                # Server WebSocket 端口（Agent 连接此端口）
    agent_port: 26065                    # Agent 本地监听端口（健康检查/状态查询）
    agent_secret: ${credential:agent-secret.token}  # 预共享密钥（可从凭据引用）
    agent_version: "1.0.0"               # 期望的 Agent 版本
    agent_auto_bootstrap: true           # 是否自动部署 Agent（默认 true，类 Jenkins）
    agent_binary_path: /usr/local/bin/taskpps-agent  # Agent 二进制在远程主机的安装路径
    agent_work_dir: /opt/taskpps-agent   # Agent 工作目录（远程）
    agent_log_dir: /var/log/taskpps      # Agent 日志目录（远程）
    agent_pid_file: /var/run/taskpps-agent.pid  # Agent PID 文件路径（远程）
```

### 5.6 日志增强

在 `_execute_subpipeline` 中，当 `exit_code < 0` 时增加信号名称：

```python
# runner.py — _execute_subpipeline
if exit_code < 0:
    signal_num = -exit_code
    signal_names = {1: "SIGHUP", 2: "SIGINT", 9: "SIGKILL", 15: "SIGTERM", ...}
    sig_name = signal_names.get(signal_num, f"signal {signal_num}")
    detail = f"({sig_name})" if signal_num != 1 else "(sentinel -1 from executor)"
    self._write_pipeline_log(
        "FAILED",
        f"Task '{qualified_name}' failed with exit code: {exit_code} "
        f"(process was killed by signal or did not start properly) {detail}",
    )
```

同时，`AgentExecutor` 回传的 `signal_name` 也输出到 pipeline 日志中：

```python
if result.signal_name:
    self._write_pipeline_log(
        "FAILED",
        f"Task '{qualified_name}' failed with exit code: {result.exit_code} "
        f"(signal: {signal_name})",
    )
```

---

## 六、CLI 扩展

### 6.1 部署模式总览

| 模式 | 触发方式 | 适用场景 | 人工操作 |
| :--- | :--- | :--- | :--- |
| **自动部署** (推荐) | Server 首次使用 Agent 时自动触发 | 正常场景：Agent 机器可通过 SSH 访问 | 零人工操作 |
| **CLI 手动部署** (兜底) | `ppsctl agent deploy <id>` | SSH 不可用、需手动拷贝二进制 | 运维执行一条命令 |
| **手动安装** (极端) | 手动 SCP + 手动启动 | 完全隔离网络 | 全手动 |

### 6.2 新增命令

```bash
# === Agent 部署（兜底命令） ===
ppsctl agent deploy <agent-id>        # 手动部署 agent 到指定主机
                                      # 内部：从 Server 获取配置 → 下载二进制 → SCP → 启动

# === Agent 生命周期管理 ===
ppsctl agent start <agent-id>         # 启动已部署但未运行的 agent
ppsctl agent stop <agent-id>          # 停止 agent daemon
ppsctl agent restart <agent-id>       # 重启 agent

# === Agent 状态查看 ===
ppsctl agent status [agent-id]        # 查看 agent 运行状态（含连接状态、运行中的命令）
ppsctl agent logs <agent-id>          # 拉取并查看 agent 本地日志
ppsctl agent list                     # 列出所有 agent 及连接状态

# === Agent 二进制 ===
ppsctl agent build                    # 编译 agent 二进制（多架构交叉编译）
ppsctl agent version                  # 查看 agent 版本

# === 现有命令（增强） ===
ppsctl agent try-connect <agent-id>   # 测试连通性（增加 --agent 标志测试 agent 连接）
ppsctl agent check [agent-id]         # 检查 agent 状态（增加 agent 连接状态列）
```

### 6.3 `ppsctl agent status` 输出示例

```
───── Agent Status ─────
  Agent ID:       prod-server
  Host:           10.0.0.50:26065
  Connection:     ✓ connected (ws)
  Agent PID:      12345 (remote)
  Agent Version:  1.0.0
  Uptime:         2h 15m
  Running Tasks:  1/3
    └─ c022b832...  echo "building..."  (running 45s)
  Last Error:     —
```

### 6.4 `ppsctl agent list` 输出示例

```
───── Agents ─────
  AGENT ID        HOST              STATUS       UPTIME    TASKS
  prod-server     10.0.0.50:26065    ✓ connected   2h 15m   1/3
  staging-node    192.168.1.100:26065 ✓ connected   5d 3h    0/5
  dev-worker-01   10.0.1.20:26065    ✗ offline     —         —
  dev-worker-02   10.0.1.21:26065    ⚡ deploying  —         —

Total: 4 agents — 2 connected, 1 offline, 1 deploying
```

---

## 七、Server 配置

### 7.1 新增配置项

```yaml
# taskpps.yaml 或环境变量
server:
  agent:
    enabled: true                  # 是否启用 Execution Agent 功能
    ws_host: "0.0.0.0"            # WebSocket 监听地址
    ws_port: 28765                 # WebSocket 监听端口
    ws_tls: false                 # 是否启用 TLS
    ws_cert_file: ""              # TLS 证书路径
    ws_key_file: ""               # TLS 私钥路径
    heartbeat_interval: 15        # 心跳间隔（秒）
    heartbeat_timeout: 45         # 心跳超时（秒），超过此时间未收到心跳则断开
    reconnect_max_interval: 60    # Agent 重连最大间隔（秒）
    bootstrap_timeout: 30         # Bootstrap 超时（秒）
```

### 7.2 Settings 类扩展

```python
class AgentConfig(BaseModel):
    enabled: bool = True
    ws_host: str = "0.0.0.0"
    ws_port: int = 28765
    ws_tls: bool = False
    ws_cert_file: str = ""
    ws_key_file: str = ""
    heartbeat_interval: int = 15
    heartbeat_timeout: int = 45
    reconnect_max_interval: int = 60
    bootstrap_timeout: int = 30
```

---

## 八、安全性设计

| 方面 | 设计 |
| :--- | :--- |
| **认证** | 预共享密钥 (PSK)：Agent 在 handshake 时携带 `agent_id` + `secret`，Server 验证 |
| **密钥管理** | `agent_secret` 通过 `${credential:xxx.token}` 引用，不直接写在 agent YAML 中 |
| **传输加密** | 支持 TLS WebSocket (`wss://`)，生产环境推荐启用 |
| **最小权限** | Agent 以受限用户身份运行，工作目录隔离 |
| **危险命令防护** | 复用 `LocalExecutor` 的 `_DANGEROUS_PATTERNS` 检测逻辑，在 Agent 侧执行前拦截 |
| **命令隔离** | 每个命令在独立子进程中执行，环境变量隔离 |

---

## 九、兼容性与迁移

### 9.1 SSHExecutor 弃用策略

| 阶段 | 内容 |
| :--- | :--- |
| **Phase 1** | `SSHExecutor` 代码保留，添加 `@deprecated` 标记和警告日志 |
| **Phase 2** | 所有新 Agent 配置默认 `execution_agent: true`，使用 AgentExecutor |
| **Phase 3** | `execution_agent: false` 的回退路径保留，用于不支持 agent 的旧环境 |
| **Phase 4** | 观察期后移除 `SSHExecutor` 核心代码（保留 git history） |

### 9.2 Agent YAML 向后兼容

- 旧 Agent 配置不包含 `execution_agent` 字段 → 默认行为取决于 Server 配置
- 若 Server 启用了 Agent 功能 (默认) → 自动尝试 Bootstrap + AgentExecutor
- 若 Bootstrap 失败 → 回退到 `SSHExecutor`，打印警告日志

### 9.3 Pipeline YAML 无需变更

`task.host` 字段仍然引用 `agent_id`，不需要任何 pipeline YAML 改动。Executor 的选择在 `create_executor()` 内部完成。

---

## 十、实现计划

| 阶段 | 内容 | 预估工作量 | 依赖 |
| :--- | :--- | :--- | :--- |
| **Phase 1** | Agent 二进制：Go 实现 WebSocket client、命令执行、进程管理、心跳 | 大 | 无 |
| **Phase 2** | Server WebSocket：Agent WebSocket server、handshake、消息路由 | 中 | Phase 1 |
| **Phase 3** | AgentManager：连接池、send/cancel/get_result、重连 | 中 | Phase 2 |
| **Phase 4** | AgentExecutor：新 Executor 实现、集成到 create_executor | 中 | Phase 3 |
| **Phase 5** | AgentBootstrap：SSH 自动部署、启动 agent | 中 | Phase 1, 4 |
| **Phase 6** | CLI 扩展：`ppsctl agent deploy/start/stop/status` | 小 | Phase 5 |
| **Phase 7** | 日志增强：signal_name 输出、AgentExecutor 日志 | 小 | Phase 4 |
| **Phase 8** | SSHExecutor 标记 @deprecated | 小 | Phase 4 |
| **Phase 9** | 全面测试：单元测试 + 集成测试 + E2E | 大 | Phase 1-8 |

---

## 十一、风险与注意事项

1. **Bootstrap 依赖 SSH** — 首次部署仍需 SSH 连通性。如果 SSH 不可用，需手动部署 agent 二进制。
2. **Agent 二进制跨平台编译** — 需要为不同架构（amd64/arm64）和 OS（linux/darwin）编译 agent 二进制。
3. **WebSocket 防火墙** — 企业网络可能限制 WebSocket 非标准端口（28765），需支持 443 端口复用或配置自定义端口。
4. **Agent 升级** — 需要 Agent 版本协商与自动升级机制（Phase 2+）。
5. **Server 重启** — Agent 需支持 Server 重启后的自动重连，当前执行中的命令不应丢失。

---

## 十二、讨论要点（待决策）

| # | 决策点 | 选项 A | 选项 B | 建议 |
| :--- | :--- | :--- | :--- | :--- |
| 1 | Agent 实现语言 | Go（与 CLI 一致） | Rust（性能更优） | **A ✅ 已确认** — 新建 `execution_agent/` 文件夹，Go 独立开发 |
| 2 | 通信协议 | WebSocket | gRPC (HTTP/2) | **A** — 更简单，浏览器可直接调试 |
| 3 | 首次部署方式 | Server 自动 Bootstrap | 用户 CLI 手动触发 | **A ✅ 已确认** — Server 自动触发，CLI `deploy` 兜底，类 Jenkins 体验 |
| 4 | Server WebSocket 默认端口 | 28765 | 443 (wss 复用) | **A** — 非特权端口，避免冲突 |
| 5 | 单 Agent 多命令并发 | 支持（goroutine） | 串行执行 | **A** — 性能更好，按 max_parallel 限制 |
| 6 | Agent 日志本地存储 | 仅本地文件 | 本地 + 推送 Server | **A** — 减少网络开销，需要时 `ppsctl agent logs` 拉取 |

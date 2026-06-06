# 生产部署

Taskpps 提供一键部署脚本，可以快速在生产环境中部署服务。

## 快速部署

```bash
# 使用 sudo 运行部署脚本
sudo ./scripts/deploy.sh
```

部署脚本会提示选择项目工作目录，然后自动完成以下工作：

1. 安装系统依赖（Python 3、curl、rsync）
2. 创建系统用户 `taskpps`（无登录权限）
3. 复制服务器代码到 `/opt/taskpps`
4. 在项目工作目录创建 pipelines/agents/credentials 等目录结构
5. 使用 pip 安装 Python 依赖
6. 生成 Systemd 服务文件
7. 生成服务端和项目配置文件
8. 生成 `/etc/profile.d/taskpps.sh` 环境变量配置
9. 安装 `ppsctl` 到 `/usr/local/bin/`
10. 启动服务

## 工作目录选择

部署时可以选择项目工作目录（pipelines/agents/credentials 存放位置）：

```bash
# 交互式选择
sudo ./scripts/deploy.sh

# 非交互模式（CI/CD 友好）
sudo ./scripts/deploy.sh install --workdir /home/admin/projects/taskpps
```

选项：
- **默认模式** (`/opt/taskpps`)：服务器代码与项目文件在同一目录
- **当前目录**：使用 git clone 目录作为项目工作目录
- **自定义路径**：指定任意路径作为项目工作目录

## 部署脚本命令

| 命令 | 说明 |
|:--|:--|
| `sudo ./scripts/deploy.sh install` | 完整部署（默认） |
| `sudo ./scripts/deploy.sh install --workdir <path>` | 指定工作目录部署 |
| `sudo ./scripts/deploy.sh uninstall` | 移除 Systemd 服务和 ppsctl |
| `sudo ./scripts/deploy.sh status` | 查看服务状态 |
| `sudo ./scripts/deploy.sh restart` | 重启服务 |
| `sudo ./scripts/deploy.sh logs` | 查看服务日志 |
| `sudo ./scripts/deploy.sh stop` | 停止服务 |
| `sudo ./scripts/deploy.sh start` | 启动服务 |

## 目录结构

### 传统模式（workdir = /opt/taskpps）

```
/opt/taskpps/                 # 服务端 + 项目文件
├── server/                   # Python 服务端代码
├── cli/                      # CLI 源码
├── execution_agent/          # 执行代理
├── pipelines/                # 流水线定义
├── agents/                   # Agent 配置
├── credentials/              # 凭据配置
├── tasks/                    # Invoke 任务
├── plugins/                  # 自定义插件
├── .taskpps/                 # 服务端数据
│   ├── state.db              # 数据库
│   ├── logs/                 # 运行日志
│   └── workspaces/           # 工作空间
└── taskpps.yaml              # 服务端配置
```

### 分离模式（workdir ≠ /opt/taskpps）

```
/opt/taskpps/                         # 服务端安装目录
├── server/                           # Python 服务端代码
├── cli/                              # CLI 源码
├── execution_agent/                  # 执行代理
├── scripts/                          # 部署脚本
├── .taskpps/                         # 服务端数据
│   ├── state.db                      # 数据库
│   └── taskpps.yaml                  # 服务端配置
└── taskpps.yaml                      # 兼容旧格式

/home/admin/projects/taskpps/         # 项目工作目录
├── pipelines/                        # 流水线定义
├── agents/                           # Agent 配置
├── credentials/                      # 凭据配置
├── tasks/                            # Invoke 任务
├── plugins/                          # 自定义插件
├── .taskpps/                         # 项目数据
│   ├── taskpps.yaml                  # 项目配置（含 workdir）
│   ├── logs/                         # 运行日志
│   └── workspaces/                   # 工作空间
└── taskpps.yaml                      # 兼容旧格式
```

### 系统目录

```
/var/lib/taskpps/                     # 用户数据目录
/var/log/taskpps/                     # 系统日志（access.log/error.log）
/etc/systemd/system/taskpps.service   # Systemd 服务
/etc/profile.d/taskpps.sh             # 环境变量配置
/usr/local/bin/ppsctl                 # ppsctl 全局命令
```

## 环境变量

部署后，`/etc/profile.d/taskpps.sh` 自动设置：

```bash
export TASKPPS_WORKDIR=/home/admin/projects/taskpps
```

用户登录后自动生效，`ppsctl` 在任意目录都能找到项目工作目录。

### 手动设置

```bash
export TASKPPS_WORKDIR=/home/admin/projects/taskpps
ppsctl run my-pipeline
```

### 多项目切换

```bash
# 切换到项目 A
export TASKPPS_WORKDIR=/home/admin/project-a
ppsctl agent list

# 切换到项目 B
export TASKPPS_WORKDIR=/home/admin/project-b
ppsctl pipeline list

# 或使用 --project 参数
ppsctl --project /home/admin/project-b run deploy
```

## 工作目录发现优先级

`ppsctl` 按以下优先级确定项目工作目录：

1. `--project` / `-p` 命令行参数（最高优先级）
2. `TASKPPS_WORKDIR` 环境变量
3. 配置文件 `.taskpps/taskpps.yaml` 中的 `workdir` 字段
4. 无配置时报错，提示设置 `TASKPPS_WORKDIR` 或使用 `--project`

## Systemd 服务管理

```bash
# 查看服务状态
systemctl status taskpps

# 启动/停止/重启服务
systemctl start taskpps
systemctl stop taskpps
systemctl restart taskpps

# 查看服务日志
journalctl -u taskpps -f

# 启用/禁用开机自启
systemctl enable taskpps
systemctl disable taskpps
```

## 其他脚本

| 脚本 | 说明 |
|:--|:--|
| `scripts/update.sh` | 更新服务器代码和依赖 |
| `scripts/backup.sh` | 备份数据库、配置和项目文件 |
| `scripts/healthcheck.sh` | 健康检查 |

## 安全加固

Systemd 服务配置包含以下安全措施：

- **NoNewPrivileges** - 禁止获取新权限
- **ProtectSystem** - 只读挂载系统目录
- **ProtectHome** - 禁止访问用户家目录
- **PrivateTmp** - 私有临时目录
- **MemoryDenyWriteExecute** - 禁止 W+X 内存映射
- **RestrictNamespaces** - 限制命名空间
- **LockPersonality** - 锁定系统调用个性

## 资源限制

- **文件描述符**: 65536
- **进程数**: 4096
- **超时**: 30 秒（优雅关闭）
- **重启策略**: 失败后 5 秒重启，最多 3 次/60 秒

## 配置文件

### 服务端配置 (`/opt/taskpps/taskpps.yaml`)

```yaml
locale: zh
server:
  host: 0.0.0.0
  port: 26521
  api_key: "<随机生成>"
executor:
  default_timeout: 3600
  max_workers: 10
  shell: /bin/bash
plugins:
  paths: ["plugins"]
triggers: []
env: {}
```

### 项目配置 (`<workdir>/.taskpps/taskpps.yaml`)

```yaml
locale: zh
workdir: /home/admin/projects/taskpps
server:
  host: 127.0.0.1
  port: 26521
executor:
  default_timeout: 3600
  max_workers: 10
  shell: /bin/bash
env: {}
plugins:
  paths: ["plugins"]
triggers: []
```

## 日志目录结构

```
.taskpps/logs/
└── pipeline-name/
    └── run-id/
        └── task-id/
            └── output.log
```
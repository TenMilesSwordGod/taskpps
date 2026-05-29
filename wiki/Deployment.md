# 生产部署

Taskpps 提供一键部署脚本，可以快速在生产环境中部署服务。

## 快速部署

```bash
# 使用 sudo 运行部署脚本
sudo ./scripts/deploy.sh
```

部署脚本会自动完成以下工作：

1. 安装系统依赖（Python 3、curl、rsync）
2. 创建系统用户 `taskpps`（无登录权限）
3. 安装 uv 包管理器（如果未安装）
4. 复制项目文件到 `/opt/taskpps`
5. 使用 uv 安装 Python 依赖
6. 生成 Systemd 服务文件
7. 生成配置文件（包含随机 API Key）
8. 启动服务

## 部署脚本命令

| 命令 | 说明 |
|:--|:--|
| `sudo ./scripts/deploy.sh install` | 完整部署（默认） |
| `sudo ./scripts/deploy.sh uninstall` | 移除 Systemd 服务 |
| `sudo ./scripts/deploy.sh status` | 查看服务状态 |
| `sudo ./scripts/deploy.sh restart` | 重启服务 |
| `sudo ./scripts/deploy.sh logs` | 查看服务日志 |
| `sudo ./scripts/deploy.sh stop` | 停止服务 |
| `sudo ./scripts/deploy.sh start` | 启动服务 |

## 目录结构

部署后的目录结构：

```
/opt/taskpps/                 # 项目代码
/var/lib/taskpps/             # 数据目录（数据库、状态）
/var/log/taskpps/             # 日志目录
/etc/systemd/system/taskpps.service  # Systemd 服务
```

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

项目还提供以下辅助脚本：

| 脚本 | 说明 |
|:--|:--|
| `scripts/update.sh` | 更新代码和依赖 |
| `scripts/backup.sh` | 备份数据 |
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

部署时会生成 `/opt/taskpps/taskpps.yaml`，包含：
- 随机生成的 API Key
- 监听地址和端口
- 执行器配置
- 插件路径
- 触发器配置

## 日志目录结构

```
.taskpps/logs/
└── pipeline-name/
    └── run-id/
        └── task-id/
            └── output.log
```

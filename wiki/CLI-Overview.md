# CLI 概述

`ppsctl` 是 Taskpps 的命令行工具,使用 Go 编写,提供完整的流水线管理功能。

## 安装

```bash
cd cli
go build -o bin/ppsctl main.go

# 可选:移动到 PATH
sudo mv bin/ppsctl /usr/local/bin/
```

## 初始化项目

```bash
ppsctl init
```

在空白目录中执行,创建以下结构:

```
my-project/
├── .taskpps/
│   └── taskpps.yaml    # 全局配置
├── pipelines/           # 流水线 YAML 定义
├── tasks/               # Python invoke 任务函数
├── agents/              # SSH 主机配置
├── credentials/         # SSH 凭据
└── plugins/             # 自定义插件
```

## 服务管理

```bash
# 启动后端服务(自动检测后端进程)
ppsctl start-server

# 查看服务状态和信息
ppsctl server-info
```

## 基本工作流

```bash
# 1. 编写流水线(在 pipelines/ 目录下创建 YAML)
# 2. 运行
ppsctl run deploy.yaml

# 3. 查看运行列表
ppsctl list

# 4. 查看详情
ppsctl status <run-id>

# 5. 查看日志
ppsctl logs <run-id>

# 6. 检查 Agent 连通性
ppsctl agent check

# 7. TUI 实时监控
ppsctl watch
```

## 配置

CLI 连接后端默认地址 `127.0.0.1:26521`。可通过环境变量或配置文件修改。

详见 `cli/docs/config.md`。

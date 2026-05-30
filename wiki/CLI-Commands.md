# 命令参考

所有命令支持 `-h` / `--help` 查看详细参数。

## 全局标志

| 标志 | 默认值 | 说明 |
|:--|:--|:--|
| `--server` | `http://127.0.0.1:26521` | 后端服务地址 |
| `--api-key` | — | API 密钥(如服务端启用了认证) |

## 命令列表

### `init` — 初始化项目

```bash
ppsctl init
```

在当前目录创建 `.taskpps/` 及运行时目录结构。

### `run` — 运行流水线

```bash
ppsctl run <pipeline-file> [key=value ...]

# 示例
ppsctl run deploy.yaml
ppsctl run deploy.yaml TAG=latest
ppsctl run nightly.yaml TAG=stable HOST=prod
```

参数 `key=value` 会作为 `params` 传递给流水线,支持点路径覆盖。

### `list` — 列出运行记录

```bash
ppsctl list [flags]

# 示例
ppsctl list                          # 最近 20 条
ppsctl list --pipeline deploy        # 按流水线名过滤
ppsctl list --status failed          # 按状态过滤
ppsctl list --limit 50               # 限制返回条数
```

### `status` — 查看运行详情

```bash
ppsctl status <run-id>
```

显示运行状态、所有任务状态、执行时间等。

### `logs` — 查看日志

```bash
ppsctl logs <run-id> [flags]

# 示例
ppsctl logs <run-id>                 # 全部日志
ppsctl logs <run-id> --tail 100      # 仅最后 100 行
ppsctl logs <run-id> --task migrate  # 按任务名过滤
ppsctl logs <run-id> --follow        # 实时跟踪(类似 tail -f)
```

`--follow` 基于 SSE 实现实时日志流。

### `watch` — TUI 实时监控

```bash
ppsctl watch
```

启动终端交互界面,实时展示运行列表和任务状态。详见 `cli/docs/tui.md`。

### `cancel` — 取消运行

```bash
ppsctl cancel <run-id>
```

取消正在执行的流水线。已完成任务不受影响,未开始任务被标记为 `cancelled`。

### `agent` — Agent 连通性检查

```bash
ppsctl agent <subcommand> [flags]
```

| 子命令 | 说明 |
|:--|:--|
| `try-connect <id>` | 测试单个 Agent 的 TCP 连通性 |
| `check [id]` | 检查 Agent 连接状态,流式实时输出,按文件分组 |

**`agent try-connect`**

```bash
ppsctl agent try-connect prod-server
ppsctl agent try-connect prod-server --timeout 10
```

快速验证单个 Agent 网络可达性。成功退出码 0,失败退出码 1。

**`agent check`**

```bash
ppsctl agent check                     # 并发检查所有 Agent,流式输出
ppsctl agent check prod-server         # 检查指定 Agent
ppsctl agent check --file staging      # 按文件名过滤(不含扩展名)
ppsctl agent check -t 3                # 自定义超时 3 秒
```

所有 Agent 并发检查,每个完成立即推送结果(基于 SSE 流)。最后显示按 Agent 文件分组的汇总表。

如果服务端不支持流式端点,自动降级到批量模式。

**输出示例:**

```
[1] ✓ unknown (127.0.0.1:22) — ready in 0ms
[2] ✓ test-agent01 (10.98.72.23:22) — connected in 1ms
[3] ✗ test-agent02 (10.98.72.24:22) — failed
: [Errno 113] No route to host

───── agents/local.yaml ─────
   AGENT     HOST:PORT            TYPE          STATUS    LATENCY
  unknown   127.0.0.1:22          unknown        ✓ ready   0ms

───── agents/ssh.yaml ─────
     AGENT         HOST:PORT             TYPE            STATUS      LATENCY
  test-agent01   10.98.72.23:22   ssh-username-pa...   ✓ connected   1ms
  test-agent02   10.98.72.24:22   ssh-username-pa...   ✗ failed      3070ms

Total: 3 agents — 2 connected, 1 failed
```

### `clean` — 清理历史

```bash
ppsctl clean [flags]

# 示例
ppsctl clean --keep 10               # 保留最近 10 条
ppsctl clean --older-than 7d         # 删除 7 天前的记录
ppsctl clean --force-all             # 清理全部
```

### `trigger` — 管理触发器

```bash
ppsctl trigger list                  # 查看所有触发器
ppsctl trigger add cron --schedule "0 2 * * *" --pipeline nightly.yaml
ppsctl trigger delete <trigger-id>
```

### `start-server` — 启动后端

```bash
ppsctl start-server
```

自动启动 Python 后端服务(需要 `uv` 在 PATH 中)。

### `server-info` — 服务信息

```bash
ppsctl server-info
```

显示后端版本、运行状态、配置路径等。

### `version` — 版本信息

```bash
ppsctl version
```

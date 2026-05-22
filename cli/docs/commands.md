# 命令参考

所有命令支持 `-h` / `--help` 查看详细参数。

## 全局标志

| 标志 | 默认值 | 说明 |
|:--|:--|:--|
| `--server` | `http://127.0.0.1:26521` | 后端服务地址 |
| `--api-key` | — | API 密钥（如服务端启用了认证） |

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

参数 `key=value` 会作为 `params` 传递给流水线，支持点路径覆盖。

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
ppsctl logs <run-id> --follow        # 实时跟踪（类似 tail -f）
```

`--follow` 基于 SSE 实现实时日志流。

### `watch` — TUI 实时监控

```bash
ppsctl watch
```

启动终端交互界面，实时展示运行列表和任务状态。详见 `cli/docs/tui.md`。

### `cancel` — 取消运行

```bash
ppsctl cancel <run-id>
```

取消正在执行的流水线。已完成任务不受影响，未开始任务被标记为 `cancelled`。

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

自动启动 Python 后端服务（需要 `uv` 在 PATH 中）。

### `server-info` — 服务信息

```bash
ppsctl server-info
```

显示后端版本、运行状态、配置路径等。

### `version` — 版本信息

```bash
ppsctl version
```

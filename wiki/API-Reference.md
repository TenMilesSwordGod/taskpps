# API 参考

后端默认监听 `127.0.0.1:26521`。所有 API 路径以 `/api` 为前缀。

## 端点总览

| 方法 | 端点 | 功能 |
|:--|:--|:--|
| GET | `/api/health` | 健康检查 |
| POST | `/api/runs/` | 创建流水线运行 |
| GET | `/api/runs/` | 运行列表查询 |
| GET | `/api/runs/{run_id}` | 运行详情 |
| GET | `/api/runs/{run_id}/logs` | 日志查询(支持 SSE) |
| POST | `/api/runs/{run_id}/cancel` | 取消运行 |
| DELETE | `/api/runs/` | 清理历史运行 |
| POST | `/api/plugins/triggers/` | 注册触发器 |
| GET | `/api/plugins/triggers/` | 触发器列表 |
| DELETE | `/api/plugins/triggers/{id}` | 删除触发器 |
| POST | `/api/agents/try-connect` | 测试单个 Agent 连通性 |
| POST | `/api/agents/check` | 批量检查 Agent 连接状态 |
| POST | `/api/agents/check-stream` | 流式并发检查 Agent (SSE) |

## 详细说明

### 创建运行

```http
POST /api/runs/
Content-Type: application/json

{
  "pipeline": "deploy.yaml",
  "params": {
    "options.host": "prod-server"
  }
}
```

响应包含 `run_id`,可用于后续查询日志和状态。

### 查询列表

```http
GET /api/runs/?pipeline=deploy&status=failed&limit=10
```

返回 `{"items": [...], "total": N}` 格式。

### 运行详情

```http
GET /api/runs/{run_id}
```

返回运行状态、所有任务状态、参数快照等。

### 日志查询

```http
GET /api/runs/{run_id}/logs?tail=100&task=migrate
```

支持 SSE(Server-Sent Events)流式传输,适用于实时日志查看。可选 `tail`(返回最后 N 行)和 `task`(按任务名过滤)。

### 取消运行

```http
POST /api/runs/{run_id}/cancel
```

取消正在运行的流水线,已执行完成的任务不受影响。

### 清理历史

```http
DELETE /api/runs/?keep=10
DELETE /api/runs/?older_than_days=7
DELETE /api/runs/?force_all=true
```

支持三种清理策略:保留最近 N 条、删除超过 N 天的记录、强制清理全部。

## API 认证

可选,在 `taskpps.yaml` 中配置 `api_key` 后启用。认证方式为请求头 `X-API-Key`。健康检查和 OPTIONS 请求免认证。

## Agent 连通性检查

### 测试单个 Agent

```http
POST /api/agents/try-connect
Content-Type: application/json

{
  "agent_id": "prod-server",
  "timeout": 5
}
```

响应:

```json
{
  "agent_id": "prod-server",
  "name": "生产环境服务器",
  "type": "ssh-key",
  "host": "10.0.0.50",
  "port": 22,
  "source_file": "agents/prod.yaml",
  "status": "connected",
  "latency_ms": 120,
  "error": null
}
```

### 批量检查

```http
POST /api/agents/check
Content-Type: application/json

{
  "agent_id": null,
  "file_filter": "prod",
  "timeout": 5
}
```

返回 `{"results": [...], "summary": {"total": N, "connected": N, "failed": N}}`。

### 流式并发检查 (SSE)

```http
POST /api/agents/check-stream
Content-Type: application/json

{
  "timeout": 5
}
```

所有 Agent 并发检查,每个完成立即通过 SSE 推送结果。Content-Type: `text/event-stream`。

每个 agent 结果作为一个 SSE event 发送:

```
data: {"agent_id":"agent-a","status":"connected",...}

data: {"agent_id":"agent-b","status":"failed",...}

data: summary:{"total":2,"connected":1,"failed":1}
```

最后一条 event 以 `summary:` 前缀发送汇总信息。

## 日志与事件

运行日志以文件形式存储在 `.taskpps/logs/` 目录,格式为 `{run_id}.log`。通过 SSE 端点可实现前端实时日志流展示。

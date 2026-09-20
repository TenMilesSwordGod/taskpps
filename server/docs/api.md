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
| GET | `/api/pipelines/` | 流水线列表（`items` + `folders`，含空文件夹） |
| POST | `/api/pipelines/by-file/{project_id}` | 新建流水线 YAML（重名 409） |
| PATCH | `/api/pipelines/by-file/{project_id}` | 重命名/移动流水线文件 |
| DELETE | `/api/pipelines/by-file/{project_id}?file=` | 删除流水线（保留运行历史） |
| POST | `/api/pipelines/folders/{project_id}` | 新建流水线文件夹 |
| PATCH | `/api/pipelines/folders/{project_id}` | 重命名/移动文件夹 |
| DELETE | `/api/pipelines/folders/{project_id}?folder=&recursive=` | 删除文件夹（非空需 `recursive=true`） |
| POST | `/api/projects/` | 注册项目目录（服务端绝对路径） |

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

## 流水线与项目管理

流水线以 YAML 文件存放在 `<项目目录>/pipelines/` 下，支持多级子目录（文件夹）。
写操作（POST/PATCH/DELETE）需要 JWT；GET 游客可读。

### 列表

```http
GET /api/pipelines/?project_id=<project_id>
```

响应：`{"items": [...], "folders": [{"project_id", "project_name", "folder"}]}`。
`folders` 为目录扫描结果，用于展示暂无 YAML 的空文件夹。

### 新建流水线

```http
POST /api/pipelines/by-file/{project_id}
Content-Type: application/json

{
  "file": "deploy/prod.yaml",
  "content": "name: prod\ntasks:\n  - name: hello\n    command: echo hi\n"
}
```

`file` 为相对 `pipelines/` 的路径，必须以 `.yaml`/`.yml` 结尾；文件已存在返回 409。
返回 `{"status": "ok", "file": "...", "definition_id": "<uuid 或 null>"}`。

### 重命名 / 删除流水线

```http
PATCH /api/pipelines/by-file/{project_id}

{ "file": "deploy/prod.yaml", "new_file": "deploy/release.yaml" }
```

重命名只改文件路径，`definition_id` 不变，运行历史不丢失。
删除：`DELETE /api/pipelines/by-file/{project_id}?file=<相对路径>`，定义软删除（`active=false`）。

### 文件夹管理

```http
POST /api/pipelines/folders/{project_id}

{ "folder": "deploy/prod" }
```

重命名：`PATCH /api/pipelines/folders/{project_id}`，请求体 `{"folder": "...", "new_folder": "..."}`。
删除：`DELETE /api/pipelines/folders/{project_id}?folder=deploy&recursive=true`，
非空文件夹必须显式传 `recursive=true`，否则返回 409。

### 注册项目目录

```http
POST /api/projects/

{ "workdir": "/home/user/projects/my-app", "name": "my-app" }
```

`workdir` 必须是 server 所在机器上已存在的绝对目录，否则返回 400；
注册成功后自动创建 `<workdir>/pipelines/`。同一 workdir 重复注册返回 409。

## API 认证

写操作（POST/PUT/PATCH/DELETE）通过 JWT 鉴权，请求头 `Authorization: Bearer <token>`。
GET/HEAD/OPTIONS 游客可读。登录/注册接口见 `/api/v1/auth/login`、`/api/v1/auth/register`。

## 日志与事件

运行日志以文件形式存储在 `.taskpps/logs/` 目录,格式为 `{run_id}.log`。通过 SSE 端点可实现前端实时日志流展示。

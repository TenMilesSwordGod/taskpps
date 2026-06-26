# taskpps Official Plugins

官方插件目录，Server 启动时自动扫描并加载此目录下的 Go 编译 binary。

## 目录结构

```
official_plugins/
  <plugin_name>/
    go.mod              # Go module（独立模块）
    go.sum
    cmd/
      <plugin_name>/    # 入口
        main.go
    Makefile            # build / clean / test
    <plugin_name>       # go build 产物（gitignore 忽略）
```

## 插件类型

V1 仅支持 **ExecutorPlugin**——作为 task 类型在 pipeline YAML 中直接使用。

## 通信协议

Plugin binary 通过 stdin/stdout JSON-RPC 2.0 与 Server 通信。

### methods

| Method | 方向 | 说明 |
|--------|------|------|
| `describe` | Server→Plugin | 返回插件元数据（name/type/version/help_msg/params_schema），加载时调用一次 |
| `execute` | Server→Plugin | 执行任务，params 对应用户在 YAML 中填的参数 |
| `on_shutdown` | Server→Plugin | 关闭插件 |

### describe 响应

```json
{
  "name": "git_plugin",
  "type": "executor",
  "version": "1.0.0",
  "help_msg": "在 pipeline 中使用:\n  GitPlugin:\n    remote: ...\n    branch: main\n    action: checkout",
  "params_schema": {
    "remote": {"type":"string","required":true,"label":"远程仓库地址"},
    "branch": {"type":"string","required":true,"label":"分支名"},
    "action": {"type":"string","required":true,"label":"操作","enum":["checkout","clone","pull"]}
  }
}
```

### execute 响应

```json
{
  "exit_code": 0,
  "stdout": "Cloning into 'repo'... done",
  "stderr": "",
  "duration": 3.42
}
```

### 安全验证

Server 启动插件时设置 `TASKPPS_VERIFY_KEY` 环境变量。插件必须在 describe 响应中回传此 key。

```
Server                          Plugin
  │                                │
  │── spawn(env=VERIFY_KEY) ──────→│
  │── describe ───────────────────→│
  │←─ {"verify_key":"...", ...} ───│  ← key 必须匹配
  │                                │
  │── execute(params) ────────────→│
  │←─ {exit_code:0, ...} ──────────│
```

超时规则:
- describe: 5s 内必须响应，否则 kill
- execute: 300s 内必须响应，否则 kill

## 示例

| 插件 | 目录 | 说明 |
|------|------|------|
| echo | `echo/` | 最小 ExecutorPlugin，回显 message |
| hello | `hello/` | ExecutorPlugin，演示 execute + delay + 参数校验 |

## 开发新插件

1. 复制 `echo/` 或 `hello/` 目录
2. 修改 `go.mod` 中的 module 名
3. 修改 `describe` 返回值（name/help_msg/params_schema）
4. 实现 `execute` handler
5. `make build` 编译
6. 复制 binary 到目标项目的 `official_plugins/` 或 `plugins/` 下

## convention

- binary 名 = 目录名 = describe.name = YAML 中 task 类型名
- stderr 用于插件日志（不影响 JSON-RPC 通信）
- stdout 仅输出 JSON-RPC 响应（一行一条）
- help_msg 必须包含在 pipeline YAML 中的使用示例
- params_schema 中 required=true 的字段缺失时返回 JSON-RPC error

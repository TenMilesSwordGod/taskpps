# 执行器

三种执行器通过 `create_executor(task, context)` 工厂函数创建。

## Local 执行器

在本地运行 Shell 命令，基于 `asyncio.create_subprocess_exec`：

```yaml
# pipeline.yaml 中默认使用 local
tasks:
  - name: build
    command: make build
```

### 配置

在 `.taskpps/taskpps.yaml` 中：

```yaml
executor:
  shell: /bin/bash        # 默认 shell，可选 /bin/zsh /bin/sh 等
  default_timeout: 3600   # 默认超时（秒）
  max_workers: 10         # 最大并发任务数
```

### 安全机制

检测并阻止以下危险命令模式：
- 递归删除根目录：`rm -rf /` / `rm -rf /*`
- Fork 炸弹：`:(){ :|:& };:`
- 直接写入块设备：`dd if=/dev/zero of=/dev/sda` / `> /dev/sda` / `mkfs.*` / `format`
- 破坏性权限变更：`chmod -R 777 /` / `chmod 000 /`

## SSH 执行器

通过 paramiko 在远程主机执行命令：

```yaml
tasks:
  - name: deploy
    command: systemctl restart myapp
    host: prod-server
```

### 主机配置（Agent）

在 `agents/` 目录下创建 YAML 文件：

```yaml
# agents/prod.yaml
host: 192.168.1.100
port: 22
username: deploy
credential: prod-cred     # 引用凭据名称
```

### 凭据配置（Credential）

在 `credentials/` 目录下创建 YAML 文件：

```yaml
# credentials/prod-cred.yaml
# 方式一：密钥文件
key_file: ~/.ssh/id_rsa
passphrase: ""

# 方式二：密码
password: "your-password"
```

## Invoke 执行器

动态导入 `tasks/` 目录下的 Python 模块，调用指定函数：

```yaml
tasks:
  - name: migrate
    invoke:
      task: deploy_tasks.migrate_db
      args: ["--verbose"]
      kwargs:
        target_version: "3.0"
```

任务函数示例（`tasks/deploy_tasks.py`）：

```python
from taskpps.executors.invoke import invoke_task

@invoke_task
def migrate_db(target_version: str, verbose: bool = False):
    print(f"Migrating to {target_version}")
```

支持 `@invoke_task` 装饰器标记的函数和普通函数。函数参数通过 `args` 和 `kwargs` 传递。

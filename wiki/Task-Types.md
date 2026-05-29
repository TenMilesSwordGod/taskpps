# 任务类型

Taskpps 支持三种任务类型,通过工厂函数 `create_executor()` 统一创建。

## Command 任务

在本地或远程执行 Shell 命令:

```yaml
tasks:
  - name: build
    command: make build

  - name: deploy-remote
    command: systemctl restart myapp
    host: prod-server          # 指定远程主机(需配置 agent)

  - name: with-shell
    command: echo "hello" && ls -la
```

### 安全机制

`LocalExecutor` 内置危险命令检测,匹配以下模式将拒绝执行:
- `rm -rf /` / `rm -rf /*`
- `:(){ :|:& };:`(fork 炸弹)
- `dd if=/dev/zero of=/dev/sda`
- `mkfs.*` / `format` / `fdisk`
- `> /dev/sda` / 直接写入块设备
- `chmod -R 777 /` / `chmod 000 /`

## Invoke 任务

调用 Python 函数,支持参数传递。任务文件放置在 `tasks/` 目录。

```yaml
tasks:
  - name: migrate
    invoke:
      task: deploy_tasks.migrate_db
      args: ["--verbose"]
      kwargs:
        target_version: "3.0"
```

Python 任务函数示例(`tasks/deploy_tasks.py`):

```python
# 使用 @invoke_task 装饰器(推荐)
from taskpps.executors.invoke import invoke_task

@invoke_task
def migrate_db(target_version: str, verbose: bool = False):
    print(f"Migrating to {target_version}")
    # ... 业务逻辑

# 普通函数也可直接调用
def hello(name: str):
    return f"Hello, {name}"
```

## Steps 任务

将多个子步骤组合为一个逻辑任务:

```yaml
tasks:
  - name: deploy
    steps:
      - command: docker build -t myapp .
      - command: docker push myapp
      - invoke:
          task: deploy_tasks.notify
          kwargs:
            status: "done"
```

Steps 按顺序依次执行,任何一个步骤失败则整个任务失败。

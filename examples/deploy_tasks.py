"""Invoke 任务定义示例

这些函数可以在流水线的 invoke 任务中引用,例如:
  - name: migrate
    invoke:
      task: deploy_tasks.migrate_db
      kwargs:
        target_version: latest

需要在 taskpps.yaml 中配置 tasks 目录,或使用默认的 tasks/ 目录。
"""

from invoke import task


@task
def migrate_db(c, target_version="latest"):
    """执行数据库迁移"""
    print(f"正在迁移数据库到版本: {target_version}")
    c.run(f"python manage.py migrate --version {target_version}")


@task
def health_check(c, url="http://localhost:8000"):
    """健康检查"""
    print(f"正在检查服务健康状态: {url}")
    result = c.run(f"curl -sf {url}/health", warn=True)
    if result.ok:
        print("健康检查通过")
    else:
        print("健康检查失败")
        raise SystemExit(1)

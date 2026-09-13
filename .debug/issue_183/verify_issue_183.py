#!/usr/bin/env python3
"""issue #183 修复验证脚本（当前 main，直接调生产代码真实路径）。

为什么这么写：
- 约束不能写正式 tests/；本脚本自行复刻 server/tests/conftest.py 的最小环境
  （临时项目目录 + sqlite 文件库 + 注册项目/definition），直接用
  PipelineService().create_run(definition_id) 且**不传 project_id** 调用，
  这正是 issue 报告时触发 UnboundLocalError 的请求形态。
- 断言：返回 run id / pipeline_name，且全程无 UnboundLocalError。

用法（在仓库根目录）:
  server/.venv/bin/python .debug/issue_183/verify_issue_183.py
"""

from __future__ import annotations

import asyncio
import shutil
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SERVER_DIR = REPO_ROOT / "server"
# 为什么插入 server：脚本可从任意 cwd 运行，taskpps 包位于 server/ 下
sys.path.insert(0, str(SERVER_DIR))

from sqlalchemy.ext.asyncio import create_async_engine  # noqa: E402
from sqlalchemy.pool import NullPool  # noqa: E402
from sqlmodel import SQLModel  # noqa: E402

import taskpps.config as cfg  # noqa: E402
from taskpps.db.engine import get_session_factory, reset_engine, set_engine  # noqa: E402
from taskpps.db.repository import (  # noqa: E402
    PipelineDefinitionRepository,
    ProjectRepository,
)
from taskpps.services.pipeline_service import PipelineService  # noqa: E402

PIPELINE_YAML = (
    "name: deploy\noptions:\n  env:\n    APP_ENV: staging\ntasks:\n  - name: step1\n    command: echo hello\n"
)


def _make_project_dir(root: Path) -> None:
    """构建最小项目目录（对齐 conftest.tmp_project 的必要子目录/配置）。"""
    for sub in ("pipelines", "agents", "credentials", "tasks", "plugins"):
        (root / sub).mkdir(parents=True)
    (root / "taskpps.yaml").write_text(
        "server:\n  host: 127.0.0.1\n  port: 26521\n"
        "executor:\n  default_timeout: 60\n  max_workers: 4\n"
        "env:\n  GLOBAL_VAR: global_value\n"
        "plugins:\n  paths: ['plugins']\n"
        "triggers: []\n",
        encoding="utf-8",
    )
    (root / "pipelines" / "deploy.yaml").write_text(PIPELINE_YAML, encoding="utf-8")


async def _wait_background_tasks(timeout: float = 10.0) -> None:
    """等待 create_run 拉起的 PipelineRunner 后台任务自然结束。

    为什么需要：若在后台任务仍运行时销毁 DB/临时目录，asyncio.run 关闭阶段会
    抛出与本次验证无关的 "no such table" 噪音，干扰对验证结果的判读。
    """
    current = asyncio.current_task()
    pending = [t for t in asyncio.all_tasks() if t is not current and not t.done()]
    if not pending:
        return
    _, still = await asyncio.wait(pending, timeout=timeout)
    for task in still:
        task.cancel()
    if still:
        await asyncio.gather(*still, return_exceptions=True)


async def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="issue183-verify-"))
    engine = None
    try:
        _make_project_dir(tmp)

        # 对齐 conftest._setup_config/setup_project 的 config 初始化
        cfg.set_project_root(tmp)
        cfg._server_home = tmp
        cfg._project_workdir = tmp
        cfg._settings = None
        cfg.load_settings(str(tmp / "taskpps.yaml"))

        engine = create_async_engine(
            f"sqlite+aiosqlite:///{tmp / 'test.db'}",
            echo=False,
            connect_args={"check_same_thread": False},
            poolclass=NullPool,
        )
        set_engine(engine)
        async with engine.begin() as conn:
            await conn.run_sync(SQLModel.metadata.create_all)

        async with get_session_factory()() as session:
            project = await ProjectRepository(session).create_project(str(tmp), name="test-project")
        async with get_session_factory()() as session:
            definition, _ = await PipelineDefinitionRepository(session).upsert(
                project_id=project.id,
                file_path="deploy.yaml",
                name="deploy",
                content='{"name": "deploy"}',
                raw_content=PIPELINE_YAML,
                file_hash="issue183",
            )

        svc = PipelineService()
        # 关键：不传 project_id（旧版会走 else 分支并触发 UnboundLocalError）
        result = await svc.create_run(definition.id)
        assert "id" in result, f"缺少 run id: {result}"
        assert result["pipeline_name"] == "deploy", f"名称不符: {result}"

        run = await svc.get_run(result["id"])
        assert run is not None, "run 未落库"
        await _wait_background_tasks()
        print(
            "PASS: create_run(definition_id) 不传 project_id 正常返回 "
            f"run_id={result['id']} pipeline_name={result['pipeline_name']}，无 UnboundLocalError"
        )
        return 0
    except UnboundLocalError as e:
        print(f"FAIL: 仍抛 UnboundLocalError: {e}")
        return 1
    except Exception as e:  # 验证脚本需要打印任何失败形态
        print(f"FAIL: {type(e).__name__}: {e}")
        return 1
    finally:
        if engine is not None:
            await engine.dispose()
        reset_engine()
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))

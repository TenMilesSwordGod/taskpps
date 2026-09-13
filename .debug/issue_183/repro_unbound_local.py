#!/usr/bin/env python3
"""issue #183 历史 bug 最小复现脚本（只读，不修改生产代码）。

为什么这么写：
- 用户报告 400: "加载流水线失败:cannot access local variable 'get_pipelines_dir' ..."
- 根因假设：旧版 server/taskpps/services/pipeline_service.py（409f536 及之前）
  的 create_run 中，`from taskpps.config import get_pipelines_dir` 写在
  `if project_id:` 分支内部，属于函数级局部绑定；Python 编译期据此把该名字
  视为整个函数的局部变量。请求不带 project_id 时该 import 不执行，函数内
  无条件调用 get_pipelines_dir() 即抛 UnboundLocalError。
- 为避免"写个等价小函数自说自话"，本脚本分两部分交叉验证：
  Part 1: 等价最小函数，直白展示 Python 作用域规则；
  Part 2: 用 git show 提取 409f536 的真实旧文件，用 AST 抠出真实 create_run，
         注入最小 stub 后走"无 project_id + 项目列表非空"路径，复现真实异常链。

用法（在仓库根目录）:
  server/.venv/bin/python .debug/issue_183/repro_unbound_local.py
"""

from __future__ import annotations

import ast
import asyncio
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
SERVER_DIR = REPO_ROOT / "server"
DEBUG_DIR = Path(__file__).resolve().parent
OLD_FILE = DEBUG_DIR / "old_pipeline_service_409f536.py"
OLD_COMMIT = "409f536"

# 为什么插入 server 目录：脚本可能从任意 cwd 运行，而 taskpps 包位于 server/ 下
sys.path.insert(0, str(SERVER_DIR))

from taskpps.i18n import t  # noqa: E402


def part1_minimal_equivalent() -> bool:
    """等价最小函数：复刻旧 create_run 的局部 import 遮蔽形态。

    这里模块级也定义了一个同名 get_pipelines_dir（等价于旧文件的模块级 import），
    if 分支内又做了一次局部 import，使该名字在整个函数作用域成为局部变量。
    """
    print("[Part 1] 等价最小函数")

    def get_pipelines_dir(workdir: str | None = None) -> str:
        # 模拟旧文件模块级 `from taskpps.config import get_pipelines_dir`
        return f"module-level:{workdir}"

    def old_style_create_run(project_id: str | None):
        # 复刻旧代码: 局部 import 只在 if 分支执行，函数尾仍无条件调用
        if project_id:
            from taskpps.config import get_pipelines_dir

            return get_pipelines_dir(None)
        return get_pipelines_dir(None)

    try:
        old_style_create_run(None)
    except UnboundLocalError as e:
        print(f"  -> UnboundLocalError: {e}")
        return True
    print("  -> 未复现（意外）")
    return False


def _extract_old_create_run() -> str:
    """从 git 提取旧版真实文件，AST 抠出 create_run 源码（不改工作区 HEAD）。"""
    if not OLD_FILE.exists():
        src = subprocess.run(
            ["git", "show", f"{OLD_COMMIT}:server/taskpps/services/pipeline_service.py"],
            cwd=REPO_ROOT,
            check=True,
            capture_output=True,
            text=True,
        ).stdout
        OLD_FILE.write_text(src, encoding="utf-8")
    tree = ast.parse(OLD_FILE.read_text(encoding="utf-8"))
    # 为什么用 ast.walk：create_run 是 PipelineService 类的方法，不在模块顶层
    for node in ast.walk(tree):
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "create_run":
            return ast.unparse(node)
    raise RuntimeError("旧文件中未找到 create_run")


class _FakeProjectRepository:
    """为什么 stub：要触发 for 循环里 get_pipelines_dir(proj.workdir) 那一行，
    必须让 DB 查询返回至少一个项目；这里绕开真实数据库，只验证作用域问题。
    """

    def __init__(self, session):
        pass

    async def list_projects(self):
        return [SimpleNamespace(id="proj-1", workdir="/fake/project/workdir")]


class _FakeSessionCtx:
    async def __aenter__(self):
        return object()

    async def __aexit__(self, *exc):
        return False


def _fake_session_factory():
    # 旧代码写的是 get_session_factory()()（两层调用），故第一层返回可调用对象
    return _FakeSessionCtx


class _StubLoader:
    def load(self, *args, **kwargs):  # pragma: no cover - 正常路径不会走到
        raise AssertionError("不应到达 loader.load")


def part2_real_old_create_run() -> bool:
    """AST/exec 复现 409f536 真实 create_run 的失败路径。"""
    print("[Part 2] 真实旧版 create_run（409f536, AST 提取）")

    import taskpps.config as real_cfg
    import taskpps.db.repository as real_repo_mod

    orig_get_settings = real_cfg.get_settings
    orig_project_repo = real_repo_mod.ProjectRepository
    # 为什么 monkeypatch：旧代码内部 `from taskpps.config import get_settings` /
    # `from taskpps.db.repository import ProjectRepository` 是运行期取值，
    # 替换模块属性即可注入 stub，无需真实 DB/settings。
    real_cfg.get_settings = lambda: SimpleNamespace(env={})
    real_repo_mod.ProjectRepository = _FakeProjectRepository

    ns = {
        "Any": Any,
        "Path": Path,
        "asyncio": asyncio,
        "PipelineLoader": _StubLoader,
        "get_session_factory": _fake_session_factory,
        "t": t,
    }
    try:
        func_src = _extract_old_create_run()
        exec(compile(func_src, f"<create_run@{OLD_COMMIT}>", "exec"), ns)
        svc = SimpleNamespace(loader=_StubLoader())
        try:
            # 关键场景：不传 project_id（params 为空，走 else 分支遍历项目）
            asyncio.run(ns["create_run"](svc, "03-subpipelines.yaml", {}, None))
        except ValueError as e:
            cause = e.__cause__
            print(f"  -> ValueError（生产 API 包装后返回的 400 detail）: {e}")
            print(f"  -> __cause__: {type(cause).__name__}: {cause}")
            ok = isinstance(cause, UnboundLocalError) and "get_pipelines_dir" in str(cause)
            print(f"  -> 根因判定: {'匹配 UnboundLocalError(get_pipelines_dir)' if ok else '不匹配'}")
            return ok
        print("  -> 未复现（意外）")
        return False
    finally:
        real_cfg.get_settings = orig_get_settings
        real_repo_mod.ProjectRepository = orig_project_repo


def main() -> int:
    p1 = part1_minimal_equivalent()
    print()
    p2 = part2_real_old_create_run()
    print()
    if p1 and p2:
        print("REPRO OK: 历史 bug 已在旧版 create_run 上复现，根因 = UnboundLocalError('get_pipelines_dir')")
        return 0
    print("REPRO FAILED: 未能复现")
    return 1


if __name__ == "__main__":
    sys.exit(main())

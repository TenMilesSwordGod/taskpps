#!/usr/bin/env python3
"""issue #183 同类风险静态扫描：函数内局部 import 遮蔽同名外层绑定导致 UnboundLocalError。

为什么这么写：
- 简单"行号先后"启发式会漏掉 409f536 的隐蔽形态：use（第 176 行）在 import（第 160 行）
  之后，但两者位于互斥分支（if project_id / else），import 永不执行仍会触发。
- 故用 AST 记录 import 所在的"容器路径"（函数体 → try.body → if.body ...），
  只有当 import 容器路径是 use 容器路径的前缀（即 use 确实位于 import 所在受控块内）
  且 import 行号 <= use 行号时，才判定为安全。

用法（在仓库根目录）:
  server/.venv/bin/python .debug/issue_183/scan_local_import_shadow.py
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
TARGET_DIR = REPO_ROOT / "server" / "taskpps"
SELF_CHECK_FILE = Path(__file__).resolve().parent / "old_pipeline_service_409f536.py"

# 控制流容器：(AST 节点类型, 需要继续下钻的 body 字段名)
_BODY_FIELDS = {
    "If": ("body", "orelse"),
    "For": ("body", "orelse"),
    "AsyncFor": ("body", "orelse"),
    "While": ("body", "orelse"),
    "With": ("body",),
    "AsyncWith": ("body",),
    "Try": ("body", "handlers", "orelse", "finalbody"),
    "TryStar": ("body", "handlers", "orelse", "finalbody"),
    "Match": ("cases",),
}


def _module_bindings(tree: ast.Module) -> dict[str, tuple[str, int]]:
    """收集模块级绑定：名字 → (绑定种类, 行号)。"""
    out: dict[str, tuple[str, int]] = {}
    for node in tree.body:
        if isinstance(node, ast.Import):
            for a in node.names:
                out[a.asname or a.name.split(".")[0]] = ("import", node.lineno)
        elif isinstance(node, ast.ImportFrom):
            for a in node.names:
                if a.name == "*":
                    continue
                out[a.asname or a.name] = ("import", node.lineno)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            out[node.name] = ("def", node.lineno)
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                for n in ast.walk(target):
                    if isinstance(n, ast.Name):
                        out[n.id] = ("assign", node.lineno)
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            out[node.target.id] = ("assign", node.lineno)
    return out


def _collect_names(expr: ast.AST, containers: tuple, uses: list) -> None:
    for node in ast.walk(expr):
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
            uses.append((node.id, node.lineno, containers))


def _is_stmt_list(value) -> bool:
    return isinstance(value, list) and bool(value) and all(isinstance(x, ast.stmt) for x in value)


def _walk_body(body: list, containers: tuple, imports: list, uses: list, globals_: set) -> None:
    for stmt in body:
        _walk_stmt(stmt, containers, imports, uses, globals_)


def _walk_block_owner(value, containers: tuple, imports: list, uses: list, globals_: set) -> None:
    """处理 handlers/cases 这类非 stmt 的块元素。"""
    for item in value:
        if isinstance(item, ast.ExceptHandler):
            if item.type is not None:
                _collect_names(item.type, containers, uses)
            sub = (*containers, (id(item), "body"))
            _walk_body(item.body, sub, imports, uses, globals_)
        elif isinstance(item, ast.match_case):
            _collect_names(item.pattern, containers, uses)
            if item.guard is not None:
                _collect_names(item.guard, containers, uses)
            _walk_body(item.body, (*containers, (id(item), "body")), imports, uses, globals_)
        elif isinstance(item, list):
            _walk_body(item, containers, imports, uses, globals_)


def _walk_stmt(stmt: ast.stmt, containers: tuple, imports: list, uses: list, globals_: set) -> None:
    if isinstance(stmt, (ast.Import, ast.ImportFrom)):
        imports.append((stmt, containers))
        return
    if isinstance(stmt, ast.Global):
        globals_.update(stmt.names)
        return
    if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
        # 新作用域：其内部 import 不会遮蔽当前函数，跳过
        return
    # 当前语句自身表达式中的使用
    for child in ast.iter_child_nodes(stmt):
        if isinstance(child, ast.expr):
            _collect_names(child, containers, uses)
    # 下钻受控子语句，容器路径追加 (语句, 字段)
    fields = _BODY_FIELDS.get(type(stmt).__name__)
    if fields is None:
        return
    for field in fields:
        value = getattr(stmt, field, None)
        if value is None:
            continue
        sub = (*containers, (id(stmt), field))
        if _is_stmt_list(value):
            _walk_body(value, sub, imports, uses, globals_)
        elif isinstance(value, ast.stmt):
            _walk_stmt(value, sub, imports, uses, globals_)
        elif isinstance(value, list):
            _walk_block_owner(value, sub, imports, uses, globals_)


def _iter_functions(tree: ast.Module):
    """遍历模块内所有函数（含方法、闭包内嵌套函数）。

    为什么下钻函数节点：闭包内同样可能出现"局部 import + 分支外使用"的
    UnboundLocalError；扫描外层时已跳过嵌套函数体，故此处需单独入栈遍历。
    """
    stack = [tree]
    while stack:
        node = stack.pop()
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                yield child
            stack.append(child)


def _scan_file(path: Path) -> list[str]:
    """返回该文件的疑似风险描述列表（每项已含文件:行）。"""
    rel = path.relative_to(REPO_ROOT)
    tree = ast.parse(path.read_text(encoding="utf-8"))
    module_bindings = _module_bindings(tree)
    findings: list[str] = []

    for fn in _iter_functions(tree):
        imports: list = []
        uses: list = []
        globals_: set = set()
        _walk_body(fn.body, (), imports, uses, globals_)

        local_names: dict[str, list] = {}
        for node, containers in imports:
            if isinstance(node, ast.Import):
                names = [(a.asname or a.name.split(".")[0]) for a in node.names]
            else:
                names = [(a.asname or a.name) for a in node.names if a.name != "*"]
            for name in names:
                if name in globals_:
                    continue
                local_names.setdefault(name, []).append((node.lineno, containers))

        for name, binds in local_names.items():
            name_uses = [u for u in uses if u[0] == name]
            risky = []
            for _uname, uline, ucontainers in name_uses:
                safe = False
                for iline, icontainers in binds:
                    if iline > uline:
                        continue
                    if not icontainers or ucontainers[: len(icontainers)] == icontainers:
                        safe = True
                        break
                if not safe:
                    risky.append(uline)
            if not risky:
                continue
            bind_desc = ", ".join(f"L{ln}{'(函数顶层)' if not c else '(条件块内)'}" for ln, c in binds)
            module_desc = ""
            if name in module_bindings:
                kind, mline = module_bindings[name]
                module_desc = f"；模块级同名绑定: {kind} L{mline}"
            findings.append(
                f"{rel}:{risky[0]} 函数 {fn.name}() 内局部 import '{name}'（{bind_desc}）"
                f"{module_desc} → 危险使用行: {sorted(risky)}"
            )
    return findings


def main() -> int:
    # 自检：扫描旧文件必须命中 issue #183 的已知 bug，证明扫描器有效
    print("=== 扫描器自检（对 409f536 旧文件，应命中 get_pipelines_dir）===")
    if SELF_CHECK_FILE.exists():
        self_findings = _scan_file(SELF_CHECK_FILE)
        for f in self_findings:
            print(f"  {f}")
        hit = any("get_pipelines_dir" in f and "create_run" in f for f in self_findings)
        print(f"  自检结果: {'命中已知 bug（扫描器有效）' if hit else '未命中（扫描器可能失效！）'}")
        if not hit:
            return 1
    else:
        print(f"  跳过：{SELF_CHECK_FILE} 不存在")
        return 1

    print()
    print(f"=== 扫描当前生产代码 {TARGET_DIR.relative_to(REPO_ROOT)}/ ===")
    all_findings: list[str] = []
    files = sorted(p for p in TARGET_DIR.rglob("*.py") if "__pycache__" not in p.parts)
    for path in files:
        all_findings.extend(_scan_file(path))

    if all_findings:
        for f in all_findings:
            print(f"[风险] {f}")
    else:
        print("未发现（函数内局部 import 均未被同一函数在 import 生效前的路径上使用）")
    print()
    print(f"共扫描 {len(files)} 个文件，发现 {len(all_findings)} 处疑似风险")
    return 0


if __name__ == "__main__":
    sys.exit(main())

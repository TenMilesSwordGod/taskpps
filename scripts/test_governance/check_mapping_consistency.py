#!/usr/bin/env python3
"""测试用例映射一致性校验工具（issue #223 测试治理）。

用法:
    # Go 端（execution_agent / cli）
    python scripts/test_governance/check_mapping_consistency.py execution_agent \
        --source-root execution_agent
    # server 端
    python scripts/test_governance/check_mapping_consistency.py server \
        --source-root server/tests

校验项:
    1. 失效条目：map key 找不到对应真实测试函数（测试被删除/改名）
    2. 重复 ID：tc_local_id / zentao_id / 重复 test_name（按 (file, test_name) 口径，
       跨文件同名是不同测试，不算重复；同文件同名必须用 file::Class::method 消歧）
    3. 未映射函数：真实存在的测试函数不在 map 中
    4. pending 统计：pending 条目必须 zentao_id=null，active 条目必须已有 zentao_id
    5. key 与 value 的 file/test_name 一致性、total 字段
    6. @pytest.mark.zentao marker 必须与 map 的 tc_local_id 一致（server 端）
    7. TEST_CASE_ACTIVE.json（若存在）必须与 active 映射的 id/file/test_name 同步

退出码: 0=一致; 1=存在不一致; 2=参数或文件错误

设计：解析器按 source 注册在 SOURCE_PARSERS 中；Go 用正则，Python 用 AST
（需提取类方法限定名、async 与参数化装饰器下的 marker）。
"""
from __future__ import annotations

import argparse
import ast
import json
import re
import sys
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

FUNC_RE = re.compile(r"^func (Test\w+)\(t \*testing\.T\)", re.M)


@dataclass(frozen=True)
class TestFunction:
    file: str
    name: str
    line: int
    # server 端才有：@pytest.mark.zentao 的 tc_local_id 与 priority（Go 端为空）
    markers: tuple[str, ...] = ()
    priority: str | None = None


def collect_go_tests(source_root: Path) -> dict[str, TestFunction]:
    """解析 Go 源目录下所有测试函数，key 与 map 一致：<相对文件路径>::<函数名>。"""
    tests: dict[str, TestFunction] = {}
    for path in sorted(source_root.rglob("*_test.go")):
        rel = path.relative_to(source_root).as_posix()
        text = path.read_text(encoding="utf-8")
        for match in FUNC_RE.finditer(text):
            line = text[: match.start()].count("\n") + 1
            key = f"{rel}::{match.group(1)}"
            tests[key] = TestFunction(file=rel, name=match.group(1), line=line)
    return tests


def _extract_zentao_marker(decorator: ast.expr) -> tuple[str, str | None] | None:
    """从 @pytest.mark.zentao("TC-XXXX", priority="P1") 提取 (tc_id, priority)。"""
    if not isinstance(decorator, ast.Call):
        return None
    func = decorator.func
    if not (isinstance(func, ast.Attribute) and func.attr == "zentao"):
        return None
    if not (decorator.args and isinstance(decorator.args[0], ast.Constant)):
        return None
    priority = None
    for kw in decorator.keywords:
        if kw.arg == "priority" and isinstance(kw.value, ast.Constant):
            priority = str(kw.value.value)
    return str(decorator.args[0].value), priority


def collect_pytest_tests(source_root: Path) -> dict[str, TestFunction]:
    """解析 pytest 测试函数，key 规则与 map 约定一致。

    - 文件内唯一方法名：`file.py::test_name`
    - 文件内重名方法（不同类）：`file.py::Class::test_name`（支持嵌套类/函数前缀）
    """
    pytest_root = source_root.resolve()
    raw: list[TestFunction] = []
    for path in sorted(pytest_root.rglob("test_*.py")):
        if "__pycache__" in str(path):
            continue
        rel = path.relative_to(pytest_root).as_posix()
        tree = ast.parse(path.read_text(encoding="utf-8"))

        def walk(node: ast.AST, prefix: list[str], file_rel: str) -> None:
            for child in ast.iter_child_nodes(node):
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    if child.name.startswith("test_"):
                        markers = []
                        priority = None
                        for dec in child.decorator_list:
                            parsed = _extract_zentao_marker(dec)
                            if parsed is not None:
                                markers.append(parsed[0])
                                if parsed[1]:
                                    priority = parsed[1]
                        raw.append(
                            TestFunction(
                                file=file_rel,
                                name="::".join([*prefix, child.name]),
                                line=child.lineno,
                                markers=tuple(markers),
                                priority=priority,
                            )
                        )
                    walk(child, [*prefix, child.name], file_rel)
                elif isinstance(child, ast.ClassDef):
                    walk(child, [*prefix, child.name], file_rel)

        walk(tree, [], rel)

    name_counts: dict[tuple[str, str], int] = defaultdict(int)
    for t in raw:
        name_counts[(t.file, t.name.split("::")[-1])] += 1

    tests: dict[str, TestFunction] = {}
    for t in raw:
        bare = t.name.split("::")[-1]
        key = f"{t.file}::{t.name}" if name_counts[(t.file, bare)] > 1 else f"{t.file}::{bare}"
        tests[key] = t
    return tests


# 解析器注册表：按端扩展时在 SOURCE_PARSERS 中登记 source -> parser key
PARSERS: dict[str, Callable[[Path], dict[str, TestFunction]]] = {
    "go": collect_go_tests,
    "pytest": collect_pytest_tests,
}

SOURCE_PARSERS: dict[str, str] = {
    "execution_agent": "go",
    "cli": "go",
    "server": "pytest",
}


@dataclass
class ConsistencyReport:
    source: str
    map_path: str
    total_declared: int = 0
    entries: int = 0
    active: int = 0
    pending: int = 0
    tests_found: int = 0
    stale: list[str] = field(default_factory=list)
    unmapped: list[str] = field(default_factory=list)
    duplicate_tc_local_ids: dict[str, list[str]] = field(default_factory=dict)
    duplicate_zentao_ids: dict[str, list[str]] = field(default_factory=dict)
    duplicate_test_names: dict[str, list[str]] = field(default_factory=dict)
    key_value_mismatch: list[str] = field(default_factory=list)
    pending_with_zentao_id: list[str] = field(default_factory=list)
    active_without_zentao_id: list[str] = field(default_factory=list)
    marker_mismatch: list[str] = field(default_factory=list)
    total_mismatch: bool = False
    active_file_extra: list[str] = field(default_factory=list)
    active_file_missing: list[str] = field(default_factory=list)
    active_file_field_mismatch: list[str] = field(default_factory=list)
    active_file_checked: bool = False

    @property
    def ok(self) -> bool:
        return not any(
            [
                self.stale,
                self.unmapped,
                self.duplicate_tc_local_ids,
                self.duplicate_zentao_ids,
                self.duplicate_test_names,
                self.key_value_mismatch,
                self.pending_with_zentao_id,
                self.active_without_zentao_id,
                self.marker_mismatch,
                self.total_mismatch,
                self.active_file_extra,
                self.active_file_missing,
                self.active_file_field_mismatch,
            ]
        )

    def format(self) -> str:
        lines = [
            f"== {self.source} 映射一致性报告 ==",
            f"map: {self.map_path}",
            f"声明 total={self.total_declared}, 实际条目={self.entries} "
            f"(active={self.active}, pending={self.pending})",
            f"实际测试函数={self.tests_found}",
        ]

        def section(title: str, items, limit: int = 10):
            status = "OK" if not items else "FAIL"
            lines.append(f"[{status}] {title}: {len(items)}")
            for item in items[:limit]:
                lines.append(f"    - {item}")
            if len(items) > limit:
                lines.append(f"    ... 其余 {len(items) - limit} 项省略")

        section("失效映射(key 无对应测试函数)", self.stale)
        section("未映射测试函数", self.unmapped)
        section("key 与 value.file/test_name 不一致", self.key_value_mismatch)
        section("pending 但 zentao_id 非空", self.pending_with_zentao_id)
        section("active 但 zentao_id 为空", self.active_without_zentao_id)
        section("marker 与 map tc_local_id 不一致", self.marker_mismatch)

        for label, duplicates in (
            ("重复 tc_local_id", self.duplicate_tc_local_ids),
            ("重复 zentao_id", self.duplicate_zentao_ids),
            ("重复 test_name（同 file）", self.duplicate_test_names),
        ):
            status = "OK" if not duplicates else "FAIL"
            lines.append(f"[{status}] {label}: {len(duplicates)}")
            for key, keys in list(duplicates.items())[:10]:
                lines.append(f"    - {key}: {keys}")

        lines.append(f"[{'OK' if not self.total_mismatch else 'FAIL'}] total 字段与实际条目一致")
        if self.active_file_checked:
            section("TEST_CASE_ACTIVE 多出的条目", self.active_file_extra)
            section("TEST_CASE_ACTIVE 缺少的 active 条目", self.active_file_missing)
            section("TEST_CASE_ACTIVE 与 map 的 file/test_name 不一致", self.active_file_field_mismatch)
        else:
            lines.append("[SKIP] TEST_CASE_ACTIVE.json 不存在或未指定")

        lines.append(f"结论: {'一致' if self.ok else '存在不一致'}")
        return "\n".join(lines)


def check_mapping(
    source: str,
    source_root: Path,
    map_path: Path | None = None,
    active_path: Path | None = None,
) -> ConsistencyReport:
    source_root = source_root.resolve()
    map_path = (map_path or source_root / "zentao_testcase_map.json").resolve()

    parser_key = SOURCE_PARSERS.get(source)
    if parser_key is None:
        raise ValueError(f"未知 source: {source}（已注册: {sorted(SOURCE_PARSERS)}）")
    tests = PARSERS[parser_key](source_root)

    data = json.loads(map_path.read_text(encoding="utf-8"))
    mappings = data.get("mappings", {})
    report = ConsistencyReport(source=source, map_path=str(map_path))
    report.total_declared = int(data.get("total", -1))
    report.entries = len(mappings)
    report.tests_found = len(tests)
    report.total_mismatch = report.total_declared != report.entries

    by_tc: dict[str, list[str]] = defaultdict(list)
    by_zentao: dict[str, list[str]] = defaultdict(list)
    by_file_name: dict[tuple[str, str], list[str]] = defaultdict(list)

    for key, meta in mappings.items():
        if key not in tests:
            report.stale.append(key)
            continue

        file_part, _, name_part = key.partition("::")
        if meta.get("file") != file_part or meta.get("test_name") != name_part:
            report.key_value_mismatch.append(
                f"{key} (value.file={meta.get('file')}, value.test_name={meta.get('test_name')})"
            )

        sync_status = meta.get("sync_status", "active")
        if sync_status == "pending":
            report.pending += 1
            if meta.get("zentao_id") is not None:
                report.pending_with_zentao_id.append(key)
        else:
            report.active += 1
            if meta.get("zentao_id") is None:
                report.active_without_zentao_id.append(key)

        by_tc[str(meta.get("tc_local_id"))].append(key)
        if meta.get("zentao_id") is not None:
            by_zentao[str(meta.get("zentao_id"))].append(key)
        by_file_name[(file_part, name_part)].append(key)

        # marker 对齐：测试上声明的每个 zentao marker 都必须等于该条目 tc_local_id
        test = tests[key]
        for marker in test.markers:
            if marker != meta.get("tc_local_id"):
                report.marker_mismatch.append(
                    f"{key} marker={marker} map_tc={meta.get('tc_local_id')}"
                )

    report.unmapped = sorted(set(tests) - set(mappings))
    report.duplicate_tc_local_ids = {k: v for k, v in by_tc.items() if len(v) > 1}
    report.duplicate_zentao_ids = {k: v for k, v in by_zentao.items() if len(v) > 1}
    report.duplicate_test_names = {k: v for k, v in by_file_name.items() if len(v) > 1}

    if active_path is not None and active_path.exists():
        report.active_file_checked = True
        active_data = json.loads(active_path.read_text(encoding="utf-8"))
        active_by_id = {str(item.get("id")): item for item in active_data}
        expected = {
            str(meta.get("tc_local_id")): meta
            for key, meta in mappings.items()
            if meta.get("sync_status", "active") != "pending"
        }
        report.active_file_extra = sorted(set(active_by_id) - set(expected))
        report.active_file_missing = sorted(set(expected) - set(active_by_id))
        for tc_id in sorted(set(active_by_id) & set(expected)):
            item = active_by_id[tc_id]
            meta = expected[tc_id]
            if item.get("file") != meta.get("file") or item.get("test_name") != meta.get("test_name"):
                report.active_file_field_mismatch.append(
                    f"{tc_id} active(file={item.get('file')}, test_name={item.get('test_name')}) "
                    f"map(file={meta.get('file')}, test_name={meta.get('test_name')})"
                )

    return report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="校验测试用例映射与真实测试函数的一致性")
    parser.add_argument("source", help="端标识：server / execution_agent / cli")
    parser.add_argument("--source-root", required=True, help="测试源码根目录")
    parser.add_argument("--map", dest="map_path", help="映射 JSON 路径（默认 <source-root>/zentao_testcase_map.json）")
    parser.add_argument(
        "--active-file",
        dest="active_path",
        help="TEST_CASE_ACTIVE.json 路径（默认 <source-root>/TEST_CASE_ACTIVE.json，不存在则跳过）",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    source_root = Path(args.source_root)
    if not source_root.is_dir():
        print(f"源码目录不存在: {source_root}", file=sys.stderr)
        return 2

    map_path = Path(args.map_path) if args.map_path else source_root / "zentao_testcase_map.json"
    if not map_path.exists():
        print(f"映射文件不存在: {map_path}", file=sys.stderr)
        return 2
    active_path = Path(args.active_path) if args.active_path else source_root / "TEST_CASE_ACTIVE.json"

    try:
        report = check_mapping(args.source, source_root, map_path, active_path)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    print(report.format())
    return 0 if report.ok else 1


if __name__ == "__main__":
    sys.exit(main())

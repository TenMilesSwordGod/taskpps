#!/usr/bin/env python3
"""回填 pending 测试用例映射到禅道（issue #223 测试治理，跨端可复用）。

扫描 map 中 sync_status=pending 的条目，逐个执行：
    zentao testcase create --productID=<id> --title=<title> --pri=<pri> --type=unit --module=0 --format=json
成功后解析返回的用例 id，回写 zentao_id 并置 sync_status=active。

运行期环境变量（本脚本不执行 zentao login，认证交给 CLI 自身）：
    ZENTAO_URL / ZENTAO_CONFIG_FILE   由 zentao CLI 读取
    ZENTAO_PRODUCT_ID                 默认产品 ID，可用 --product-id 覆盖

CLI：
    --map <path>     显式指定映射文件
    --source <end>   server / execution_agent / cli，用各自默认 map 路径

设计：扫描/构造参数/解析输出/回填全部是纯函数，CLI 执行通过 runner 注入，
单测无需真实的 zentao 环境即可覆盖全部逻辑。
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

# Zentao 优先级数字越小越高（1 最高，4 最低），与本地 P0..P3 的对应关系
SOURCE_PRIORITY = {"P0": 1, "P1": 2, "P2": 3, "P3": 4}
DEFAULT_PRIORITY = 3

Runner = Callable[[list[str]], "subprocess.CompletedProcess"]


@dataclass
class BackfillResult:
    created: list[tuple[str, int]] = field(default_factory=list)
    failed: list[tuple[str, str]] = field(default_factory=list)
    planned: list[tuple[str, list[str]]] = field(default_factory=list)


def find_pending(mappings: dict[str, dict]) -> list[str]:
    """返回所有 sync_status=pending 的 key（按 key 排序保证执行顺序稳定）。"""
    return sorted(key for key, meta in mappings.items() if meta.get("sync_status") == "pending")


def priority_to_zentao(priority: str | None) -> int:
    return SOURCE_PRIORITY.get(str(priority or "").upper(), DEFAULT_PRIORITY)


def build_title(meta: dict) -> str:
    """禅道标题带来源与本地编号，回填后仍可反查映射。"""
    return f"[{meta.get('source', 'unknown')}] [{meta.get('tc_local_id')}] {meta.get('test_name')}"


def build_create_args(meta: dict, product_id: int) -> list[str]:
    return [
        "testcase",
        "create",
        f"--productID={product_id}",
        f"--title={build_title(meta)}",
        f"--pri={priority_to_zentao(meta.get('priority'))}",
        "--type=unit",
        "--module=0",
        "--format=json",
    ]


def parse_created_id(stdout: str) -> int | None:
    """解析 zentao CLI 输出中的新用例 id。

    CLI 默认可能输出 JSON 或人类可读文本，因此先按 JSON 解析，
    失败再退化为正则匹配 id 字段/ID: 形式。
    """
    text = (stdout or "").strip()
    if not text:
        return None

    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        payload = None

    if isinstance(payload, dict):
        candidate = payload.get("id")
        if candidate is None and isinstance(payload.get("data"), dict):
            candidate = payload["data"].get("id")
        if candidate is not None:
            try:
                return int(candidate)
            except (TypeError, ValueError):
                return None

    match = re.search(r'"(?:id|ID)"\s*:\s*"?(\d+)"?', text)
    if match is None:
        match = re.search(r"\b(?:ID|id)\s*[:=]\s*(\d+)", text)
    return int(match.group(1)) if match else None


def load_mapping(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def save_mapping(path: Path, data: dict) -> None:
    """先写临时文件再替换，避免中断时把映射文件写成半截 JSON。"""
    tmp_path = path.with_name(path.name + ".tmp")
    tmp_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp_path, path)


def backfill(
    mapping_path: Path,
    product_id: int,
    runner: Runner,
    dry_run: bool = False,
) -> BackfillResult:
    data = load_mapping(mapping_path)
    mappings = data.get("mappings", {})
    result = BackfillResult()

    for key in find_pending(mappings):
        meta = mappings[key]
        args = build_create_args(meta, product_id)
        result.planned.append((key, args))
        if dry_run:
            continue

        proc = runner(args)
        returncode = getattr(proc, "returncode", 1)
        stdout = getattr(proc, "stdout", "") or ""
        stderr = getattr(proc, "stderr", "") or ""
        if returncode != 0:
            result.failed.append((key, stderr.strip() or f"exit code {returncode}"))
            continue

        zentao_id = parse_created_id(stdout)
        if zentao_id is None:
            result.failed.append((key, f"无法从输出解析用例 id: {stdout.strip()[:200]}"))
            continue

        meta["zentao_id"] = zentao_id
        meta["sync_status"] = "active"
        result.created.append((key, zentao_id))

    if not dry_run and result.created:
        save_mapping(mapping_path, data)
    return result


def run_zentao(args: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["zentao", *args],
        capture_output=True,
        text=True,
        env=os.environ,
    )


REPO_ROOT = Path(__file__).resolve().parents[2]

# 各端 map 默认位置：server 在 tests/ 子目录下，Go 端在源码根；映射 key
# 对回填逻辑是 opaque（server 端可能是 file::Class::method），无需解析。
SOURCE_MAP_PATHS = {
    "server": Path("server") / "tests" / "zentao_testcase_map.json",
    "execution_agent": Path("execution_agent") / "zentao_testcase_map.json",
    "cli": Path("cli") / "zentao_testcase_map.json",
}


def resolve_map_path(source: str | None, map_arg: str | None, repo_root: Path = REPO_ROOT) -> Path:
    """把 --source 转成默认 map 路径；显式 --map 优先（保持单测可注入临时目录）。"""
    if map_arg:
        return Path(map_arg)
    if not source:
        raise ValueError("必须提供 --map 或 --source")
    if source not in SOURCE_MAP_PATHS:
        raise ValueError(f"未知 source: {source}（可选: {sorted(SOURCE_MAP_PATHS)}）")
    return (repo_root / SOURCE_MAP_PATHS[source]).resolve()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="将 pending 映射回填到禅道")
    parser.add_argument("--map", help="zentao_testcase_map.json 路径（与 --source 二选一）")
    parser.add_argument("--source", choices=sorted(SOURCE_MAP_PATHS), help="端标识，用默认 map 路径")
    parser.add_argument("--product-id", type=int, default=None, help="产品 ID（默认读取 ZENTAO_PRODUCT_ID）")
    parser.add_argument("--dry-run", action="store_true", help="只打印将要执行的命令，不真正调用 zentao")
    args = parser.parse_args(argv)

    product_id = args.product_id
    if product_id is None:
        try:
            product_id = int(os.environ.get("ZENTAO_PRODUCT_ID", "0") or "0")
        except ValueError:
            product_id = 0
    if product_id <= 0:
        print("缺少产品 ID：请传 --product-id 或设置 ZENTAO_PRODUCT_ID", file=sys.stderr)
        return 2

    try:
        mapping_path = resolve_map_path(args.source, args.map)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    if not mapping_path.exists():
        print(f"映射文件不存在: {mapping_path}", file=sys.stderr)
        return 2

    if not args.dry_run and shutil.which("zentao") is None:
        print("找不到 zentao CLI，请先安装并配置 ZENTAO_URL/ZENTAO_CONFIG_FILE", file=sys.stderr)
        return 2
    if not args.dry_run and not os.environ.get("ZENTAO_URL") and not os.environ.get("ZENTAO_CONFIG_FILE"):
        print("[warn] ZENTAO_URL / ZENTAO_CONFIG_FILE 均未设置，将使用 zentao CLI 默认配置", file=sys.stderr)

    result = backfill(mapping_path, product_id, run_zentao, dry_run=args.dry_run)
    if args.dry_run:
        for key, cmd in result.planned:
            print(f"[dry-run] {key}: zentao {' '.join(cmd)}")
        print(f"[dry-run] 共 {len(result.planned)} 条 pending 待回填")
        return 0

    for key, zentao_id in result.created:
        print(f"[ok] {key} -> zentao_id={zentao_id}")
    for key, reason in result.failed:
        print(f"[fail] {key}: {reason}", file=sys.stderr)
    print(f"完成：成功 {len(result.created)}，失败 {len(result.failed)}")
    return 0 if not result.failed else 1


if __name__ == "__main__":
    sys.exit(main())

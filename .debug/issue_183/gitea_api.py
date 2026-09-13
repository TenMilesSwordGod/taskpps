#!/usr/bin/env python3
"""issue #183 专用 Gitea API helper（一次性脚本）。

为什么这么写：software-team-skill 的 scripts/gitea/*.py 在当前仓库缺失，
故从 SKILL.md 内嵌的 ini 凭据块解析账号，直接调 Gitea REST API。

用法:
  python3 .debug/issue_183/gitea_api.py get-issue 183
  python3 .debug/issue_183/gitea_api.py comment 183 "评论内容" [--role developer]
  python3 .debug/issue_183/gitea_api.py label 183 Priority/High [--role manager]
"""
from __future__ import annotations

import argparse
import base64
import json
import re
import sys
import urllib.error
import urllib.request

SKILL_MD = ".agents/skills/software-team-skill/SKILL.md"


def _parse_ini(block: str) -> dict[str, dict[str, str]]:
    cur, out = None, {}
    for line in block.splitlines():
        line = line.strip()
        if not line or line.startswith(";"):
            continue
        m = re.match(r"\[(\w+)\]", line)
        if m:
            cur = m.group(1)
            out[cur] = {}
            continue
        m = re.match(r"(\w+)\s*=\s*([^;]+)", line)
        if m and cur:
            out[cur][m.group(1).strip()] = m.group(2).strip()
    return out


def load_credentials() -> dict[str, dict[str, str]]:
    src = open(SKILL_MD, encoding="utf-8").read()
    blocks = re.findall(r"```ini\n(.*?)```", src, re.S)
    for block in blocks:
        parsed = _parse_ini(block)
        if "gitea" in parsed:
            return parsed
    raise RuntimeError("SKILL.md 中未找到 gitea 凭据块")


def request(method: str, path: str, role: str = "manager", payload: dict | None = None):
    creds = load_credentials()
    url = creds["gitea"]["host"].rstrip("/")
    repo = creds["gitea"]["repo"]
    account = creds[role]
    token = base64.b64encode(
        f"{account['user']}:{account['password']}".encode()
    ).decode()
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(
        f"{url}/api/v1/repos/{repo}{path}",
        data=data,
        headers={
            "Authorization": f"Basic {token}",
            "Content-Type": "application/json",
        },
        method=method,
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            body = resp.read()
            return resp.status, json.loads(body) if body else {}
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode(errors="replace")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["get-issue", "comment", "label"])
    parser.add_argument("number", type=int)
    parser.add_argument("value", nargs="?", help="评论内容或标签名")
    parser.add_argument("--role", default="manager")
    args = parser.parse_args()

    if args.action == "get-issue":
        status, data = request("GET", f"/issues/{args.number}", args.role)
        print(json.dumps(data, ensure_ascii=False, indent=2))
        return 0 if status == 200 else 3

    if args.action == "comment":
        if not args.value:
            print("缺少评论内容", file=sys.stderr)
            return 1
        status, data = request(
            "POST", f"/issues/{args.number}/comments", args.role, {"body": args.value}
        )
        print(f"comment -> {status}")
        return 0 if status in (200, 201) else 3

    if args.action == "label":
        status, labels = request("GET", "/labels?limit=200", args.role)
        label_id = next(
            (label["id"] for label in labels if label["name"] == args.value), None
        )
        if label_id is None:
            print(f"标签不存在: {args.value}", file=sys.stderr)
            return 2
        status, data = request(
            "POST", f"/issues/{args.number}/labels", args.role, {"labels": [label_id]}
        )
        print(f"label -> {status}")
        return 0 if status in (200, 201) else 3

    return 1


if __name__ == "__main__":
    sys.exit(main())

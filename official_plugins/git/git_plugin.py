#!/usr/bin/env python3
import json
import sys


def main():
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            request = json.loads(line)
        except json.JSONDecodeError:
            continue
        method = request.get("method", "")
        req_id = request.get("id", 1)

        if method == "describe":
            response = {
                "jsonrpc": "2.0",
                "result": {
                    "name": "git_plugin",
                    "type": "executor",
                    "version": "1.0.0",
                    "help_msg": "Git plugin for pipeline tasks",
                    "hooks": [],
                    "params_schema": {
                        "remote": {"type": "string", "required": True, "label": "remote url"},
                        "branch": {"type": "string", "required": True, "label": "branch name"},
                        "action": {"type": "string", "required": True, "label": "action", "enum": ["checkout", "clone", "pull"]},
                    },
                },
                "id": req_id,
            }
            sys.stdout.write(json.dumps(response) + "\n")
            sys.stdout.flush()
        elif method == "execute":
            params = request.get("params", {})
            response = {
                "jsonrpc": "2.0",
                "result": {
                    "success": True,
                    "stdout": f"git {params.get('action', 'clone')} {params.get('remote', '')} (branch={params.get('branch', 'main')})",
                    "stderr": "",
                    "exit_code": 0,
                },
                "id": req_id,
            }
            sys.stdout.write(json.dumps(response) + "\n")
            sys.stdout.flush()
        elif method == "on_shutdown":
            break
    sys.exit(0)


if __name__ == "__main__":
    main()

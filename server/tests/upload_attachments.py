#!/usr/bin/env python3
"""上传文件到 Gitea issue 附件"""
import base64
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request


def upload_attachment(base_url: str, repo: str, issue_number: int, file_path: str, token: str | None = None):
    file_name = os.path.basename(file_path)
    with open(file_path, "rb") as f:
        file_data = f.read()

    api_url = f"{base_url}/api/v1/repos/{repo}/issues/{issue_number}/assets"
    boundary = "----WebKitFormBoundary7MA4YWxkTrZu0gW"
    body = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="file"; filename="{file_name}"\r\n'
        f"Content-Type: application/json\r\n\r\n"
    ).encode("utf-8") + file_data + f"\r\n--{boundary}--\r\n".encode("utf-8")

    req = urllib.request.Request(api_url, data=body, method="POST")
    req.add_header("Content-Type", f"multipart/form-data; boundary={boundary}")

    if token:
        req.add_header("Authorization", f"token {token}")
    else:
        cred_match = __import__("re").match(r"https?://([^:]+):([^@]+)@", base_url)
        if cred_match:
            user = urllib.parse.unquote(cred_match.group(1))
            passwd = urllib.parse.unquote(cred_match.group(2))
            credentials = base64.b64encode(f"{user}:{passwd}".encode()).decode()
            req.add_header("Authorization", f"Basic {credentials}")

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read())
            print(f"  ✓ {file_name} ({len(file_data)} bytes) → {result.get('browser_download_url', 'uploaded')}")
            return result
    except urllib.error.HTTPError as e:
        error_body = e.read().decode("utf-8", errors="replace")
        print(f"  ✗ {file_name}: HTTP {e.code} - {error_body}", file=sys.stderr)
        return None


def main():
    repo_url = "http://10.98.72.23:8418/AM-SYS/taskpps"
    issue_number = 129
    files = sys.argv[1:]

    cred_match = __import__("re").match(r"https?://([^:]+):([^@]+)@", repo_url)
    if cred_match:
        user = urllib.parse.unquote(cred_match.group(1))
        passwd = urllib.parse.unquote(cred_match.group(2))
        host = repo_url.split("@")[1].split("/")[0]
        base_url = f"http://{urllib.parse.quote(user)}:{urllib.parse.quote(passwd)}@{host}"
    else:
        base_url = repo_url

    token = os.environ.get("GITEA_TOKEN")

    for fp in files:
        if os.path.exists(fp):
            upload_attachment(base_url, "AM-SYS/taskpps", issue_number, fp, token)
        else:
            print(f"  ✗ {fp}: 文件不存在", file=sys.stderr)


if __name__ == "__main__":
    main()

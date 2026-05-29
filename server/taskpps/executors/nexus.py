from __future__ import annotations

import asyncio
import base64
import hashlib
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from taskpps.executors.base import BaseExecutor, ExecutorResult
from taskpps.i18n import t


class NexusExecutor(BaseExecutor):
    def __init__(
        self,
        action: str,
        url: str,
        repository: str,
        credential: Optional[str] = None,
        group_id: Optional[str] = None,
        artifact_id: Optional[str] = None,
        version: Optional[str] = None,
        packaging: str = "jar",
        classifier: Optional[str] = None,
        files: Optional[List[str]] = None,
        dest: Optional[str] = None,
        query: Optional[str] = None,
        source_repo: Optional[str] = None,
        target_repo: Optional[str] = None,
    ):
        self.action = action
        self.url = url.rstrip("/")
        self.repository = repository
        self.credential = credential
        self.group_id = group_id
        self.artifact_id = artifact_id
        self.version = version
        self.packaging = packaging
        self.classifier = classifier
        self.files = files or []
        self.dest = dest
        self.query = query
        self.source_repo = source_repo
        self.target_repo = target_repo
        self._cancelled = False

    async def execute(
        self,
        command: str,
        env: Dict[str, str],
        log_path: Path,
        timeout: Optional[int] = None,
        cwd: Optional[str] = None,
    ) -> ExecutorResult:
        self._ensure_log_dir(log_path)
        self._cancelled = False

        merged_env = {**os.environ, **env}

        def _run_nexus():
            try:
                import urllib.request
                import urllib.error
            except ImportError:
                return ExecutorResult(exit_code=1, stderr=t("urllib not available"))

            auth_header = _build_auth_header(self.credential, merged_env)

            if self.action == "upload":
                return _nexus_upload(
                    self.url, self.repository, self.files,
                    self.group_id, self.artifact_id, self.version,
                    self.packaging, self.classifier, auth_header, log_path,
                )
            elif self.action == "download":
                return _nexus_download(
                    self.url, self.repository,
                    self.group_id, self.artifact_id, self.version,
                    self.packaging, self.classifier, self.dest,
                    auth_header, log_path,
                )
            elif self.action == "search":
                return _nexus_search(
                    self.url, self.repository, self.query,
                    auth_header, log_path,
                )
            elif self.action == "delete":
                return _nexus_delete(
                    self.url, self.repository,
                    self.group_id, self.artifact_id, self.version,
                    self.packaging, self.classifier,
                    auth_header, log_path,
                )
            elif self.action == "list":
                return _nexus_list(
                    self.url, self.repository,
                    auth_header, log_path,
                )
            else:
                return ExecutorResult(exit_code=1, stderr=t("Unknown nexus action: {action}", action=self.action))

        try:
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(None, _run_nexus)
            return result
        except asyncio.CancelledError:
            msg = t("Nexus task was cancelled")
            with open(log_path, "a") as f:
                f.write(msg)
            return ExecutorResult(exit_code=-1, stderr=msg)

    async def cancel(self) -> None:
        self._cancelled = True


def _build_auth_header(credential: Optional[str], env: Dict[str, str]) -> Optional[str]:
    username = env.get("NEXUS_USER", "")
    password = env.get("NEXUS_PASS", "")

    if credential:
        username = env.get(f"{credential}_USER", username)
        password = env.get(f"{credential}_PASS", password)

    if username and password:
        credentials = f"{username}:{password}"
        encoded = base64.b64encode(credentials.encode()).decode()
        return f"Basic {encoded}"
    return None


def _build_maven_path(group_id: Optional[str], artifact_id: Optional[str], version: Optional[str],
                      packaging: str, classifier: Optional[str]) -> Optional[str]:
    if not group_id or not artifact_id or not version:
        return None

    group_path = group_id.replace(".", "/")
    base_name = f"{artifact_id}-{version}"
    if classifier:
        file_name = f"{base_name}-{classifier}.{packaging}"
    else:
        file_name = f"{base_name}.{packaging}"

    return f"{group_path}/{artifact_id}/{version}/{file_name}"


def _nexus_upload(
    url: str,
    repository: str,
    files: List[str],
    group_id: Optional[str],
    artifact_id: Optional[str],
    version: Optional[str],
    packaging: str,
    classifier: Optional[str],
    auth_header: Optional[str],
    log_path: Path,
) -> ExecutorResult:
    import urllib.request
    import urllib.error

    if not files:
        return ExecutorResult(exit_code=1, stderr=t("No files specified for upload"))

    results: List[ExecutorResult] = []

    for file_path in files:
        p = Path(file_path)
        if not p.exists():
            msg = t("File not found: {path}", path=file_path)
            with open(log_path, "a") as f:
                f.write(f"{msg}\n")
            results.append(ExecutorResult(exit_code=1, stderr=msg))
            continue

        maven_path = _build_maven_path(group_id, artifact_id, version, packaging, classifier)
        if maven_path:
            nexus_path = maven_path
        else:
            nexus_path = p.name

        nexus_url = f"{url}/repository/{repository}/{nexus_path}"

        with open(log_path, "a") as f:
            f.write(f"+ PUT {nexus_url}\n")

        try:
            with open(p, "rb") as fh:
                data = fh.read()

            req = urllib.request.Request(nexus_url, data=data, method="PUT")
            req.add_header("Content-Type", "application/octet-stream")
            if auth_header:
                req.add_header("Authorization", auth_header)

            with urllib.request.urlopen(req, timeout=300) as resp:
                body = resp.read().decode("utf-8", errors="replace")
                with open(log_path, "a") as f:
                    f.write(f"HTTP {resp.status}: {body[:500]}\n")

                sha256 = hashlib.sha256(data).hexdigest()
                with open(log_path, "a") as f:
                    f.write(f"SHA256: {sha256}\n")

                results.append(ExecutorResult(exit_code=0, stdout=f"Uploaded {file_path} → {nexus_url}"))

        except urllib.error.HTTPError as e:
            error_body = e.read().decode("utf-8", errors="replace") if e.fp else ""
            msg = f"HTTP {e.code}: {error_body[:500]}"
            with open(log_path, "a") as f:
                f.write(f"{msg}\n")
            results.append(ExecutorResult(exit_code=1, stderr=msg))
        except Exception as e:
            msg = str(e)
            with open(log_path, "a") as f:
                f.write(f"{msg}\n")
            results.append(ExecutorResult(exit_code=1, stderr=msg))

    failures = [r for r in results if not r.success]
    if failures:
        return ExecutorResult(
            exit_code=1,
            stdout="\n".join(r.stdout or "" for r in results),
            stderr="\n".join(r.stderr or "" for r in failures),
        )
    return ExecutorResult(exit_code=0, stdout="\n".join(r.stdout or "" for r in results))


def _nexus_download(
    url: str,
    repository: str,
    group_id: Optional[str],
    artifact_id: Optional[str],
    version: Optional[str],
    packaging: str,
    classifier: Optional[str],
    dest: Optional[str],
    auth_header: Optional[str],
    log_path: Path,
) -> ExecutorResult:
    import urllib.request
    import urllib.error

    maven_path = _build_maven_path(group_id, artifact_id, version, packaging, classifier)
    if not maven_path:
        return ExecutorResult(exit_code=1, stderr=t("Maven coordinates required for download"))

    nexus_url = f"{url}/repository/{repository}/{maven_path}"
    dest_dir = Path(dest) if dest else Path.cwd()
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest_file = dest_dir / maven_path.split("/")[-1]

    with open(log_path, "a") as f:
        f.write(f"+ GET {nexus_url}\n")

    try:
        req = urllib.request.Request(nexus_url)
        if auth_header:
            req.add_header("Authorization", auth_header)

        with urllib.request.urlopen(req, timeout=300) as resp:
            data = resp.read()
            with open(dest_file, "wb") as fh:
                fh.write(data)

            sha256 = hashlib.sha256(data).hexdigest()
            with open(log_path, "a") as f:
                f.write(f"Downloaded {len(data)} bytes → {dest_file}\n")
                f.write(f"SHA256: {sha256}\n")

            return ExecutorResult(exit_code=0, stdout=f"Downloaded {nexus_url} → {dest_file}")

    except urllib.error.HTTPError as e:
        error_body = e.read().decode("utf-8", errors="replace") if e.fp else ""
        msg = f"HTTP {e.code}: {error_body[:500]}"
        with open(log_path, "a") as f:
            f.write(f"{msg}\n")
        return ExecutorResult(exit_code=1, stderr=msg)
    except Exception as e:
        msg = str(e)
        with open(log_path, "a") as f:
            f.write(f"{msg}\n")
        return ExecutorResult(exit_code=1, stderr=msg)


def _nexus_search(
    url: str,
    repository: str,
    query: Optional[str],
    auth_header: Optional[str],
    log_path: Path,
) -> ExecutorResult:
    import json
    import urllib.request
    import urllib.error

    search_url = f"{url}/service/rest/v1/search"
    params = f"?repository={repository}"
    if query:
        params += f"&q={urllib.request.quote(query)}"

    full_url = search_url + params

    with open(log_path, "a") as f:
        f.write(f"+ GET {full_url}\n")

    try:
        req = urllib.request.Request(full_url)
        if auth_header:
            req.add_header("Authorization", auth_header)

        with urllib.request.urlopen(req, timeout=60) as resp:
            data = resp.read().decode("utf-8", errors="replace")
            with open(log_path, "a") as f:
                f.write(data[:2000])

            return ExecutorResult(exit_code=0, stdout=data)

    except urllib.error.HTTPError as e:
        error_body = e.read().decode("utf-8", errors="replace") if e.fp else ""
        msg = f"HTTP {e.code}: {error_body[:500]}"
        with open(log_path, "a") as f:
            f.write(f"{msg}\n")
        return ExecutorResult(exit_code=1, stderr=msg)
    except Exception as e:
        msg = str(e)
        with open(log_path, "a") as f:
            f.write(f"{msg}\n")
        return ExecutorResult(exit_code=1, stderr=msg)


def _nexus_delete(
    url: str,
    repository: str,
    group_id: Optional[str],
    artifact_id: Optional[str],
    version: Optional[str],
    packaging: str,
    classifier: Optional[str],
    auth_header: Optional[str],
    log_path: Path,
) -> ExecutorResult:
    import urllib.request
    import urllib.error

    maven_path = _build_maven_path(group_id, artifact_id, version, packaging, classifier)
    if not maven_path:
        return ExecutorResult(exit_code=1, stderr=t("Maven coordinates required for delete"))

    nexus_url = f"{url}/repository/{repository}/{maven_path}"

    with open(log_path, "a") as f:
        f.write(f"+ DELETE {nexus_url}\n")

    try:
        req = urllib.request.Request(nexus_url, method="DELETE")
        if auth_header:
            req.add_header("Authorization", auth_header)

        with urllib.request.urlopen(req, timeout=60) as resp:
            body = resp.read().decode("utf-8", errors="replace")
            with open(log_path, "a") as f:
                f.write(f"HTTP {resp.status}: deleted\n")
            return ExecutorResult(exit_code=0, stdout=f"Deleted {nexus_url}")

    except urllib.error.HTTPError as e:
        error_body = e.read().decode("utf-8", errors="replace") if e.fp else ""
        msg = f"HTTP {e.code}: {error_body[:500]}"
        with open(log_path, "a") as f:
            f.write(f"{msg}\n")
        return ExecutorResult(exit_code=1, stderr=msg)
    except Exception as e:
        msg = str(e)
        with open(log_path, "a") as f:
            f.write(f"{msg}\n")
        return ExecutorResult(exit_code=1, stderr=msg)


def _nexus_list(
    url: str,
    repository: str,
    auth_header: Optional[str],
    log_path: Path,
) -> ExecutorResult:
    import json
    import urllib.request
    import urllib.error

    list_url = f"{url}/service/rest/v1/components?repository={repository}"

    with open(log_path, "a") as f:
        f.write(f"+ GET {list_url}\n")

    try:
        req = urllib.request.Request(list_url)
        if auth_header:
            req.add_header("Authorization", auth_header)

        with urllib.request.urlopen(req, timeout=60) as resp:
            data = resp.read().decode("utf-8", errors="replace")
            with open(log_path, "a") as f:
                f.write(data[:2000])

            return ExecutorResult(exit_code=0, stdout=data)

    except urllib.error.HTTPError as e:
        error_body = e.read().decode("utf-8", errors="replace") if e.fp else ""
        msg = f"HTTP {e.code}: {error_body[:500]}"
        with open(log_path, "a") as f:
            f.write(f"{msg}\n")
        return ExecutorResult(exit_code=1, stderr=msg)
    except Exception as e:
        msg = str(e)
        with open(log_path, "a") as f:
            f.write(f"{msg}\n")
        return ExecutorResult(exit_code=1, stderr=msg)
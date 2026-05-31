from __future__ import annotations

import asyncio
import base64
import hashlib
import os
from pathlib import Path

import httpx

from taskpps.executors.base import BaseExecutor, ExecutorResult
from taskpps.i18n import t


class NexusExecutor(BaseExecutor):
    def __init__(
        self,
        action: str,
        url: str,
        repository: str,
        credential: str | None = None,
        group_id: str | None = None,
        artifact_id: str | None = None,
        version: str | None = None,
        packaging: str = "jar",
        classifier: str | None = None,
        files: list[str] | None = None,
        dest: str | None = None,
        query: str | None = None,
        source_repo: str | None = None,
        target_repo: str | None = None,
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
        env: dict[str, str],
        log_path: Path,
        timeout: int | None = None,
        cwd: str | None = None,
    ) -> ExecutorResult:
        self._ensure_log_dir(log_path)
        self._cancelled = False

        merged_env = {**os.environ, **env}
        auth_header = _build_auth_header(self.credential, merged_env)
        headers = {}
        if auth_header:
            headers["Authorization"] = auth_header

        client_timeout = timeout or 300

        try:
            async with httpx.AsyncClient(timeout=client_timeout) as client:
                if self.action == "upload":
                    return await _nexus_upload(
                        client,
                        self.url,
                        self.repository,
                        self.files,
                        self.group_id,
                        self.artifact_id,
                        self.version,
                        self.packaging,
                        self.classifier,
                        headers,
                        log_path,
                    )
                elif self.action == "download":
                    return await _nexus_download(
                        client,
                        self.url,
                        self.repository,
                        self.group_id,
                        self.artifact_id,
                        self.version,
                        self.packaging,
                        self.classifier,
                        self.dest,
                        headers,
                        log_path,
                    )
                elif self.action == "search":
                    return await _nexus_search(client, self.url, self.repository, self.query, headers, log_path)
                elif self.action == "delete":
                    return await _nexus_delete(
                        client,
                        self.url,
                        self.repository,
                        self.group_id,
                        self.artifact_id,
                        self.version,
                        self.packaging,
                        self.classifier,
                        headers,
                        log_path,
                    )
                elif self.action == "list":
                    return await _nexus_list(client, self.url, self.repository, headers, log_path)
                else:
                    return ExecutorResult(exit_code=1, stderr=t("Unknown nexus action: {action}", action=self.action))
        except asyncio.CancelledError:
            msg = t("Nexus task was cancelled")
            with open(log_path, "a") as f:
                f.write(msg)
            return ExecutorResult(exit_code=-1, stderr=msg)

    async def cancel(self) -> None:
        self._cancelled = True


def _build_auth_header(credential: str | None, env: dict[str, str]) -> str | None:
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


def _build_maven_path(
    group_id: str | None, artifact_id: str | None, version: str | None, packaging: str, classifier: str | None
) -> str | None:
    if not group_id or not artifact_id or not version:
        return None

    group_path = group_id.replace(".", "/")
    base_name = f"{artifact_id}-{version}"
    file_name = f"{base_name}-{classifier}.{packaging}" if classifier else f"{base_name}.{packaging}"

    return f"{group_path}/{artifact_id}/{version}/{file_name}"


async def _nexus_upload(
    client: httpx.AsyncClient,
    url: str,
    repository: str,
    files: list[str],
    group_id: str | None,
    artifact_id: str | None,
    version: str | None,
    packaging: str,
    classifier: str | None,
    headers: dict[str, str],
    log_path: Path,
) -> ExecutorResult:
    if not files:
        return ExecutorResult(exit_code=1, stderr=t("No files specified for upload"))

    results: list[ExecutorResult] = []

    for file_path in files:
        p = Path(file_path)
        if not p.exists():
            msg = t("File not found: {path}", path=file_path)
            with open(log_path, "a") as f:
                f.write(f"{msg}\n")
            results.append(ExecutorResult(exit_code=1, stderr=msg))
            continue

        maven_path = _build_maven_path(group_id, artifact_id, version, packaging, classifier)
        nexus_path = maven_path or p.name

        nexus_url = f"{url}/repository/{repository}/{nexus_path}"

        with open(log_path, "a") as f:
            f.write(f"+ PUT {nexus_url}\n")

        try:
            data = p.read_bytes()
            resp = await client.put(
                nexus_url, content=data, headers={**headers, "Content-Type": "application/octet-stream"}
            )
            body = resp.text

            with open(log_path, "a") as f:
                f.write(f"HTTP {resp.status_code}: {body[:500]}\n")

            sha256 = hashlib.sha256(data).hexdigest()
            with open(log_path, "a") as f:
                f.write(f"SHA256: {sha256}\n")

            if resp.is_success:
                results.append(ExecutorResult(exit_code=0, stdout=f"Uploaded {file_path} → {nexus_url}"))
            else:
                results.append(ExecutorResult(exit_code=1, stderr=f"HTTP {resp.status_code}: {body[:500]}"))

        except httpx.HTTPError as e:
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


async def _nexus_download(
    client: httpx.AsyncClient,
    url: str,
    repository: str,
    group_id: str | None,
    artifact_id: str | None,
    version: str | None,
    packaging: str,
    classifier: str | None,
    dest: str | None,
    headers: dict[str, str],
    log_path: Path,
) -> ExecutorResult:
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
        resp = await client.get(nexus_url, headers=headers)
        if resp.is_success:
            data = resp.content
            dest_file.write_bytes(data)

            sha256 = hashlib.sha256(data).hexdigest()
            with open(log_path, "a") as f:
                f.write(f"Downloaded {len(data)} bytes → {dest_file}\n")
                f.write(f"SHA256: {sha256}\n")

            return ExecutorResult(exit_code=0, stdout=f"Downloaded {nexus_url} → {dest_file}")

        msg = f"HTTP {resp.status_code}: {resp.text[:500]}"
        with open(log_path, "a") as f:
            f.write(f"{msg}\n")
        return ExecutorResult(exit_code=1, stderr=msg)

    except httpx.HTTPError as e:
        msg = str(e)
        with open(log_path, "a") as f:
            f.write(f"{msg}\n")
        return ExecutorResult(exit_code=1, stderr=msg)


async def _nexus_search(
    client: httpx.AsyncClient,
    url: str,
    repository: str,
    query: str | None,
    headers: dict[str, str],
    log_path: Path,
) -> ExecutorResult:
    search_url = f"{url}/service/rest/v1/search"
    params: dict[str, str] = {"repository": repository}
    if query:
        params["q"] = query

    with open(log_path, "a") as f:
        f.write(f"+ GET {search_url} params={params}\n")

    try:
        resp = await client.get(search_url, params=params, headers=headers)
        data = resp.text

        with open(log_path, "a") as f:
            f.write(data[:2000])

        if resp.is_success:
            return ExecutorResult(exit_code=0, stdout=data)

        msg = f"HTTP {resp.status_code}: {data[:500]}"
        with open(log_path, "a") as f:
            f.write(f"{msg}\n")
        return ExecutorResult(exit_code=1, stderr=msg)

    except httpx.HTTPError as e:
        msg = str(e)
        with open(log_path, "a") as f:
            f.write(f"{msg}\n")
        return ExecutorResult(exit_code=1, stderr=msg)


async def _nexus_delete(
    client: httpx.AsyncClient,
    url: str,
    repository: str,
    group_id: str | None,
    artifact_id: str | None,
    version: str | None,
    packaging: str,
    classifier: str | None,
    headers: dict[str, str],
    log_path: Path,
) -> ExecutorResult:
    maven_path = _build_maven_path(group_id, artifact_id, version, packaging, classifier)
    if not maven_path:
        return ExecutorResult(exit_code=1, stderr=t("Maven coordinates required for delete"))

    nexus_url = f"{url}/repository/{repository}/{maven_path}"

    with open(log_path, "a") as f:
        f.write(f"+ DELETE {nexus_url}\n")

    try:
        resp = await client.delete(nexus_url, headers=headers)
        if resp.is_success:
            with open(log_path, "a") as f:
                f.write(f"HTTP {resp.status_code}: deleted\n")
            return ExecutorResult(exit_code=0, stdout=f"Deleted {nexus_url}")

        msg = f"HTTP {resp.status_code}: {resp.text[:500]}"
        with open(log_path, "a") as f:
            f.write(f"{msg}\n")
        return ExecutorResult(exit_code=1, stderr=msg)

    except httpx.HTTPError as e:
        msg = str(e)
        with open(log_path, "a") as f:
            f.write(f"{msg}\n")
        return ExecutorResult(exit_code=1, stderr=msg)


async def _nexus_list(
    client: httpx.AsyncClient,
    url: str,
    repository: str,
    headers: dict[str, str],
    log_path: Path,
) -> ExecutorResult:
    list_url = f"{url}/service/rest/v1/components"
    params = {"repository": repository}

    with open(log_path, "a") as f:
        f.write(f"+ GET {list_url}\n")

    try:
        resp = await client.get(list_url, params=params, headers=headers)
        data = resp.text

        with open(log_path, "a") as f:
            f.write(data[:2000])

        if resp.is_success:
            return ExecutorResult(exit_code=0, stdout=data)

        msg = f"HTTP {resp.status_code}: {data[:500]}"
        with open(log_path, "a") as f:
            f.write(f"{msg}\n")
        return ExecutorResult(exit_code=1, stderr=msg)

    except httpx.HTTPError as e:
        msg = str(e)
        with open(log_path, "a") as f:
            f.write(f"{msg}\n")
        return ExecutorResult(exit_code=1, stderr=msg)

from __future__ import annotations

import asyncio
import socket
import time
from collections.abc import AsyncGenerator

from taskpps.i18n import t
from taskpps.loaders.agent_loader import AgentLoader
from taskpps.schemas.agent import (
    AgentCheckRequest,
    AgentCheckResponse,
    AgentCheckResult,
    AgentCheckSummary,
)


class AgentService:
    def __init__(self):
        self._loader = AgentLoader()

    def try_connect(self, agent_id: str, timeout: int = 5) -> AgentCheckResult:
        self._loader.clear_cache()
        agent_data = self._loader.get(agent_id)
        if agent_data is None:
            raise ValueError(t("Agent not found: {id}", id=agent_id))
        return self._check_one(agent_data, timeout)

    def check(self, request: AgentCheckRequest) -> AgentCheckResponse:
        self._loader.clear_cache()
        all_agents = self._loader.load_all()
        results = []

        for agent_id, agent_data in all_agents.items():
            if request.agent_id and agent_id != request.agent_id:
                continue

            file_filter = request.file_filter
            if file_filter:
                source_file = agent_data.get("_source_file", "")
                if not _match_file_filter(source_file, file_filter):
                    continue

            results.append(self._check_one(agent_data, request.timeout))

        total = len(results)
        connected = sum(1 for r in results if r.status not in ("failed", "disconnected"))
        failed = total - connected

        return AgentCheckResponse(
            results=results,
            summary=AgentCheckSummary(total=total, connected=connected, failed=failed),
        )

    async def check_stream(self, request: AgentCheckRequest) -> AsyncGenerator[str, None]:
        self._loader.clear_cache()
        all_agents = self._loader.load_all()

        target: list[dict] = []
        for agent_id, agent_data in all_agents.items():
            if request.agent_id and agent_id != request.agent_id:
                continue
            file_filter = request.file_filter
            if file_filter:
                source_file = agent_data.get("_source_file", "")
                if not _match_file_filter(source_file, file_filter):
                    continue
            target.append(agent_data)

        total = len(target)
        connected = 0
        failed = 0

        async def check_one(agent_data: dict) -> AgentCheckResult:
            return await asyncio.to_thread(self._check_one, agent_data, request.timeout)

        tasks = [asyncio.create_task(check_one(a)) for a in target]

        for coro in asyncio.as_completed(tasks):
            result = await coro
            if result.status in ("failed", "disconnected"):
                failed += 1
            else:
                connected += 1
            import json

            yield f"data: {json.dumps(result.model_dump())}\n\n"

        summary = AgentCheckSummary(total=total, connected=connected, failed=failed)
        import json

        yield f"data: summary:{json.dumps(summary.model_dump())}\n\n"

    def _check_one(self, agent_data: dict, timeout: int) -> AgentCheckResult:
        agent_id = agent_data.get("id", "unknown")
        agent_name = agent_data.get("name", agent_id)
        agent_type = agent_data.get("type", "unknown")
        host = agent_data.get("host", "")
        port = agent_data.get("port", 22)
        source_file = agent_data.get("_source_file", "")

        # Execution agents connect via WebSocket, check AgentManager
        if agent_type in ("execution-agent", "agent", "websocket"):
            from taskpps.services.agent_manager import AgentManager

            manager = AgentManager.instance()
            if manager.is_connected(agent_id):
                conn = manager.get_connection(agent_id)
                sys_name = conn.system if conn else ""
                arch_name = conn.arch if conn else ""
                plat = f"{sys_name}/{arch_name}" if sys_name and arch_name else (conn.platform if conn else "")
                return AgentCheckResult(
                    agent_id=agent_id,
                    name=agent_name,
                    type=agent_type,
                    host=conn.hostname if conn else host,
                    port=port,
                    source_file=source_file,
                    status="connected",
                    latency_ms=0,
                    system=sys_name,
                    arch=arch_name,
                    platform=plat,
                    error=None,
                )
            else:
                # WebSocket not connected, try TCP check for host reachability
                if host and host not in ("localhost", "127.0.0.1", "::1"):
                    start = time.monotonic()
                    try:
                        sock = socket.create_connection((host, port), timeout=timeout)
                        sock.close()
                        latency_ms = int((time.monotonic() - start) * 1000)
                        return AgentCheckResult(
                            agent_id=agent_id,
                            name=agent_name,
                            type=agent_type,
                            host=host,
                            port=port,
                            source_file=source_file,
                            status="disconnected",
                            latency_ms=latency_ms,
                            error="Host reachable but execution agent not connected via WebSocket",
                        )
                    except Exception as e:
                        latency_ms = int((time.monotonic() - start) * 1000)
                        return AgentCheckResult(
                            agent_id=agent_id,
                            name=agent_name,
                            type=agent_type,
                            host=host,
                            port=port,
                            source_file=source_file,
                            status="failed",
                            latency_ms=latency_ms,
                            error=t("Host unreachable: {error}", error=str(e)),
                        )
                else:
                    return AgentCheckResult(
                        agent_id=agent_id,
                        name=agent_name,
                        type=agent_type,
                        host=host or "localhost",
                        port=port or 0,
                        source_file=source_file,
                        status="disconnected",
                        latency_ms=0,
                        error="Execution agent not connected via WebSocket",
                    )

        if not host or host in ("localhost", "127.0.0.1", "::1"):
            return AgentCheckResult(
                agent_id=agent_id,
                name=agent_name,
                type=agent_type,
                host=host or "localhost",
                port=port or 0,
                source_file=source_file,
                status="ready",
                latency_ms=0,
                error=None,
            )

        start = time.monotonic()
        try:
            sock = socket.create_connection((host, port), timeout=timeout)
            sock.close()
        except TimeoutError:
            latency_ms = int(timeout * 1000)
            return AgentCheckResult(
                agent_id=agent_id,
                name=agent_name,
                type=agent_type,
                host=host,
                port=port,
                source_file=source_file,
                status="failed",
                latency_ms=latency_ms,
                error="Connection timed out",
            )
        except Exception as e:
            latency_ms = int((time.monotonic() - start) * 1000)
            return AgentCheckResult(
                agent_id=agent_id,
                name=agent_name,
                type=agent_type,
                host=host,
                port=port,
                source_file=source_file,
                status="failed",
                latency_ms=latency_ms,
                error=str(e),
            )

        latency_ms = int((time.monotonic() - start) * 1000)

        credential_id = agent_data.get("credential_id")
        if credential_id:
            auth_result = self._check_ssh_auth(agent_data, timeout)
            if auth_result is not None:
                return auth_result

        detected_system = str(agent_data.get("_detected_system", "") or "")
        detected_arch = str(agent_data.get("_detected_arch", "") or "")
        detected_platform = f"{detected_system}/{detected_arch}" if detected_system and detected_arch else ""
        return AgentCheckResult(
            agent_id=agent_id,
            name=agent_name,
            type=agent_type,
            host=host,
            port=port,
            source_file=source_file,
            status="connected",
            latency_ms=latency_ms,
            system=detected_system,
            arch=detected_arch,
            platform=detected_platform,
            error=None,
        )

    def _check_ssh_auth(self, agent_data: dict, timeout: int) -> AgentCheckResult | None:
        import paramiko

        agent_id = agent_data.get("id", "unknown")
        agent_name = agent_data.get("name", agent_id)
        agent_type = agent_data.get("type", "unknown")
        host = agent_data.get("host", "")
        port = agent_data.get("port", 22)
        username = agent_data.get("username", "root")
        source_file = agent_data.get("_source_file", "")
        credential_id = agent_data.get("credential_id", "")

        cred_data = self._loader.resolve_credential(agent_data)
        if cred_data is None:
            return AgentCheckResult(
                agent_id=agent_id,
                name=agent_name,
                type=agent_type,
                host=host,
                port=port,
                source_file=source_file,
                status="failed",
                latency_ms=0,
                error=t("Credential not found: {id}", id=credential_id),
            )

        cred_username = cred_data.get("username", username)
        connect_kwargs: dict = {}
        key_path = cred_data.get("key_path")
        password = cred_data.get("password")

        if key_path:
            connect_kwargs["key_filename"] = key_path
        elif password:
            connect_kwargs["password"] = password
        else:
            return AgentCheckResult(
                agent_id=agent_id,
                name=agent_name,
                type=agent_type,
                host=host,
                port=port,
                source_file=source_file,
                status="failed",
                latency_ms=0,
                error=t("Credential has no password or key_path"),
            )

        start = time.monotonic()
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        try:
            client.connect(
                hostname=host,
                port=port,
                username=cred_username,
                timeout=timeout,
                **connect_kwargs,
            )
        except paramiko.AuthenticationException as e:
            latency_ms = int((time.monotonic() - start) * 1000)
            return AgentCheckResult(
                agent_id=agent_id,
                name=agent_name,
                type=agent_type,
                host=host,
                port=port,
                source_file=source_file,
                status="failed",
                latency_ms=latency_ms,
                error=t("Authentication failed: {error}", error=str(e)),
            )
        except Exception as e:
            latency_ms = int((time.monotonic() - start) * 1000)
            return AgentCheckResult(
                agent_id=agent_id,
                name=agent_name,
                type=agent_type,
                host=host,
                port=port,
                source_file=source_file,
                status="failed",
                latency_ms=latency_ms,
                error=t("SSH auth check failed: {error}", error=str(e)),
            )

        # 认证成功：探测远端 uname
        system, arch = self._probe_remote_system(client, timeout=min(timeout, 5))
        client.close()
        latency_ms = int((time.monotonic() - start) * 1000)
        # 暂存到 agent_data，便于 _check_one 写入结果
        agent_data["_detected_system"] = system
        agent_data["_detected_arch"] = arch
        return None

    def _probe_remote_system(self, client, timeout: int = 5) -> tuple[str, str]:
        """通过已认证 SSH 会话执行 uname，返回 (system, arch)"""

        def _run(cmd: str) -> str:
            try:
                _stdin, stdout, _stderr = client.exec_command(cmd, timeout=timeout)
                return stdout.read().decode("utf-8", errors="ignore").strip()
            except Exception:
                return ""

        system = _run("uname -s")
        if not system:
            # Windows 没有 uname，使用 ver 或 echo
            system = _run("ver")
        arch = _run("uname -m")
        if not arch:
            arch = _run("echo %PROCESSOR_ARCHITECTURE%")
        return system, arch

    def _probe_remote_host_info(self, client, timeout: int = 5) -> dict:
        """通过已认证 SSH 会话采集主机硬件/系统信息"""
        import re

        def _run(cmd: str) -> str:
            try:
                _stdin, stdout, _stderr = client.exec_command(cmd, timeout=timeout)
                return stdout.read().decode("utf-8", errors="ignore").strip()
            except Exception:
                return ""

        info: dict = {
            "hostname": _run("hostname") or _run("uname -n"),
            "kernel": _run("uname -a") or _run("uname -srv"),
            "os_release": _run("cat /etc/os-release 2>/dev/null | head -10") or _run("lsb_release -a 2>/dev/null"),
            "uptime": _run("uptime"),
            "cpu": {"model": "", "cores": 0, "threads": 0},
            "memory": {"total": "", "used": "", "free": "", "percent": -1},
            "disks": [],
        }

        # CPU：lscpu 输出解析
        lscpu = _run("lscpu 2>/dev/null")
        if lscpu:
            for line in lscpu.splitlines():
                low = line.lower()
                if "model name" in low:
                    info["cpu"]["model"] = line.split(":", 1)[-1].strip()
                elif low.startswith("cpu(s):") and "thread" not in low:
                    try:
                        info["cpu"]["threads"] = int(line.split(":", 1)[-1].strip())
                    except Exception:
                        pass
                elif "core(s) per socket" in low or "cores per socket" in low:
                    try:
                        cores_per_socket = int(line.split(":", 1)[-1].strip())
                        sockets = 1
                        for l in lscpu.splitlines():
                            if l.lower().startswith("socket(s):"):
                                try:
                                    sockets = int(l.split(":", 1)[-1].strip())
                                except Exception:
                                    pass
                        info["cpu"]["cores"] = cores_per_socket * sockets
                    except Exception:
                        pass
        # 兜底 nproc
        if info["cpu"]["threads"] == 0:
            nproc = _run("nproc")
            try:
                info["cpu"]["threads"] = int(nproc)
            except Exception:
                pass

        # 内存：free -h / free -m 解析
        free_out = _run("free -h 2>/dev/null") or _run("free -m")
        for line in free_out.splitlines():
            if line.lower().startswith("mem"):
                parts = line.split()
                if len(parts) >= 3:
                    info["memory"]["total"] = parts[1]
                    info["memory"]["used"] = parts[2]
                    info["memory"]["free"] = parts[3] if len(parts) > 3 else ""
                break
        # 用 MemAvailable 算 percent（更准）
        avail = _run("grep MemAvailable /proc/meminfo")
        if avail:
            m = re.search(r"(\d+)\s*kB", avail)
            total_kb = re.search(r"MemTotal:\s*(\d+)\s*kB", _run("grep MemTotal /proc/meminfo"))
            if m and total_kb:
                try:
                    free_kb = int(m.group(1))
                    total = int(total_kb.group(1))
                    if total > 0:
                        info["memory"]["percent"] = round((total - free_kb) * 100 / total)
                except Exception:
                    pass

        # 磁盘：df -h
        df_out = _run("df -h -x tmpfs -x devtmpfs 2>/dev/null") or _run("df -h")
        for line in df_out.splitlines()[1:]:
            parts = line.split()
            if len(parts) < 6:
                continue
            fs, size, used, avail, percent, mount = parts[0], parts[1], parts[2], parts[3], parts[4], parts[5]
            pct = -1
            try:
                pct = int(percent.rstrip("%"))
            except Exception:
                pass
            info["disks"].append(
                {
                    "filesystem": fs,
                    "size": size,
                    "used": used,
                    "avail": avail,
                    "percent": pct,
                    "mount": mount,
                }
            )
        return info


def _match_file_filter(source_file: str, file_filter: str) -> bool:
    import re

    pattern = r"(?:^|/|\\)" + re.escape(file_filter) + r"(\.ya?ml)?$"
    return bool(re.search(pattern, source_file, re.IGNORECASE))

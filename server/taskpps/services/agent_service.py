from __future__ import annotations

import asyncio
import socket
import time
from typing import AsyncGenerator, List, Optional

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
        connected = sum(1 for r in results if r.status != "failed")
        failed = total - connected

        return AgentCheckResponse(
            results=results,
            summary=AgentCheckSummary(total=total, connected=connected, failed=failed),
        )

    async def check_stream(self, request: AgentCheckRequest) -> AsyncGenerator[str, None]:
        self._loader.clear_cache()
        all_agents = self._loader.load_all()

        target: List[dict] = []
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
            if result.status == "failed":
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
            latency_ms = int((time.monotonic() - start) * 1000)
            return AgentCheckResult(
                agent_id=agent_id,
                name=agent_name,
                type=agent_type,
                host=host,
                port=port,
                source_file=source_file,
                status="connected",
                latency_ms=latency_ms,
                error=None,
            )
        except socket.timeout:
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


def _match_file_filter(source_file: str, file_filter: str) -> bool:
    import re

    pattern = r"(?:^|/|\\)" + re.escape(file_filter) + r"(\.ya?ml)?$"
    return bool(re.search(pattern, source_file, re.IGNORECASE))
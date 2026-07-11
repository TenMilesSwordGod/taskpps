from __future__ import annotations

import asyncio

import pytest
from unittest.mock import AsyncMock


class TestAgentExecStream:
    @pytest.mark.asyncio
    async def test_exec_stream_not_connected(self, client):
        response = await client.post(
            "/api/agents/nonexistent/exec/stream",
            json={"command": "echo hello", "timeout": 10},
        )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_exec_stream_streams_output_and_result(self, client):
        from taskpps.services.agent_manager import AgentConnection, AgentManager

        manager = AgentManager.instance()
        ws = AsyncMock()
        ws.send_json = AsyncMock()
        conn = AgentConnection("stream-agent", ws)
        manager._connections["stream-agent"] = conn

        async def resolve_after_delay():
            await asyncio.sleep(0.2)
            pending_ids = list(conn._pending_commands.keys())
            if pending_ids:
                cid = pending_ids[0]
                conn.handle_output(cid, "hello world\n")
                conn.resolve_pending(cid, {"exit_code": 0, "signal_name": "", "error": ""})

        resolver_task = asyncio.create_task(resolve_after_delay())

        try:
            response = await client.post(
                "/api/agents/stream-agent/exec/stream",
                json={"command": "echo hello", "timeout": 10},
            )
            assert response.status_code == 200
            assert "text/event-stream" in response.headers.get("content-type", "")

            text = response.text
            assert "event: output" in text
            assert "hello world" in text
            assert "event: result" in text
            assert "event: done" in text
        finally:
            await resolver_task
            for cid in list(conn._pending_commands.keys()):
                conn.cleanup_command(cid)
            manager._connections.pop("stream-agent", None)

    @pytest.mark.asyncio
    async def test_exec_stream_allowed_when_pipeline_running(self, client):
        """REPL 与 pipeline 并存：有 pipeline 任务时 exec/stream 不应返回 409。"""
        from taskpps.services.agent_manager import (
            AgentConnection,
            AgentManager,
            PendingCommandInfo,
        )

        manager = AgentManager.instance()
        ws = AsyncMock()
        ws.send_json = AsyncMock()
        conn = AgentConnection("busy-stream-agent", ws)
        info = PendingCommandInfo(
            command_id="pipeline-cmd",
            command="robot --test example",
            run_id="run-123",
            task_name="main.example",
        )
        conn._pending_commands["pipeline-cmd"] = info
        manager._connections["busy-stream-agent"] = conn

        async def resolve_after_delay():
            await asyncio.sleep(0.2)
            pending_ids = [cid for cid in conn._pending_commands if cid != "pipeline-cmd"]
            if pending_ids:
                cid = pending_ids[0]
                conn.resolve_pending(cid, {"exit_code": 0, "signal_name": "", "error": ""})

        resolver_task = asyncio.create_task(resolve_after_delay())

        try:
            response = await client.post(
                "/api/agents/busy-stream-agent/exec/stream",
                json={"command": "ls -la", "timeout": 10},
            )
            assert response.status_code != 409
            assert response.status_code == 200
        finally:
            await resolver_task
            for cid in list(conn._pending_commands.keys()):
                conn.cleanup_command(cid)
            manager._connections.pop("busy-stream-agent", None)
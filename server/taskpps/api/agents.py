import asyncio
import time
import uuid

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from taskpps.schemas.agent import (
    AgentCheckRequest,
    AgentCheckResponse,
    AgentCheckResult,
    AgentDeployRequest,
    AgentDeployResult,
    AgentExecRequest,
    AgentExecResult,
    AgentStatus,
)
from taskpps.services.agent_manager import AgentManager
from taskpps.services.agent_service import AgentService

router = APIRouter(prefix="/agents", tags=["agents"])

_agent_service = AgentService()


@router.post("/try-connect", response_model=AgentCheckResult)
async def try_connect(body: AgentCheckRequest):
    try:
        result = _agent_service.try_connect(body.agent_id, body.timeout)
        return result
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


@router.post("/check", response_model=AgentCheckResponse)
async def check(body: AgentCheckRequest):
    try:
        result = _agent_service.check(body)
        return result
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.post("/check-stream")
async def check_stream(body: AgentCheckRequest):
    async def generate():
        async for chunk in _agent_service.check_stream(body):
            yield chunk

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/status/{agent_id}", response_model=AgentStatus)
async def agent_status(agent_id: str):
    manager = AgentManager.instance()
    conn = manager.get_connection(agent_id)
    if conn is None:
        return AgentStatus(agent_id=agent_id, connected=False)

    pending_count = len(conn._pending_commands)
    return AgentStatus(
        agent_id=agent_id,
        connected=True,
        hostname=conn.hostname,
        agent_version=conn.agent_version,
        agent_pid=conn.agent_pid,
        connected_at=conn.connected_at,
        last_heartbeat=conn.last_heartbeat,
        running_commands=pending_count,
    )


@router.get("/list", response_model=list[AgentStatus])
async def agent_list():
    manager = AgentManager.instance()
    result = []
    for agent_id, conn in manager.connections.items():
        result.append(
            AgentStatus(
                agent_id=agent_id,
                connected=True,
                hostname=conn.hostname,
                agent_version=conn.agent_version,
                agent_pid=conn.agent_pid,
                connected_at=conn.connected_at,
                last_heartbeat=conn.last_heartbeat,
                running_commands=len(conn._pending_commands),
            )
        )
    return result


@router.post("/{agent_id}/exec")
async def agent_exec(agent_id: str, body: AgentExecRequest):
    manager = AgentManager.instance()
    conn = manager.get_connection(agent_id)
    if conn is None:
        raise HTTPException(status_code=404, detail=f"Agent '{agent_id}' not connected")

    command_id = str(uuid.uuid4())
    start_time = time.monotonic()

    output_chunks: list[str] = []

    def on_output(data: str) -> None:
        output_chunks.append(data)

    conn.register_output_callback(command_id, on_output)
    fut = manager.create_pending(agent_id, command_id)

    try:
        await manager.send_command(
            agent_id,
            command_id,
            body.command,
            body.env or {},
            body.cwd or "",
            body.timeout,
        )
    except Exception as e:
        conn.cleanup_command(command_id)
        raise HTTPException(status_code=500, detail=f"Failed to send command: {e}") from e

    try:
        result = await asyncio.wait_for(fut, timeout=body.timeout + 10)
    except asyncio.TimeoutError:
        await manager.cancel_command(agent_id, command_id)
        return AgentExecResult(
            agent_id=agent_id,
            exit_code=-1,
            stdout="".join(output_chunks),
            error="execution timeout exceeded",
            duration_ms=int((time.monotonic() - start_time) * 1000),
        )
    except asyncio.CancelledError:
        await manager.cancel_command(agent_id, command_id)
        raise

    exit_code = result.get("exit_code", -1)
    signal_name = result.get("signal_name", "")
    error = result.get("error", "")
    duration_ms = int((time.monotonic() - start_time) * 1000)

    error_msg = ""
    if signal_name:
        error_msg = f"killed by signal {signal_name}"
    elif error:
        error_msg = error

    return AgentExecResult(
        agent_id=agent_id,
        exit_code=exit_code,
        stdout="".join(output_chunks),
        stderr=error_msg,
        duration_ms=duration_ms,
        error=error_msg or None,
    )


@router.post("/deploy", response_model=AgentDeployResult)
async def deploy_agent(body: AgentDeployRequest):
    try:
        from taskpps.services.agent_bootstrap import AgentBootstrap

        bootstrap = AgentBootstrap()
        await bootstrap.bootstrap(body.agent_id)
        return AgentDeployResult(success=True, agent_id=body.agent_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e

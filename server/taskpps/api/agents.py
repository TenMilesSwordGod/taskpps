from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from taskpps.schemas.agent import (
    AgentCheckRequest,
    AgentCheckResponse,
    AgentCheckResult,
    AgentDeployRequest,
    AgentDeployResult,
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
        running_commands=pending_count,
    )


@router.get("/list", response_model=list[AgentStatus])
async def agent_list():
    manager = AgentManager.instance()
    result = []
    for agent_id, conn in manager.connections.items():
        result.append(AgentStatus(
            agent_id=agent_id,
            connected=True,
            hostname=conn.hostname,
            agent_version=conn.agent_version,
            agent_pid=conn.agent_pid,
            connected_at=conn.connected_at,
            running_commands=len(conn._pending_commands),
        ))
    return result


@router.post("/deploy", response_model=AgentDeployResult)
async def deploy_agent(body: AgentDeployRequest):
    try:
        from taskpps.services.agent_bootstrap import AgentBootstrap
        bootstrap = AgentBootstrap()
        import asyncio
        result = await asyncio.to_thread(
            lambda: asyncio.get_event_loop().run_until_complete(
                bootstrap.bootstrap(body.agent_id)
            )
        )
        return AgentDeployResult(success=True, agent_id=body.agent_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e

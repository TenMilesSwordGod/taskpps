from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from taskpps.schemas.agent import AgentCheckRequest, AgentCheckResponse, AgentCheckResult
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

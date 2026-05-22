from typing import List

from fastapi import APIRouter, HTTPException

from taskpps.i18n import t
from taskpps.schemas.trigger import CreateTriggerRequest, TriggerResponse
from taskpps.services.trigger_service import TriggerService

router = APIRouter(prefix="/plugins/triggers", tags=["triggers"])

_trigger_service = TriggerService()


@router.post("/", status_code=201, response_model=TriggerResponse)
async def create_trigger(body: CreateTriggerRequest):
    result = await _trigger_service.create_trigger(
        type=body.type,
        config=body.config,
        pipeline_file=body.pipeline_file,
        enabled=body.enabled,
    )
    return TriggerResponse.from_orm_with_parsed_config(result)


@router.get("/", response_model=List[TriggerResponse])
async def list_triggers():
    triggers = await _trigger_service.list_triggers()
    return [TriggerResponse.from_orm_with_parsed_config(t) for t in triggers]


@router.delete("/{trigger_id}")
async def delete_trigger(trigger_id: str):
    success = await _trigger_service.delete_trigger(trigger_id)
    if not success:
        raise HTTPException(status_code=404, detail=t("Trigger not found"))
    return {"status": "deleted"}

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from taskpps.db.engine import get_session_factory
from taskpps.db.repository import TriggerRepository
from taskpps.models.trigger import TriggerType


class TriggerService:
    async def create_trigger(self, type: str, config: Dict[str, Any], pipeline_file: str, enabled: bool = True) -> dict:
        async with get_session_factory()() as session:
            repo = TriggerRepository(session)
            trigger = await repo.create_trigger(
                type=type,
                config=config,
                pipeline_file=pipeline_file,
                enabled=enabled,
            )
            return {
                "id": trigger.id,
                "type": trigger.type,
                "config": trigger.config,
                "pipeline_file": trigger.pipeline_file,
                "enabled": trigger.enabled,
                "created_at": trigger.created_at,
            }

    async def list_triggers(self) -> List[dict]:
        async with get_session_factory()() as session:
            repo = TriggerRepository(session)
            triggers = await repo.list_triggers()
            return [
                {
                    "id": t.id,
                    "type": t.type,
                    "config": t.config,
                    "pipeline_file": t.pipeline_file,
                    "enabled": t.enabled,
                    "created_at": t.created_at,
                }
                for t in triggers
            ]

    async def delete_trigger(self, trigger_id: str) -> bool:
        async with get_session_factory()() as session:
            repo = TriggerRepository(session)
            return await repo.delete_trigger(trigger_id)

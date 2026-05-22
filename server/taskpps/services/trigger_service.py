from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from taskpps.db.engine import get_session_factory
from taskpps.db.repository import TriggerRepository
from taskpps.models.trigger import TriggerType


class TriggerService:
    async def create_trigger(self, type: str, config: Dict[str, Any], pipeline_file: str, enabled: bool = True):
        async with get_session_factory()() as session:
            repo = TriggerRepository(session)
            trigger = await repo.create_trigger(
                type=type,
                config=config,
                pipeline_file=pipeline_file,
                enabled=enabled,
            )
            return trigger

    async def list_triggers(self):
        async with get_session_factory()() as session:
            repo = TriggerRepository(session)
            triggers = await repo.list_triggers()
            return triggers

    async def delete_trigger(self, trigger_id: str) -> bool:
        async with get_session_factory()() as session:
            repo = TriggerRepository(session)
            return await repo.delete_trigger(trigger_id)

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import select

from taskpps.db.engine import get_session_factory
from taskpps.models.plugin import Plugin
from taskpps.schemas.plugin import PluginResponse
from taskpps.services.plugin_center import get_plugin_center

router = APIRouter(prefix="/plugins", tags=["plugins"])


def _enrich_plugin(db_plugin: Plugin) -> dict:
    result = {
        "id": db_plugin.id,
        "name": db_plugin.name,
        "type": db_plugin.type,
        "version": db_plugin.version,
        "enabled": db_plugin.enabled,
        "help_msg": db_plugin.help_msg,
        "config": db_plugin.config,
        "created_at": db_plugin.created_at,
        "updated_at": db_plugin.updated_at,
        "status": "unknown",
    }
    pc = get_plugin_center()
    if pc is not None:
        p_info = pc.get_plugin(db_plugin.name)
        if p_info is not None:
            result["status"] = p_info.status
            result["type"] = p_info.type
            result["version"] = p_info.version
            result["help_msg"] = p_info.help_msg
        else:
            result["status"] = "db_only"
    return result


@router.get("/", response_model=list[PluginResponse])
async def list_plugins(type: str | None = Query(default=None, description="按插件类型筛选")):
    async with get_session_factory()() as session:
        stmt = select(Plugin).order_by(Plugin.created_at)
        if type:
            stmt = stmt.where(Plugin.type == type)
        result = await session.execute(stmt)
        plugins = result.scalars().all()
        enriched = [_enrich_plugin(p) for p in plugins]

        pc = get_plugin_center()
        if pc is not None:
            db_names = {p["name"] for p in enriched}
            for p_info in pc.list_plugins():
                if p_info.name not in db_names:
                    enriched.append({
                        "id": p_info.name,
                        "name": p_info.name,
                        "type": p_info.type,
                        "version": p_info.version,
                        "enabled": False,
                        "help_msg": p_info.help_msg,
                        "config": "{}",
                        "created_at": None,
                        "updated_at": None,
                        "status": p_info.status,
                    })
        return enriched


@router.get("/{name}", response_model=PluginResponse)
async def get_plugin(name: str):
    async with get_session_factory()() as session:
        result = await session.execute(select(Plugin).where(Plugin.name == name))
        plugin = result.scalar_one_or_none()
        if plugin is None:
            pc = get_plugin_center()
            if pc is not None:
                p_info = pc.get_plugin(name)
                if p_info is not None:
                    return {
                        "id": p_info.name,
                        "name": p_info.name,
                        "type": p_info.type,
                        "version": p_info.version,
                        "enabled": False,
                        "help_msg": p_info.help_msg,
                        "config": "{}",
                        "created_at": None,
                        "updated_at": None,
                        "status": p_info.status,
                    }
            raise HTTPException(status_code=404, detail=f"插件 {name} 不存在")
        return _enrich_plugin(plugin)


@router.patch("/{name}/toggle", response_model=PluginResponse)
async def toggle_plugin(name: str):
    async with get_session_factory()() as session:
        result = await session.execute(select(Plugin).where(Plugin.name == name))
        plugin = result.scalar_one_or_none()
        if plugin is None:
            raise HTTPException(status_code=404, detail=f"插件 {name} 不存在")

        plugin.enabled = not plugin.enabled
        from datetime import datetime, timezone

        plugin.updated_at = datetime.now(timezone.utc)
        session.add(plugin)
        await session.commit()
        await session.refresh(plugin)
        return _enrich_plugin(plugin)

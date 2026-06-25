from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import select

from taskpps.db.engine import get_session_factory
from taskpps.models.plugin import Plugin
from taskpps.schemas.plugin import PluginResponse

router = APIRouter(prefix="/plugins", tags=["plugins"])


@router.get("/", response_model=list[PluginResponse])
async def list_plugins(type: str | None = Query(default=None, description="按插件类型筛选")):
    async with get_session_factory()() as session:
        stmt = select(Plugin).order_by(Plugin.created_at)
        if type:
            stmt = stmt.where(Plugin.type == type)
        result = await session.execute(stmt)
        plugins = result.scalars().all()
        return plugins


@router.get("/{name}", response_model=PluginResponse)
async def get_plugin(name: str):
    async with get_session_factory()() as session:
        result = await session.execute(select(Plugin).where(Plugin.name == name))
        plugin = result.scalar_one_or_none()
        if plugin is None:
            raise HTTPException(status_code=404, detail=f"插件 {name} 不存在")
        return plugin


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
        return plugin

from __future__ import annotations

import asyncio
import importlib
import logging
import sys
from pathlib import Path

from taskpps.config import get_pipelines_dir, get_plugins_dir, get_settings
from taskpps.services.cron_trigger import CronTrigger
from taskpps.services.plugin_base import BasePlugin, ExecutorPlugin, NotifierPlugin, TriggerPlugin

logger = logging.getLogger(__name__)


_PLUGIN_TYPE_NAMES = {
    TriggerPlugin: "TriggerPlugin",
    NotifierPlugin: "NotifierPlugin",
    ExecutorPlugin: "ExecutorPlugin",
}


def _get_plugin_type(plugin: BasePlugin) -> str:
    """Determine the plugin type based on which base class it inherits from."""
    for base_cls, type_name in _PLUGIN_TYPE_NAMES.items():
        if isinstance(plugin, base_cls):
            return type_name
    return type(plugin).__name__


def _run_coro_sync(coro):
    """在同步上下文中安全地运行一个异步协程。"""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    else:
        import concurrent.futures

        with concurrent.futures.ThreadPoolExecutor() as pool:
            future = pool.submit(asyncio.run, coro)
            return future.result()


class PluginManager:
    def __init__(self):
        self._plugins: dict[str, BasePlugin] = {}
        self._triggers: dict[str, TriggerPlugin] = {}

    def register(self, name: str, plugin: BasePlugin) -> None:
        self._plugins[name] = plugin
        if isinstance(plugin, TriggerPlugin):
            self._triggers[name] = plugin

    def get(self, name: str) -> BasePlugin | None:
        return self._plugins.get(name)

    def list_plugins(self) -> list[str]:
        return list(self._plugins.keys())

    def discover_plugins(self) -> None:
        plugins_dir = get_plugins_dir()
        if plugins_dir.exists():
            for path in plugins_dir.iterdir():
                if (path.is_dir() and not path.name.startswith("_")) or (
                    path.suffix == ".py" and not path.name.startswith("_")
                ):
                    self._try_load_plugin(path)

        self._upsert_discovered_to_db()
        self._seed_builtin_plugins_to_db()

    def _upsert_discovered_to_db(self) -> None:
        """将已发现的插件信息写入 DB, 默认 enabled=False。"""
        from datetime import datetime, timezone

        async def _upsert():
            from sqlalchemy import select

            from taskpps.db.engine import get_session_factory
            from taskpps.models.plugin import Plugin

            async with get_session_factory()() as session:
                for name, plugin in self._plugins.items():
                    result = await session.execute(select(Plugin).where(Plugin.name == name))
                    existing = result.scalar_one_or_none()
                    if existing:
                        existing.version = plugin.version
                        existing.help_msg = plugin.help_msg
                        existing.type = _get_plugin_type(plugin)
                        existing.updated_at = datetime.now(timezone.utc)
                    else:
                        new_plugin = Plugin(
                            name=plugin.name,
                            type=_get_plugin_type(plugin),
                            version=plugin.version,
                            help_msg=plugin.help_msg,
                            enabled=False,
                        )
                        session.add(new_plugin)
                await session.commit()
            logger.info("Synced %d discovered plugins to DB", len(self._plugins))

        try:
            _run_coro_sync(_upsert())
        except Exception as e:
            logger.warning("Failed to sync discovered plugins to DB: %s", e)

    def _seed_builtin_plugins_to_db(self) -> None:
        """将内置插件（taskpps.plugins 包内）的信息写入 DB，确保插件页面始终有可用的插件类型。"""
        import importlib

        import taskpps.services as _pkg

        pkg_dir = Path(_pkg.__file__).parent
        builtin_plugins: list[dict[str, str]] = []

        for path in sorted(pkg_dir.iterdir()):
            if path.suffix != ".py" or path.name.startswith("_"):
                continue
            module_name = path.stem
            module = importlib.import_module(f"taskpps.services.{module_name}")
            for attr_name in dir(module):
                attr = getattr(module, attr_name)
                if (
                    isinstance(attr, type)
                    and issubclass(attr, BasePlugin)
                    and attr not in (BasePlugin, TriggerPlugin, NotifierPlugin, ExecutorPlugin)
                ):
                    meta = getattr(attr, "PLUGIN_META", None)
                    if meta and isinstance(meta, dict):
                        builtin_plugins.append(meta)

        if not builtin_plugins:
            return

        from datetime import datetime, timezone

        async def _seed():
            from sqlalchemy import select

            from taskpps.db.engine import get_session_factory
            from taskpps.models.plugin import Plugin

            async with get_session_factory()() as session:
                for info in builtin_plugins:
                    result = await session.execute(select(Plugin).where(Plugin.name == info["name"]))
                    existing = result.scalar_one_or_none()
                    if existing:
                        if not existing.help_msg:
                            existing.help_msg = info.get("help_msg", "")
                        if not existing.type:
                            existing.type = info.get("type", "")
                        if not existing.version:
                            existing.version = info.get("version", "")
                        existing.updated_at = datetime.now(timezone.utc)
                    else:
                        new_plugin = Plugin(
                            name=info["name"],
                            type=info.get("type", ""),
                            version=info.get("version", ""),
                            help_msg=info.get("help_msg", ""),
                            enabled=False,
                        )
                        session.add(new_plugin)
                await session.commit()
            logger.info("Seeded %d built-in plugins to DB", len(builtin_plugins))

        try:
            _run_coro_sync(_seed())
        except Exception as e:
            logger.warning("Failed to seed builtin plugins to DB: %s", e)

    def _try_load_plugin(self, path: Path) -> None:
        try:
            if path.is_dir():
                init_file = path / "__init__.py"
                if not init_file.exists():
                    return
                module_name = path.name
            else:
                module_name = path.stem

            plugins_dir = str(path.parent if path.is_file() else str(path.parent))
            if plugins_dir not in sys.path:
                sys.path.insert(0, plugins_dir)

            module = importlib.import_module(module_name)

            for attr_name in dir(module):
                attr = getattr(module, attr_name)
                if (
                    isinstance(attr, type)
                    and issubclass(attr, BasePlugin)
                    and attr not in (BasePlugin, TriggerPlugin, NotifierPlugin, ExecutorPlugin)
                ):
                    try:
                        instance = attr()
                        self.register(instance.name, instance)
                        logger.info(f"Loaded plugin: {instance.name}")
                    except Exception as e:
                        logger.error(f"Failed to instantiate plugin {attr_name}: {e}")
        except Exception as e:
            logger.error(f"Failed to load plugin from {path}: {e}")

    def start_triggers(self, callback=None) -> None:
        from sqlalchemy import select

        from taskpps.db.engine import get_session_factory
        from taskpps.models.plugin import Plugin

        settings = get_settings()

        async def _get_enabled_names() -> set[str] | None:
            try:
                async with get_session_factory()() as session:
                    result = await session.execute(
                        select(Plugin.name).where(Plugin.enabled, Plugin.type == "TriggerPlugin"),
                    )
                    return {row[0] for row in result.fetchall()}
            except Exception:
                logger.warning("Failed to query plugin DB for enabled status, assuming all enabled")
                return None

        try:
            enabled_names = _run_coro_sync(_get_enabled_names())
        except Exception:
            enabled_names = None

        for trigger_cfg in settings.triggers:
            if trigger_cfg.type == "cron" and trigger_cfg.schedule:
                cron_name = f"cron:{trigger_cfg.schedule}:{trigger_cfg.pipeline}"

                if enabled_names is not None and cron_name not in enabled_names:
                    logger.warning("Skipping disabled plugin: %s", cron_name)
                    continue

                pipeline_path = get_pipelines_dir() / trigger_cfg.pipeline
                if not pipeline_path.exists():
                    raise FileNotFoundError(f"Pipeline {trigger_cfg.pipeline} 不存在")

                cron_trigger = CronTrigger(
                    expression=trigger_cfg.schedule,
                    pipeline_file=trigger_cfg.pipeline,
                    callback=callback,
                )
                self.register(cron_trigger.name, cron_trigger)
                cron_trigger.start()
                logger.info(f"Started cron trigger: {cron_trigger.name}")

        for _name, trigger in self._triggers.items():
            if not trigger._running:
                trigger.start()

    def stop_all(self) -> None:
        for name, plugin in self._plugins.items():
            try:
                plugin.stop()
            except Exception as e:
                logger.error(f"Error stopping plugin {name}: {e}")

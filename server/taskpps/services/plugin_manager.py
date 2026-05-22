from __future__ import annotations

import importlib
import logging
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from taskpps.config import get_plugins_dir, get_settings
from taskpps.events.bus import get_event_bus
from taskpps.plugins.base import BasePlugin, TriggerPlugin
from taskpps.plugins.cron_trigger import CronTrigger

logger = logging.getLogger(__name__)


class PluginManager:
    def __init__(self):
        self._plugins: Dict[str, BasePlugin] = {}
        self._triggers: Dict[str, TriggerPlugin] = {}

    def register(self, name: str, plugin: BasePlugin) -> None:
        self._plugins[name] = plugin
        if isinstance(plugin, TriggerPlugin):
            self._triggers[name] = plugin

    def get(self, name: str) -> Optional[BasePlugin]:
        return self._plugins.get(name)

    def list_plugins(self) -> List[str]:
        return list(self._plugins.keys())

    def discover_plugins(self) -> None:
        plugins_dir = get_plugins_dir()
        if not plugins_dir.exists():
            return

        for path in plugins_dir.iterdir():
            if path.is_dir() and not path.name.startswith("_"):
                self._try_load_plugin(path)
            elif path.suffix == ".py" and not path.name.startswith("_"):
                self._try_load_plugin(path)

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
                    and attr is not BasePlugin
                    and attr is not TriggerPlugin
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
        settings = get_settings()
        for trigger_cfg in settings.triggers:
            if trigger_cfg.type == "cron" and trigger_cfg.schedule:
                cron_trigger = CronTrigger(
                    expression=trigger_cfg.schedule,
                    pipeline_file=trigger_cfg.pipeline,
                    callback=callback,
                )
                self.register(cron_trigger.name, cron_trigger)
                cron_trigger.start()
                logger.info(f"Started cron trigger: {cron_trigger.name}")

        for name, trigger in self._triggers.items():
            if not trigger._running:
                trigger.start()

    def stop_all(self) -> None:
        for name, plugin in self._plugins.items():
            try:
                plugin.stop()
            except Exception as e:
                logger.error(f"Error stopping plugin {name}: {e}")

from __future__ import annotations

import contextlib

from taskpps.config import get_settings

_zh: dict[str, str] = {
    # API
    "Run not found": "运行记录未找到",
    "Run not found or cannot be cancelled": "运行记录未找到或无法取消",
    "Trigger not found": "触发器未找到",
    "Invalid or missing API key": "API密钥无效或缺失",
    # Executors
    "Command contains dangerous pattern": "命令包含危险模式",
    "Task exceeded timeout of {timeout}s": "任务超时({timeout}秒)",
    "Task was cancelled": "任务已取消",
    "No invoke task specified": "未指定调用任务",
    "Invalid invoke task format: {task}": "无效的调用任务格式:{task}",
    "Invoke task exceeded timeout of {timeout}s": "调用任务超时({timeout}秒)",
    "Invoke task was cancelled": "调用任务已取消",
    # Loaders
    "Path traversal not allowed: {path}": "不允许的路径遍历:{path}",
    "Invalid pipeline file path: {path}": "无效的流水线文件路径:{path}",
    "Pipeline file not found: {path}": "流水线文件未找到:{path}",
    "Pipeline file is empty: {path}": "流水线文件为空:{path}",
    "Agent file is empty: {name}": "代理配置文件为空:{name}",
    "Agent file not found: {name}": "代理配置文件未找到:{name}",
    "Credential file is empty: {name}": "凭据文件为空:{name}",
    "Credential file not found: {name}": "凭据文件未找到:{name}",
    "Failed to load pipeline: {error}": "加载流水线失败:{error}",
    "Failed to apply overrides: {error}": "应用参数覆盖失败:{error}",
    # DAG
    "Task '{task}' depends on unknown task '{dep}'": "任务'{task}'依赖了未知任务'{dep}'",
    "Cycle detected among tasks: {tasks}": "任务之间存在循环依赖:{tasks}",
    # Runner
    "Step {n}/{total}: {cmd}": "步骤 {n}/{total}:{cmd}",
    "Step {n} failed: {error}": "步骤 {n} 失败:{error}",
    "Pipeline run failed unexpectedly: {error}": "流水线运行意外失败:{error}",
    # Plugin
    "CronTrigger started: {name}": "定时触发器已启动:{name}",
    "CronTrigger stopped: {name}": "定时触发器已停止:{name}",
    "CronTrigger callback error: {error}": "定时触发器回调错误:{error}",
    # App
    "Taskpps API": "Taskpps 接口服务",
}


_en: dict[str, str] = {}


class Translator:
    def __init__(self, locale: str = "zh"):
        self._locale = locale
        self._translations = _zh if locale == "zh" else _en

    def t(self, key: str, **kwargs) -> str:
        msg = self._translations.get(key, key)
        if kwargs:
            with contextlib.suppress(KeyError):
                msg = msg.format(**kwargs)
        return msg


_translator: Translator | None = None


def get_translator() -> Translator:
    global _translator
    if _translator is None:
        settings = get_settings()
        _translator = Translator(locale=settings.locale)
    return _translator


def t(key: str, **kwargs) -> str:
    return get_translator().t(key, **kwargs)


def set_locale(locale: str):
    global _translator
    _translator = Translator(locale=locale)

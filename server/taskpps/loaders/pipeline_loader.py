import logging
import os
import re
from pathlib import Path
from typing import Any

import yaml

from taskpps.config import get_agents_dir, get_pipelines_dir, get_settings
from taskpps.i18n import t
from taskpps.schemas.pipeline import PipelineYAML

log = logging.getLogger(__name__)

_VAR_PATTERN = re.compile(r"\$\{([^}]+)\}")

_credential_loader = None
_agent_loader = None


# v7 (2026-08): 拒绝重复 mapping key 的 SafeLoader。
# 为什么需要：PyYAML 默认对重复 key 静默「后者覆盖前者」，而前端 js-yaml 会报
# duplicated mapping key。两边不一致会导致「前端显示错误、后端照样保存」，
# 重复的 env 变量 / name / task 字段被静默覆盖。
# 注意：只检查「显式书写」的重复 key；`<<: *anchor` 合并后显式覆盖同名字段
# 是合法 YAML 语义，不能误判（初版 flatten_mapping 实现踩过这个坑）。
class _UniqueKeySafeLoader(yaml.SafeLoader):
    def construct_mapping(self, node, deep=False):
        if isinstance(node, yaml.MappingNode):
            explicit_keys: set = set()
            for key_node, _ in node.value:
                if key_node.tag == "tag:yaml.org,2002:merge" or (
                    isinstance(key_node, yaml.ScalarNode) and key_node.value == "<<"
                ):
                    continue
                key = self.construct_object(key_node, deep=deep)
                try:
                    hash(key)
                except TypeError as exc:
                    raise yaml.constructor.ConstructorError(
                        "while constructing a mapping",
                        node.start_mark,
                        f"found unacceptable key ({exc})",
                        key_node.start_mark,
                    ) from exc
                if key in explicit_keys:
                    raise yaml.constructor.ConstructorError(
                        "while constructing a mapping",
                        node.start_mark,
                        f"found duplicate key {key!r}",
                        key_node.start_mark,
                    )
                explicit_keys.add(key)
        return super().construct_mapping(node, deep)


def load_yaml_strict(text: str) -> Any:
    """解析 YAML 并拒绝重复 mapping key（抛 yaml.YAMLError 子类）。"""
    return yaml.load(text, Loader=_UniqueKeySafeLoader)


def _get_credential_loader(project_workdir: Path | None = None):
    global _credential_loader
    if project_workdir is not None:
        from taskpps.loaders.credential_loader import CredentialLoader

        return CredentialLoader(project_workdir / "credentials")
    if _credential_loader is None:
        from taskpps.loaders.credential_loader import CredentialLoader

        _credential_loader = CredentialLoader()
    return _credential_loader


def _get_agent_loader(project_workdir: Path | None = None):
    global _agent_loader
    if project_workdir is not None:
        from taskpps.loaders.agent_loader import AgentLoader

        return AgentLoader(get_agents_dir(project_workdir))
    if _agent_loader is None:
        from taskpps.loaders.agent_loader import AgentLoader

        _agent_loader = AgentLoader()
    return _agent_loader


# AgentConnection 字段名 → 属性名的映射（用于 WebSocket 连接 fallback）
_AGENT_CONNECTION_FIELD_MAP = {
    "host": ("hostname", "ip"),
    "hostname": ("hostname",),
    "ip": ("ip",),
    "platform": ("platform",),
    "system": ("system",),
    "arch": ("arch",),
    "agent_version": ("agent_version",),
    "id": ("agent_id",),
}


def _resolve_agent_field_from_connection(agent_id: str, field: str) -> str | None:
    """配置文件中找不到 agent 时，尝试从 AgentManager 的 WebSocket 连接解析字段。

    与 create_executor 的 fallback 逻辑保持一致：execution-agent 可能没有
    agents/ 配置文件，仅通过 WebSocket 连接注册。
    """
    try:
        from taskpps.services.agent_manager import AgentManager

        conn = AgentManager.instance().get_connection(agent_id)
        if conn is None:
            return None
        attr_names = _AGENT_CONNECTION_FIELD_MAP.get(field)
        if attr_names is None:
            return None
        for attr in attr_names:
            value = getattr(conn, attr, "")
            if value:
                return str(value)
        return ""
    except Exception:
        return None


def _resolve_variable_match(match, env: dict[str, str], project_workdir: Path | None = None) -> str:
    ref = match.group(1)

    if ref.startswith("credential:"):
        try:
            rest = ref.split(":", 1)[1]
            cred_id, field = rest.split(".", 1)
            cred_loader = _get_credential_loader(project_workdir)
            return str(cred_loader.get_field(cred_id, field))
        except (ValueError, KeyError) as e:
            import logging

            logging.getLogger("taskpps.pipelines").warning(
                t("Failed to resolve variable '{ref}': {error}", ref=ref, error=str(e))
            )
            return match.group(0)

    elif ref.startswith("agent:"):
        try:
            rest = ref.split(":", 1)[1]
            agent_id, field = rest.split(".", 1)
            agent_loader = _get_agent_loader(project_workdir)
            try:
                return str(agent_loader.get_field(agent_id, field))
            except KeyError:
                # 配置文件中未找到 agent，尝试从 WebSocket 连接解析
                # 与 create_executor 的 fallback 逻辑保持一致（executors/__init__.py:72-80）
                resolved = _resolve_agent_field_from_connection(agent_id, field)
                if resolved is not None:
                    return resolved
                raise
        except (ValueError, KeyError) as e:
            import logging

            logging.getLogger("taskpps.pipelines").warning(
                t("Failed to resolve variable '{ref}': {error}", ref=ref, error=str(e))
            )
            return match.group(0)

    elif ref.startswith("env."):
        key = ref[4:]
        # 按优先级查找: 传入的 env > settings.env > os.environ
        if key in env:
            return env[key]
        settings = get_settings()
        if key in settings.env:
            return settings.env[key]
        return os.environ.get(key, match.group(0))

    else:
        # 按优先级查找: 传入的 env > settings.env > os.environ
        if ref in env:
            return env[ref]
        settings = get_settings()
        if ref in settings.env:
            return settings.env[ref]
        if ref in os.environ:
            return os.environ[ref]
        return match.group(0)


def substitute_env_vars(value: Any, env: dict[str, str], project_workdir: Path | None = None) -> Any:
    if isinstance(value, str):
        result = value
        for _ in range(10):
            new_result = _VAR_PATTERN.sub(lambda m: _resolve_variable_match(m, env, project_workdir), result)
            if new_result == result:
                break
            result = new_result
        return result
    if isinstance(value, dict):
        return {k: substitute_env_vars(v, env, project_workdir) for k, v in value.items()}
    if isinstance(value, list):
        return [substitute_env_vars(item, env, project_workdir) for item in value]
    return value


def resolve_task_env_vars(
    data: Any, params_env: dict[str, str] | None = None, project_workdir: Path | None = None
) -> Any:
    """对快照中的每个任务再做一次变量替换，把任务级 env 也纳入。

    为什么这么写：全局 substitute_env_vars 只使用 pipeline 顶层 config.env + 运行参数 env，
    而执行时 ExecutionContext.get_task_env 还会叠加 subpipeline config.env 与 task.env。
    为了让前端「重试」弹窗/版本展示的命令与实际执行一致（所见即所跑），这里按任务再替换一次。
    仅处理命令字段（command/commands/steps）与 cwd；env 值本身不递归替换，与执行时 build_env 一致。
    """
    if not isinstance(data, dict):
        return data

    params_env = params_env or {}
    top_env = (data.get("config") or {}).get("env") or {}

    # 兼容两种快照结构：pipelines[].tasks（多子流水线）与顶层 tasks
    task_groups: list[tuple[dict, list]] = []
    for sub in data.get("pipelines") or []:
        if isinstance(sub, dict):
            task_groups.append(((sub.get("config") or {}).get("env") or {}, sub.get("tasks") or []))
    if isinstance(data.get("tasks"), list):
        task_groups.append(({}, data["tasks"]))

    for sub_env, tasks in task_groups:
        for task in tasks:
            if not isinstance(task, dict):
                continue
            # 优先级与 ExecutionContext.get_task_env 一致：顶层 config.env < sub config.env < task.env < 运行参数
            task_env = {**top_env, **sub_env, **(task.get("env") or {}), **params_env}
            # cwd 与命令一样做模板替换，保证弹窗预填值与重试记录一致
            for field in ("command", "commands", "steps", "cwd"):
                if field in task:
                    task[field] = substitute_env_vars(task[field], task_env, project_workdir)
    return data


class PipelineLoader:
    def __init__(self, base_dir: Path | None = None):
        self._base_dir = base_dir

    @property
    def base_dir(self) -> Path:
        return self._base_dir or get_pipelines_dir()

    def load(self, pipeline_file: str, env: dict[str, str] | None = None, project_workdir: Path | None = None) -> PipelineYAML:
        p = Path(pipeline_file)
        if len(p.parts) > 0 and p.parts[0] == self.base_dir.name:
            p = Path(*p.parts[1:])
            pipeline_file = str(p)
        path = self.base_dir / pipeline_file
        try:
            resolved = path.resolve()
            # v7 (2026-08): 用 relative_to 做目录归属判断，替代 startswith 前缀比较。
            # startswith 会放行「同前缀兄弟目录」（如 pipelines_evil/），造成路径穿越。
            resolved.relative_to(self.base_dir.resolve())
        except (OSError, ValueError):
            raise FileNotFoundError(t("Invalid pipeline file path: {path}", path=pipeline_file)) from None

        if not path.exists():
            raise FileNotFoundError(t("Pipeline file not found: {path}", path=pipeline_file))

        with open(path) as f:
            # v7 (2026-08): 严格解析，重复 key 视为非法（与前端 js-yaml 对齐）
            data = load_yaml_strict(f.read())

        if data is None:
            raise ValueError(t("Pipeline file is empty: {path}", path=pipeline_file))

        # 提取 pipeline 自身的 config.env，合并到 env 中，使这些变量在替换时可用
        # 解决 config.env 中定义的变量无法在命令中通过 ${env.X} 引用的问题
        # 优先级: 传入的 env (params) > config.env
        config_env = (data.get("config") or {}).get("env") or {}
        if isinstance(config_env, dict) and config_env:
            merged = dict(config_env)
            merged.update(env or {})
            env = merged

        # 始终执行变量替换, 即使 env 为空也支持 settings.env 和 os.environ
        # 传递项目工作目录, 使 agent/credential 变量替换能找到项目目录下的配置
        # 优先使用显式传入的 project_workdir, 其次从 base_dir 推导
        effective_workdir = project_workdir or (self.base_dir.parent if self._base_dir is not None else None)
        data = substitute_env_vars(data, env or {}, effective_workdir)

        return PipelineYAML(**data)

    def load_all(self) -> dict[str, PipelineYAML]:
        result = {}
        base = self.base_dir
        if not base.exists():
            return result
        for path in sorted(base.glob("**/*.yaml")):
            try:
                rel = path.relative_to(base)
                spec = self.load(str(rel))
                result[spec.name] = spec
            except Exception as e:
                log.warning("跳过无效 pipeline 文件 %s: %s", path, e)
                continue
        for path in sorted(base.glob("**/*.yml")):
            try:
                rel = path.relative_to(base)
                spec = self.load(str(rel))
                result[spec.name] = spec
            except Exception as e:
                log.warning("跳过无效 pipeline 文件 %s: %s", path, e)
                continue
        return result

    def load_all_with_files(self) -> dict[str, PipelineYAML]:
        """加载所有流水线，返回以文件相对路径为 key 的映射"""
        result = {}
        base = self.base_dir
        if not base.exists():
            return result
        for path in sorted(base.glob("**/*.yaml")):
            try:
                rel = path.relative_to(base)
                spec = self.load(str(rel))
                result[str(rel)] = spec
            except Exception as e:
                log.warning("跳过无效 pipeline 文件 %s: %s", path, e)
                continue
        for path in sorted(base.glob("**/*.yml")):
            try:
                rel = path.relative_to(base)
                spec = self.load(str(rel))
                result[str(rel)] = spec
            except Exception as e:
                log.warning("跳过无效 pipeline 文件 %s: %s", path, e)
                continue
        return result

    # v1 (2026-07): issue #195 — 列表页需要展示非法 pipeline，因此新增此方法
    # 原 load_all_with_files 静默跳过非法文件，此方法同时返回 valid + invalid 两类数据
    # invalid_items 使用统一的 error 结构: {message, line?, column?, path?}
    # v2 (2026-07): issue #195 补充 — invalid_items 增加 raw_content 字段
    #   让前端能拿到原始 YAML 文本填入编辑器，用户可看到并修改错误内容
    def load_all_with_files_and_errors(self) -> tuple[dict[str, PipelineYAML], list[dict]]:
        """加载所有流水线，返回 (valid_specs, invalid_items)

        valid_specs: 以文件相对路径为 key 的合法 PipelineYAML 映射
        invalid_items: 非法文件列表，每项含 file/name/validation_error/raw_content 字段
        """
        from pydantic import ValidationError

        valid = {}
        invalid = []
        base = self.base_dir
        if not base.exists():
            return valid, invalid

        for path in sorted(list(base.glob("**/*.yaml")) + list(base.glob("**/*.yml"))):
            rel = str(path.relative_to(base))
            raw_text = ""
            try:
                raw_text = path.read_text(encoding="utf-8")
                # v7 (2026-08): 严格解析，重复 key 在列表中标记为非法
                data = load_yaml_strict(raw_text)
                if data is None:
                    invalid.append({
                        "file": rel,
                        "name": path.stem,
                        "validation_error": {"message": "YAML 文件为空", "line": 1, "column": 1},
                        "raw_content": raw_text,
                    })
                    continue
                spec = self.load(str(rel))
                valid[rel] = spec
            except yaml.YAMLError as e:
                # YAML 语法错误：从 problem_mark 提取行列号
                line = e.problem_mark.line + 1 if e.problem_mark else 1
                column = e.problem_mark.column + 1 if e.problem_mark else 1
                invalid.append({
                    "file": rel,
                    "name": path.stem,
                    "validation_error": {"message": e.problem or str(e), "line": line, "column": column},
                    "raw_content": raw_text,
                })
            except ValidationError as e:
                # pydantic schema 校验错误：提取错误路径与消息
                err_list = e.errors()
                # 取第一个错误的 loc 路径；优先展示第一个错误详情
                first_err = err_list[0]
                loc_path = ".".join(str(loc_item) for loc_item in first_err["loc"])
                msg = first_err["msg"]
                # 尝试从 data 中提取 name
                name = (data.get("name", path.stem) if isinstance(data, dict) else path.stem)
                invalid.append({
                    "file": rel,
                    "name": name,
                    "validation_error": {
                        "message": msg,
                        "path": loc_path if isinstance(first_err["loc"], (list, tuple)) and len(first_err["loc"]) > 0 else None,
                    },
                    "raw_content": raw_text,
                })
            except Exception as e:
                name = (data.get("name", path.stem)
                        if 'data' in dir() and isinstance(data, dict) else path.stem)
                invalid.append({
                    "file": rel,
                    "name": name,
                    "validation_error": {"message": str(e)},
                    "raw_content": raw_text,
                })

        return valid, invalid

    def parse_dict(
        self,
        data: dict,
        env: dict[str, str] | None = None,
        project_workdir: Path | None = None,
        substitute: bool = True,
    ) -> PipelineYAML:
        """把已解析的 YAML dict 转成 PipelineYAML。

        v7 (2026-08): substitute=False 用于「持久化/展示」场景（DB content、
        GET by-id）—— 必须保留 ${credential:...} 等占位符。否则解析结果会带着
        明文凭据入库，并通过 guest 可读的 by-id 接口泄漏，前端编辑器再次保存
        还会把明文写回磁盘。运行时仍走 load()（默认替换）。
        """
        if not substitute:
            return PipelineYAML(**data)

        if env is None:
            env = {}

        config_env = (data.get("config") or {}).get("env") or {}
        if isinstance(config_env, dict) and config_env:
            merged = dict(config_env)
            merged.update(env)
            env = merged

        effective_workdir = project_workdir or (self.base_dir.parent if self._base_dir is not None else None)
        data = substitute_env_vars(data, env, effective_workdir)

        return PipelineYAML(**data)

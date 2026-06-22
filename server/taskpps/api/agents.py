import asyncio
import contextlib
import time
import uuid
from pathlib import Path

import paramiko
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from taskpps.loaders.agent_loader import AgentLoader
from taskpps.i18n import t

# --- Agent 配置缓存 ---
# 避免每次 /api/agents/all 请求都从磁盘读取 YAML 文件。
# 前端每 5 秒轮询一次，10 秒 TTL 意味着大部分请求命中缓存。
_agents_cache: tuple[list[dict], list] | None = None
_agents_cache_ts: float = 0.0
_AGENTS_CACHE_TTL: float = 10.0
from taskpps.schemas.agent import (
    AgentCheckRequest,
    AgentCheckResponse,
    AgentCheckResult,
    AgentDeployRequest,
    AgentDeployResult,
    AgentExecRequest,
    AgentExecResult,
    AgentHostInfo,
    AgentStatus,
    AgentWithConfig,
    PendingCommandItem,
)
from taskpps.services.agent_manager import AgentManager
from taskpps.services.agent_service import AgentService

router = APIRouter(prefix="/agents", tags=["agents"])

_agent_service = AgentService()


async def _query_all_projects() -> list:
    """查询所有已注册项目。"""
    from taskpps.db.engine import get_session_factory
    from taskpps.db.repository import ProjectRepository

    async with get_session_factory()() as session:
        repo = ProjectRepository(session)
        return await repo.list_projects()


async def _load_agents_from_projects() -> tuple[list[dict], list]:
    """从所有已注册项目加载 agents 配置，返回 (items, projects)。

    items 每项包含 agent cfg + _project_id/_project_name。
    DB 不可用时回退到默认 AgentLoader（仅返回当前 workdir 的 agent）。

    使用 TTL 缓存避免每次请求都读磁盘 YAML 文件。
    """
    global _agents_cache, _agents_cache_ts

    now = time.monotonic()
    if _agents_cache is not None and (now - _agents_cache_ts) < _AGENTS_CACHE_TTL:
        return _agents_cache

    from taskpps.config import get_agents_dir

    projects = await _query_all_projects()

    if not projects:
        loader = AgentLoader()
        agents = loader.load_all()
        result = (
            [
                {**cfg, "id": agent_id, "_project_id": "", "_project_name": "", "_project_workdir": ""}
                for agent_id, cfg in agents.items()
            ],
            [],
        )
        _agents_cache = result
        _agents_cache_ts = now
        return result

    items = []
    for project in projects:
        project_workdir = Path(project.workdir)
        loader = AgentLoader(base_dir=get_agents_dir(project_workdir))
        for agent_id, cfg in loader.load_all().items():
            cfg["id"] = agent_id
            cfg["_project_id"] = project.id
            cfg["_project_name"] = project.name or project.id
            cfg["_project_workdir"] = str(project_workdir)
            items.append(cfg)
    result = (items, projects)
    _agents_cache = result
    _agents_cache_ts = now
    return result


def invalidate_agents_cache() -> None:
    """手动清除 agent 配置缓存（在项目注册/删除时调用）。"""
    global _agents_cache, _agents_cache_ts
    _agents_cache = None
    _agents_cache_ts = 0.0


async def _load_agent_max_parallel_map() -> dict[str, int]:
    """加载所有 agent 的 max_parallel 配置，返回 agent_id -> max_parallel 映射。"""
    try:
        agent_items, _ = await _load_agents_from_projects()
        return {str(cfg.get("id", "")): int(cfg.get("max_parallel", 1) or 1) for cfg in agent_items}
    except Exception:
        return {}


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


@router.get("/status/{agent_id}", response_model=AgentStatus)
async def agent_status(agent_id: str):
    manager = AgentManager.instance()
    max_parallel_map = await _load_agent_max_parallel_map()
    if not manager.is_connected(agent_id):
        return AgentStatus(
            agent_id=agent_id,
            connected=False,
            max_parallel=max_parallel_map.get(agent_id, 1),
        )
    conn = manager.get_connection(agent_id)

    running_count = sum(1 for info in conn._pending_commands.values() if info.status == "running") if conn else 0
    queued_count = sum(1 for info in conn._pending_commands.values() if info.status == "queued") if conn else 0
    return AgentStatus(
        agent_id=agent_id,
        connected=True,
        hostname=conn.hostname if conn else "",
        platform=conn.platform if conn else "",
        system=conn.system if conn else "",
        arch=conn.arch if conn else "",
        ip=conn.ip if conn else "",
        agent_version=conn.agent_version if conn else "",
        agent_pid=conn.agent_pid if conn else 0,
        connected_at=conn.connected_at if conn else 0,
        last_heartbeat=conn.last_heartbeat if conn else 0,
        running_commands=running_count,
        queued_commands=queued_count,
        max_parallel=max_parallel_map.get(agent_id, 1),
    )


@router.get("/{agent_id}/pending-commands", response_model=list[PendingCommandItem])
async def agent_pending_commands(agent_id: str):
    """获取 agent 当前正在执行或等待执行的命令列表（按启动/入队时间排序）"""
    manager = AgentManager.instance()
    conn = manager.get_connection(agent_id)
    if conn is None:
        return []
    now = time.time()
    sorted_commands = sorted(
        conn._pending_commands.values(),
        key=lambda info: info.started_at or info.queued_at or 0,
    )
    return [
        PendingCommandItem(
            command_id=info.command_id,
            command=info.command[:500],
            cwd=info.cwd,
            timeout=info.timeout,
            run_id=info.run_id,
            task_name=info.task_name,
            started_at=info.started_at,
            duration_s=round(now - (info.started_at or info.queued_at), 1)
            if (info.started_at or info.queued_at)
            else 0,
            status=info.status,
        )
        for info in sorted_commands
    ]


@router.get("/list", response_model=list[AgentStatus])
async def agent_list():
    manager = AgentManager.instance()
    max_parallel_map = await _load_agent_max_parallel_map()
    result = []
    for agent_id, conn in manager.connections.items():
        if not manager.is_connected(agent_id):
            continue
        running_count = sum(1 for info in conn._pending_commands.values() if info.status == "running")
        queued_count = sum(1 for info in conn._pending_commands.values() if info.status == "queued")
        result.append(
            AgentStatus(
                agent_id=agent_id,
                connected=True,
                hostname=conn.hostname,
                platform=conn.platform,
                system=conn.system,
                arch=conn.arch,
                ip=conn.ip,
                agent_version=conn.agent_version,
                agent_pid=conn.agent_pid,
                connected_at=conn.connected_at,
                last_heartbeat=conn.last_heartbeat,
                running_commands=running_count,
                queued_commands=queued_count,
                max_parallel=max_parallel_map.get(agent_id, 1),
            )
        )
    return result


@router.get("/all", response_model=list[AgentWithConfig])
async def agent_all():
    """返回所有已注册项目中 yaml 配置的 agent + 实时连接状态（未连接也展示）"""
    manager = AgentManager.instance()
    result: list[AgentWithConfig] = []

    agent_items, _ = await _load_agents_from_projects()
    for cfg in agent_items:
        agent_id = str(cfg.get("id", "") or "")
        item = AgentWithConfig(
            agent_id=agent_id,
            name=str(cfg.get("name", "") or ""),
            type=str(cfg.get("type", "") or ""),
            host=str(cfg.get("host", "") or ""),
            port=int(cfg.get("port", 0) or 0),
            source_file=str(cfg.get("_source_file", "") or ""),
            project_id=str(cfg.get("_project_id", "") or ""),
            project_name=str(cfg.get("_project_name", "") or ""),
            max_parallel=int(cfg.get("max_parallel", 1) or 1),
        )
        if manager.is_connected(agent_id):
            conn = manager.get_connection(agent_id)
            if conn is not None:
                item.connected = True
                item.hostname = conn.hostname
                item.platform = conn.platform
                item.system = conn.system
                item.arch = conn.arch
                item.ip = conn.ip
                item.agent_version = conn.agent_version
                item.agent_pid = conn.agent_pid
                item.connected_at = conn.connected_at
                item.last_heartbeat = conn.last_heartbeat
                item.running_commands = sum(1 for info in conn._pending_commands.values() if info.status == "running")
                item.queued_commands = sum(1 for info in conn._pending_commands.values() if info.status == "queued")
                item.net_status = "reachable"
        result.append(item)

    # 并发探测所有 agent 的网络可达性
    async def probe_net(host: str, port: int) -> str:
        if not host or not port:
            return "unknown"
        try:
            fut = asyncio.open_connection(host, port)
            reader, writer = await asyncio.wait_for(fut, timeout=1.5)
            writer.close()
            try:
                await writer.wait_closed()
            except Exception:
                pass
            del reader
            return "reachable"
        except Exception:
            return "unreachable"

    # 并发执行所有探测，填回 net_status（ws 连接的 agent 跳过，已填 reachable）
    if result:
        tasks = []
        idx_map: list[int] = []
        for idx, item in enumerate(result):
            if item.net_status == "unknown" and item.host and item.port:
                tasks.append(probe_net(item.host, item.port))
                idx_map.append(idx)
        if tasks:
            statuses = await asyncio.gather(*tasks, return_exceptions=False)
            for idx, status in zip(idx_map, statuses):
                result[idx].net_status = status

    return result


@router.post("/{agent_id}/exec")
async def agent_exec(agent_id: str, body: AgentExecRequest):
    manager = AgentManager.instance()
    if not manager.is_connected(agent_id):
        raise HTTPException(status_code=404, detail=f"Agent '{agent_id}' not connected")
    conn = manager.get_connection(agent_id)

    # Issue #68: 检查 agent 是否正在执行 pipeline 任务，避免手动 exec 中断正在运行的任务
    pipeline_commands = [
        info
        for info in conn._pending_commands.values()
        if info.run_id  # run_id 非空说明是 pipeline 任务
    ]
    if pipeline_commands:
        task_names = ", ".join(info.task_name or info.command_id for info in pipeline_commands)
        raise HTTPException(
            status_code=409,
            detail=f"Agent '{agent_id}' is executing pipeline task(s): {task_names}. "
            f"Please wait for completion or cancel the run first.",
        )

    cwd = body.cwd or ""
    if not cwd:
        agent_items, _ = await _load_agents_from_projects()
        for item in agent_items:
            if item.get("id") == agent_id and item.get("agent_work_dir"):
                cwd = item["agent_work_dir"]
                break

    command_id = str(uuid.uuid4())
    start_time = time.monotonic()

    output_chunks: list[str] = []

    def on_output(data: str) -> None:
        output_chunks.append(data)

    conn.register_output_callback(command_id, on_output)
    fut = manager.create_pending(agent_id, command_id)

    try:
        await manager.send_command(
            agent_id,
            command_id,
            body.command,
            body.env or {},
            cwd,
            body.timeout,
        )
    except Exception as e:
        conn.cleanup_command(command_id)
        raise HTTPException(status_code=500, detail=f"Failed to send command: {e}") from e

    try:
        result = await asyncio.wait_for(fut, timeout=body.timeout + 10)
    except asyncio.TimeoutError:
        await manager.cancel_command(agent_id, command_id)
        manager.cleanup_command(agent_id, command_id)
        return AgentExecResult(
            agent_id=agent_id,
            exit_code=-1,
            stdout="".join(output_chunks),
            error="execution timeout exceeded",
            duration_ms=int((time.monotonic() - start_time) * 1000),
        )
    except asyncio.CancelledError:
        await manager.cancel_command(agent_id, command_id)
        manager.cleanup_command(agent_id, command_id)
        raise

    exit_code = result.get("exit_code", -1)
    signal_name = result.get("signal_name", "")
    error = result.get("error", "")
    duration_ms = int((time.monotonic() - start_time) * 1000)

    # 清理 output callback（resolve_pending 已清理 pending command）
    conn._output_callbacks.pop(command_id, None)

    error_msg = ""
    if signal_name:
        error_msg = f"killed by signal {signal_name}"
    elif error:
        error_msg = error

    return AgentExecResult(
        agent_id=agent_id,
        exit_code=exit_code,
        stdout="".join(output_chunks),
        stderr=error_msg,
        duration_ms=duration_ms,
        error=error_msg or None,
    )


@router.post("/deploy", response_model=AgentDeployResult)
async def deploy_agent(body: AgentDeployRequest):
    try:
        from taskpps.config import get_agents_dir, get_credentials_dir
        from taskpps.loaders.agent_loader import AgentLoader
        from taskpps.loaders.credential_loader import CredentialLoader
        from taskpps.services.agent_bootstrap import AgentBootstrap

        # 先从已注册项目查找 agent 配置
        agent_items, _ = await _load_agents_from_projects()
        agent_cfg = None
        project_workdir = None
        for item in agent_items:
            if item.get("id") == body.agent_id:
                agent_cfg = item
                project_workdir = item.get("_project_workdir", "")
                break

        if not agent_cfg:
            raise HTTPException(status_code=404, detail=t("Agent not found: {id}", id=body.agent_id))

        loader = AgentLoader(base_dir=get_agents_dir(Path(project_workdir))) if project_workdir else AgentLoader()

        cred_loader = CredentialLoader(base_dir=get_credentials_dir(Path(project_workdir))) if project_workdir else None

        bootstrap = AgentBootstrap()
        await bootstrap.bootstrap(body.agent_id, agent_loader=loader, credential_loader=cred_loader)
        return AgentDeployResult(success=True, agent_id=body.agent_id)
    except Exception as e:
        detail = str(e)
        status_code = 404 if "not found" in detail.lower() else 500
        raise HTTPException(status_code=status_code, detail=detail) from e


@router.get("/{agent_id}/host-info", response_model=AgentHostInfo)
async def get_agent_host_info(agent_id: str):
    """获取 agent host 详细信息（CPU/内存/磁盘/内核等）
    - execution-agent 类型：从 ws connection 拿（agent 主动上报，待实现）
    - ssh-* 类型：复用 paramiko + uname/lscpu/free/df 探测
    - 失败返回 error 字段而非 5xx
    """
    from taskpps.services.agent_service import AgentService

    # 先用默认 loader 查找（测试环境会 mock AgentLoader）
    loader = AgentLoader()
    cfg = loader.get(agent_id)

    # 默认 loader 找不到时，从已注册项目扫描
    if not cfg:
        agent_items, _ = await _load_agents_from_projects()
        for item in agent_items:
            if item.get("id") == agent_id:
                cfg = item
                project_workdir = item.get("_project_workdir", "")
                if project_workdir:
                    from taskpps.config import get_agents_dir

                    loader = AgentLoader(base_dir=get_agents_dir(Path(project_workdir)))
                break

    if not cfg:
        raise HTTPException(status_code=404, detail=f"agent {agent_id} not found")

    agent_type = cfg.get("type", "")

    # execution-agent：目前没存 host_info（需要 agent 端主动上报），返回空
    if agent_type in ("execution-agent", "agent", "websocket", "local") or not agent_type.startswith("ssh-"):
        conn = manager.get_connection(agent_id)
        info = AgentHostInfo(agent_id=agent_id, source="agent")
        if conn:
            info.hostname = conn.hostname
            info.kernel = conn.platform
        if not conn:
            info.error = "execution agent 未连接或未实现 host info 上报（需 agent 端集成）"
        return info

    # SSH 探测：复用 _check_ssh_auth 的认证方式（key_path / password / username 来自 credential）
    svc = AgentService()
    cred_data = loader.resolve_credential(cfg) or {}

    host = cfg.get("host", "")
    port = int(cfg.get("port", 22) or 22)
    # 优先用 credential 里的 username（参考 _check_ssh_auth）
    username = cred_data.get("username") or cfg.get("username") or "root"
    key_path = cred_data.get("key_path")
    password = cred_data.get("password")

    # 兜底：cfg 自身可能也含 username/password
    if not password:
        password = cfg.get("password")

    if not key_path and not password:
        return AgentHostInfo(
            agent_id=agent_id,
            error="凭据缺少 key_path 或 password（请检查 credential yaml 字段：type=ssh-key 用 key_path；type=password 用 password）",
            source="ssh",
        )

    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    connect_kwargs: dict = {}
    if key_path:
        # paramiko key_filename 会自己加载文件，兼容 RSA/Ed25519/ecdsa 等
        connect_kwargs["key_filename"] = key_path
    if password and "key_filename" not in connect_kwargs:
        connect_kwargs["password"] = password
    try:
        await asyncio.to_thread(client.connect, host, port=port, username=username, timeout=5, **connect_kwargs)
    except paramiko.AuthenticationException as e:
        return AgentHostInfo(
            agent_id=agent_id,
            error=f"SSH 认证失败：{e}（username={username}，方法={'私钥' if key_path else '密码'}）",
            source="ssh",
        )
    except Exception as e:
        return AgentHostInfo(agent_id=agent_id, error=f"SSH 连接失败：{e}", source="ssh")
    try:
        data = await asyncio.to_thread(svc._probe_remote_host_info, client, 5)
        data["agent_id"] = agent_id
        data["source"] = "ssh"
        return AgentHostInfo(**data)
    finally:
        with contextlib.suppress(Exception):
            client.close()

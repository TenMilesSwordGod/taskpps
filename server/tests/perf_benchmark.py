"""Server 性能优化 mock 数据与基准测试脚本。

用法:
    cd server
    uv run python tests/perf_benchmark.py

测试内容:
    1. Agent 配置缓存 (TTL=10s)
    2. list_runs() 批量解析 project_name (N+1 → 批量)
    3. 数据库索引效果
    4. SSE 日志流批量查询 task 状态
    5. 连接池 vs NullPool
    6. _recover_stale_runs() 按状态查询 vs 全表扫描
"""

from __future__ import annotations

import asyncio
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Sequence

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import AsyncAdaptedQueuePool, NullPool
from sqlmodel import SQLModel

from taskpps.db.engine import get_session_factory, reset_engine, set_engine
from taskpps.db.repository import (
    ProjectRepository,
    RetryRecordRepository,
    RunRepository,
    TaskRunRepository,
)
from taskpps.models.run import PipelineRun, RunStatus, TaskRetryRecord, TaskRun, TaskStatus


# ─── 配置 ───────────────────────────────────────────────────────────────────

NUM_PROJECTS = 5
NUM_RUNS_PER_PROJECT = 20  # 总共 100 条 run
NUM_TASKS_PER_RUN = 10  # 总共 1000 条 task_run
NUM_RETRIES_PER_TASK = 3  # 总共 3000 条 retry_record
AGENT_YAML_COUNT = 10  # 模拟 agent YAML 文件数


# ─── Mock 数据构造 ──────────────────────────────────────────────────────────


async def seed_mock_data(session: AsyncSession) -> dict:
    """向数据库灌入 mock 数据，返回统计信息。"""
    print("=" * 60)
    print("  灌入 Mock 数据")
    print("=" * 60)

    start = time.monotonic()

    # 1. 创建项目
    project_repo = ProjectRepository(session)
    projects = []
    for i in range(NUM_PROJECTS):
        p = await project_repo.create_project(
            workdir=f"/tmp/mock-project-{i}",
            name=f"MockProject-{i}",
        )
        projects.append(p)
    print(f"  创建 {len(projects)} 个项目")

    # 2. 创建 runs + task_runs
    run_repo = RunRepository(session)
    task_repo = TaskRunRepository(session)
    runs: list[PipelineRun] = []
    task_runs: list[TaskRun] = []

    statuses_cycle = [RunStatus.SUCCESS, RunStatus.FAILED, RunStatus.RUNNING, RunStatus.PENDING, RunStatus.CANCELLED]
    task_statuses_cycle = [TaskStatus.SUCCESS, TaskStatus.FAILED, TaskStatus.RUNNING, TaskStatus.PENDING, TaskStatus.SKIPPED]

    for p_idx, project in enumerate(projects):
        for r_idx in range(NUM_RUNS_PER_PROJECT):
            run = await run_repo.create_run(
                pipeline_name=f"pipeline-{p_idx}-{r_idx}",
                pipeline_file=f"pipeline-{p_idx}-{r_idx}.yaml",
                pipeline_id=f"pipeline-id-{p_idx}",
                pipeline_version=f"v{r_idx % 5}",
                project_id=project.id,
                display_name=f"Run {p_idx}-{r_idx}",
            )
            # 模拟不同状态
            run.status = statuses_cycle[(p_idx + r_idx) % len(statuses_cycle)]
            run.started_at = datetime.now(timezone.utc)
            if run.status in (RunStatus.SUCCESS, RunStatus.FAILED, RunStatus.CANCELLED):
                run.finished_at = datetime.now(timezone.utc)
            runs.append(run)

            for t_idx in range(NUM_TASKS_PER_RUN):
                sub_name = "build" if t_idx % 2 == 0 else "deploy"
                task_name = f"{sub_name}.task-{t_idx}"
                tr = await task_repo.create_task_run(
                    run_id=run.id,
                    task_name=task_name,
                    task_type="command",
                    subpipeline_name=sub_name,
                    log_path=f"/tmp/logs/{run.id}/{task_name}/task.log",
                )
                tr.status = task_statuses_cycle[(p_idx + r_idx + t_idx) % len(task_statuses_cycle)]
                if tr.status in (TaskStatus.SUCCESS, TaskStatus.FAILED, TaskStatus.CANCELLED, TaskStatus.SKIPPED):
                    tr.exit_code = 0 if tr.status == TaskStatus.SUCCESS else 1
                task_runs.append(tr)

    await session.commit()
    print(f"  创建 {len(runs)} 个 run")
    print(f"  创建 {len(task_runs)} 个 task_run")

    # 3. 创建 retry_records
    retry_repo = RetryRecordRepository(session)
    retry_count = 0
    # 只对前 30% 的 task_run 创建 retry
    for tr in task_runs[: len(task_runs) * 3 // 10]:
        for v in range(1, NUM_RETRIES_PER_TASK + 1):
            await retry_repo.create_retry_record(
                run_id=tr.run_id,
                task_run_id=tr.id,
                task_name=tr.task_name,
                subpipeline_name=tr.subpipeline_name,
                retry_version=v,
                command=f"echo retry-v{v}",
                original_command=f"echo retry-v{v}",
                log_path=f"/tmp/logs/{tr.run_id}/{tr.task_name}/retry-v{v}.log",
            )
            retry_count += 1

    await session.commit()
    elapsed = time.monotonic() - start
    print(f"  创建 {retry_count} 条 retry_record")
    print(f"  灌入耗时: {elapsed:.2f}s")
    print()

    return {
        "projects": len(projects),
        "runs": len(runs),
        "task_runs": len(task_runs),
        "retry_records": retry_count,
        "elapsed_s": elapsed,
    }


# ─── 基准测试 ────────────────────────────────────────────────────────────────


async def bench_list_runs(session: AsyncSession) -> None:
    """测试 list_runs + 批量解析 project_name。"""
    print("─" * 60)
    print("  基准: list_runs() + 批量解析 project_name")
    print("─" * 60)

    run_repo = RunRepository(session)

    # 测试 1: list_runs 查询
    start = time.monotonic()
    runs = await run_repo.list_runs(limit=50)
    elapsed_list = time.monotonic() - start
    print(f"  list_runs(limit=50): {len(runs)} 条, 耗时 {elapsed_list*1000:.1f}ms")

    # 测试 2: get_task_summaries 批量
    run_ids = [r.id for r in runs]
    start = time.monotonic()
    summaries = await run_repo.get_task_summaries(run_ids)
    elapsed_summary = time.monotonic() - start
    print(f"  get_task_summaries({len(run_ids)} ids): {elapsed_summary*1000:.1f}ms")

    # 测试 3: 批量解析 project_name (优化后)
    project_ids = {getattr(r, "project_id", None) for r in runs}
    start = time.monotonic()
    from taskpps.services.pipeline_service import _batch_resolve_project_names

    name_map = await _batch_resolve_project_names(project_ids)
    elapsed_batch = time.monotonic() - start
    print(f"  _batch_resolve_project_names({len(project_ids)} ids): {elapsed_batch*1000:.1f}ms, 结果: {name_map}")

    # 对比: 逐条解析 (旧方式)
    from taskpps.services.pipeline_service import _resolve_project_name

    start = time.monotonic()
    for r in runs[:20]:  # 只测 20 条，否则太慢
        await _resolve_project_name(getattr(r, "project_id", None))
    elapsed_n1 = time.monotonic() - start
    print(f"  _resolve_project_name x20 (旧N+1): {elapsed_n1*1000:.1f}ms")
    print(f"  加速比 (20条): {elapsed_n1 / max(elapsed_batch, 0.001):.1f}x")
    print()


async def bench_task_status_batch(session: AsyncSession) -> None:
    """测试 SSE 日志流批量查询 task 状态。"""
    print("─" * 60)
    print("  基准: SSE 日志流批量查询 task 状态")
    print("─" * 60)

    task_repo = TaskRunRepository(session)

    # 获取一批 task IDs
    runs = await RunRepository(session).list_runs(limit=5)
    all_task_ids: list[str] = []
    for run in runs:
        tasks = await task_repo.list_task_runs(run.id)
        all_task_ids.extend(t.id for t in tasks)

    # 批量查询 (优化后)
    start = time.monotonic()
    statuses = await task_repo.get_task_statuses_by_ids(all_task_ids)
    elapsed_batch = time.monotonic() - start
    print(f"  get_task_statuses_by_ids({len(all_task_ids)} ids): {elapsed_batch*1000:.1f}ms, 结果数: {len(statuses)}")

    # 逐条查询 (旧方式)
    start = time.monotonic()
    for tid in all_task_ids:
        await task_repo.get_task_run(tid)
    elapsed_n1 = time.monotonic() - start
    print(f"  get_task_run x{len(all_task_ids)} (旧逐条): {elapsed_n1*1000:.1f}ms")
    print(f"  加速比: {elapsed_n1 / max(elapsed_batch, 0.001):.1f}x")
    print()


async def bench_recover_stale_runs(session: AsyncSession) -> None:
    """测试 _recover_stale_runs 按状态查询 vs 全表扫描。"""
    print("─" * 60)
    print("  基准: _recover_stale_runs 按状态查询 vs 全表扫描")
    print("─" * 60)

    run_repo = RunRepository(session)

    # 优化后: 按状态查询
    start = time.monotonic()
    stale = await run_repo.list_runs_by_statuses([RunStatus.RUNNING, RunStatus.PENDING])
    elapsed_targeted = time.monotonic() - start
    print(f"  list_runs_by_statuses (优化后): {len(stale)} 条, 耗时 {elapsed_targeted*1000:.1f}ms")

    # 旧方式: 全表扫描 + Python 过滤
    start = time.monotonic()
    all_runs = await run_repo.list_runs(limit=10000)
    stale_old = [r for r in all_runs if r.status in (RunStatus.RUNNING, RunStatus.PENDING)]
    elapsed_full = time.monotonic() - start
    print(f"  list_runs(limit=10000) + filter (旧方式): {len(stale_old)} 条, 耗时 {elapsed_full*1000:.1f}ms")
    print(f"  加速比: {elapsed_full / max(elapsed_targeted, 0.001):.1f}x")

    # 批量更新 task (优化后)
    if stale:
        run_id = stale[0].id
        start = time.monotonic()
        count = await run_repo.batch_update_stale_tasks(
            run_id, TaskStatus.FAILED, [TaskStatus.RUNNING, TaskStatus.PENDING]
        )
        elapsed_batch = time.monotonic() - start
        print(f"  batch_update_stale_tasks (优化后): {count} 条, 耗时 {elapsed_batch*1000:.1f}ms")

        # 回滚，不影响后续测试
        await session.rollback()
    print()


async def bench_agent_cache(session: AsyncSession, tmp_project: Path) -> None:
    """测试 Agent 配置缓存。"""
    print("─" * 60)
    print("  基准: Agent 配置缓存 (TTL=10s)")
    print("─" * 60)

    import taskpps.config as cfg

    cfg._project_root = tmp_project
    cfg._server_home = tmp_project
    cfg._project_workdir = tmp_project
    cfg._settings = None
    cfg.load_settings(str(tmp_project / "taskpps.yaml"))

    from taskpps.api.agents import _load_agents_from_projects, invalidate_agents_cache

    # 先注册项目到数据库，这样 _load_agents_from_projects 才能找到 agent YAML
    project_repo = ProjectRepository(session)
    await project_repo.create_project(workdir=str(tmp_project), name="PerfTestProject")
    await session.commit()

    # 第一次: 冷启动 (读磁盘)
    invalidate_agents_cache()
    start = time.monotonic()
    items1, _ = await _load_agents_from_projects()
    elapsed_cold = time.monotonic() - start
    print(f"  冷启动 (读磁盘): {len(items1)} 个 agent, 耗时 {elapsed_cold*1000:.1f}ms")

    # 第二次: 缓存命中
    start = time.monotonic()
    items2, _ = await _load_agents_from_projects()
    elapsed_warm = time.monotonic() - start
    print(f"  缓存命中: {len(items2)} 个 agent, 耗时 {elapsed_warm*1000:.1f}ms")
    print(f"  加速比: {elapsed_cold / max(elapsed_warm, 0.001):.1f}x")

    # 第三次: 仍在 TTL 内
    start = time.monotonic()
    items3, _ = await _load_agents_from_projects()
    elapsed_warm2 = time.monotonic() - start
    print(f"  缓存命中 (第二次): {len(items3)} 个 agent, 耗时 {elapsed_warm2*1000:.1f}ms")

    # 手动失效后重新加载
    invalidate_agents_cache()
    start = time.monotonic()
    items4, _ = await _load_agents_from_projects()
    elapsed_invalidate = time.monotonic() - start
    print(f"  失效后重载: {len(items4)} 个 agent, 耗时 {elapsed_invalidate*1000:.1f}ms")
    print()


async def bench_connection_pool(tmp_path: Path) -> None:
    """测试连接池 vs NullPool。"""
    print("─" * 60)
    print("  基准: 连接池 (AsyncAdaptedQueuePool) vs NullPool")
    print("─" * 60)

    db_file_null = tmp_path / "test_nullpool.db"
    db_file_queue = tmp_path / "test_queuepool.db"

    # NullPool
    engine_null = create_async_engine(
        f"sqlite+aiosqlite:///{db_file_null}",
        connect_args={"check_same_thread": False},
        poolclass=NullPool,
    )
    async with engine_null.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)

    # QueuePool
    engine_queue = create_async_engine(
        f"sqlite+aiosqlite:///{db_file_queue}",
        connect_args={"check_same_thread": False},
        poolclass=AsyncAdaptedQueuePool,
        pool_size=5,
        max_overflow=10,
    )
    async with engine_queue.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)

    # 灌入相同数据
    for engine in [engine_null, engine_queue]:
        from sqlalchemy.ext.asyncio import async_sessionmaker

        factory = async_sessionmaker(engine, expire_on_commit=False)
        async with factory() as session:
            repo = RunRepository(session)
            for i in range(100):
                await repo.create_run(
                    pipeline_name=f"perf-test-{i}",
                    pipeline_file=f"perf-{i}.yaml",
                    pipeline_id=f"perf-id-{i % 5}",
                    pipeline_version=f"v{i % 3}",
                )

    # 测试: 连续 100 次查询
    from sqlalchemy.ext.asyncio import async_sessionmaker

    ITERATIONS = 100

    # NullPool
    factory_null = async_sessionmaker(engine_null, expire_on_commit=False)
    start = time.monotonic()
    for _ in range(ITERATIONS):
        async with factory_null() as session:
            repo = RunRepository(session)
            await repo.list_runs(limit=10)
    elapsed_null = time.monotonic() - start
    print(f"  NullPool x{ITERATIONS}: {elapsed_null*1000:.1f}ms ({elapsed_null/ITERATIONS*1000:.1f}ms/op)")

    # QueuePool
    factory_queue = async_sessionmaker(engine_queue, expire_on_commit=False)
    start = time.monotonic()
    for _ in range(ITERATIONS):
        async with factory_queue() as session:
            repo = RunRepository(session)
            await repo.list_runs(limit=10)
    elapsed_queue = time.monotonic() - start
    print(f"  QueuePool x{ITERATIONS}: {elapsed_queue*1000:.1f}ms ({elapsed_queue/ITERATIONS*1000:.1f}ms/op)")
    print(f"  加速比: {elapsed_null / max(elapsed_queue, 0.001):.1f}x")

    await engine_null.dispose()
    await engine_queue.dispose()
    print()


async def bench_index_effect(tmp_path: Path) -> None:
    """测试索引对查询的影响（对比有索引 vs 无索引的查询时间）。"""
    print("─" * 60)
    print("  基准: 数据库索引效果")
    print("─" * 60)

    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import async_sessionmaker

    db_file = tmp_path / "test_index.db"
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{db_file}",
        connect_args={"check_same_thread": False},
        poolclass=AsyncAdaptedQueuePool,
        pool_size=5,
    )

    # 创建表（含索引，因为模型已定义 index=True）
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)

    factory = async_sessionmaker(engine, expire_on_commit=False)

    # 灌入大量数据
    async with factory() as session:
        repo = RunRepository(session)
        for i in range(500):
            await repo.create_run(
                pipeline_name=f"idx-test-{i}",
                pipeline_file=f"idx-{i % 10}.yaml",
                pipeline_id=f"idx-pid-{i % 20}",
                project_id=f"proj-{i % 5}" if i % 3 != 0 else None,
            )

    # 测试: 按 pipeline_id 查询（有索引）
    async with factory() as session:
        repo = RunRepository(session)
        start = time.monotonic()
        runs = await repo.list_runs(pipeline="idx-test-250")
        elapsed = time.monotonic() - start
        print(f"  按 pipeline_name 查询 (有索引): {len(runs)} 条, 耗时 {elapsed*1000:.1f}ms")

        start = time.monotonic()
        count = await repo.count_runs(pipeline_id="idx-pid-10")
        elapsed = time.monotonic() - start
        print(f"  按 pipeline_id 计数 (有索引): {count} 条, 耗时 {elapsed*1000:.1f}ms")

        # 查看索引列表
        result = await session.execute(text("SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='runs'"))
        indexes = [row[0] for row in result.fetchall()]
        print(f"  runs 表索引: {indexes}")

    await engine.dispose()
    print()


# ─── 主入口 ──────────────────────────────────────────────────────────────────


async def main() -> None:
    import tempfile

    tmp_path = Path(tempfile.mkdtemp(prefix="taskpps-perf-"))
    print(f"临时目录: {tmp_path}")
    print()

    # 构造项目目录结构
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    (project_dir / "pipelines").mkdir()
    (project_dir / "agents").mkdir()
    (project_dir / "credentials").mkdir()
    (project_dir / "tasks").mkdir()
    (project_dir / "plugins").mkdir()

    # 写入配置
    (project_dir / "taskpps.yaml").write_text(
        "server:\n  host: 127.0.0.1\n  port: 26521\n"
        "executor:\n  default_timeout: 60\n  max_workers: 4\n"
        "env:\n  GLOBAL_VAR: global_value\n"
        "plugins:\n  paths: ['plugins']\n"
        "triggers: []\n"
    )

    # 写入 pipeline YAML
    (project_dir / "pipelines" / "deploy.yaml").write_text(
        "name: deploy\noptions:\n  env:\n    APP_ENV: staging\n  timeout: 60\n"
        "tasks:\n  - name: step1\n    command: echo hello\n"
    )

    # 写入多个 agent YAML (模拟多 agent 场景)
    for i in range(AGENT_YAML_COUNT):
        (project_dir / "agents" / f"agent-{i}.yaml").write_text(
            f"host: 10.0.{i // 256}.{i % 256}\nport: 22\nusername: test\nname: Agent-{i}\ntype: ssh-key\n"
        )

    # ─── 初始化数据库 ───
    db_file = tmp_path / "perf_test.db"
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{db_file}",
        connect_args={"check_same_thread": False},
        poolclass=AsyncAdaptedQueuePool,
        pool_size=5,
    )
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)

    set_engine(engine)
    factory = get_session_factory()

    # ─── 灌入 Mock 数据 ───
    async with factory() as session:
        stats = await seed_mock_data(session)

    # ─── 运行基准测试 ───
    async with factory() as session:
        await bench_list_runs(session)

    async with factory() as session:
        await bench_task_status_batch(session)

    async with factory() as session:
        await bench_recover_stale_runs(session)

    async with factory() as session:
        await bench_agent_cache(session, project_dir)

    await bench_connection_pool(tmp_path)

    await bench_index_effect(tmp_path)

    # ─── 清理 ───
    await engine.dispose()
    reset_engine()

    print("=" * 60)
    print("  Mock 数据统计")
    print("=" * 60)
    for k, v in stats.items():
        print(f"  {k}: {v}")
    print()
    print("基准测试完成!")


if __name__ == "__main__":
    asyncio.run(main())

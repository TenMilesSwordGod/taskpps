"""Issue #79: task_summary 聚合查询测试"""
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.pool import StaticPool
from sqlmodel import SQLModel

from taskpps.db.repository import RunRepository
from taskpps.models.run import PipelineRun, TaskRun, RunStatus, TaskStatus, TaskType


@pytest_asyncio.fixture
async def db_session():
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        echo=False,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    async with AsyncSession(engine) as session:
        yield session
    await engine.dispose()


@pytest.mark.asyncio
async def test_get_task_summaries_empty(db_session: AsyncSession):
    """空 run_ids 返回空字典"""
    repo = RunRepository(db_session)
    result = await repo.get_task_summaries([])
    assert result == {}


@pytest.mark.asyncio
async def test_get_task_summaries_no_tasks(db_session: AsyncSession):
    """有 run 但无 task 时返回空计数"""
    repo = RunRepository(db_session)
    run = PipelineRun(pipeline_name="test", id="run-1")
    db_session.add(run)
    await db_session.commit()

    result = await repo.get_task_summaries(["run-1"])
    assert result == {"run-1": {}}


@pytest.mark.asyncio
async def test_get_task_summaries_with_tasks(db_session: AsyncSession):
    """正确聚合任务状态计数"""
    repo = RunRepository(db_session)

    # 创建 run
    run = PipelineRun(pipeline_name="test", id="run-1")
    db_session.add(run)
    await db_session.commit()

    # 创建 tasks
    for status in [TaskStatus.SUCCESS, TaskStatus.SUCCESS, TaskStatus.FAILED, TaskStatus.RUNNING]:
        task = TaskRun(
            run_id="run-1",
            task_name=f"task-{status.value}",
            task_type=TaskType.COMMAND,
            status=status,
        )
        db_session.add(task)
    await db_session.commit()

    result = await repo.get_task_summaries(["run-1"])
    assert result["run-1"]["success"] == 2
    assert result["run-1"]["failed"] == 1
    assert result["run-1"]["running"] == 1


@pytest.mark.asyncio
async def test_get_task_summaries_multiple_runs(db_session: AsyncSession):
    """多个 run 的批量查询"""
    repo = RunRepository(db_session)

    for rid in ["run-1", "run-2"]:
        run = PipelineRun(pipeline_name="test", id=rid)
        db_session.add(run)
    await db_session.commit()

    # run-1: 2 success
    for i in range(2):
        db_session.add(TaskRun(run_id="run-1", task_name=f"t{i}", task_type=TaskType.COMMAND, status=TaskStatus.SUCCESS))
    # run-2: 1 failed + 1 pending
    db_session.add(TaskRun(run_id="run-2", task_name="t0", task_type=TaskType.COMMAND, status=TaskStatus.FAILED))
    db_session.add(TaskRun(run_id="run-2", task_name="t1", task_type=TaskType.COMMAND, status=TaskStatus.PENDING))
    await db_session.commit()

    result = await repo.get_task_summaries(["run-1", "run-2", "run-3"])
    assert result["run-1"] == {"success": 2}
    assert result["run-2"]["failed"] == 1
    assert result["run-2"]["pending"] == 1
    assert result["run-3"] == {}  # 不存在的 run

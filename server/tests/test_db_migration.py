"""数据库迁移测试：验证 _migrate_schema 对旧数据库的增量升级。"""
import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import StaticPool
from sqlmodel import SQLModel

from taskpps.db.engine import _MIGRATIONS, _migrate_schema


@pytest_asyncio.fixture
async def old_db_engine():
    """模拟旧版数据库：只有基础列，缺少迁移列。"""
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        echo=False,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    # 手动创建旧版表结构（不含迁移列）
    async with engine.begin() as conn:
        await conn.execute(text("""
            CREATE TABLE runs (
                id TEXT PRIMARY KEY,
                pipeline_name TEXT NOT NULL,
                pipeline_file TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                params TEXT NOT NULL DEFAULT '{}',
                started_at TIMESTAMP,
                finished_at TIMESTAMP,
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """))
        await conn.execute(text("""
            CREATE TABLE task_runs (
                id TEXT PRIMARY KEY,
                run_id TEXT NOT NULL,
                task_name TEXT NOT NULL,
                task_type TEXT NOT NULL DEFAULT 'command',
                status TEXT NOT NULL DEFAULT 'pending',
                exit_code INTEGER,
                log_path TEXT NOT NULL DEFAULT '',
                started_at TIMESTAMP,
                finished_at TIMESTAMP,
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (run_id) REFERENCES runs(id) ON DELETE CASCADE
            )
        """))
        await conn.execute(text("""
            CREATE TABLE triggers (
                id TEXT PRIMARY KEY,
                type TEXT NOT NULL,
                config TEXT NOT NULL DEFAULT '{}',
                pipeline_file TEXT NOT NULL,
                enabled INTEGER NOT NULL DEFAULT 1,
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """))
        await conn.execute(text("""
            CREATE TABLE projects (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL DEFAULT '',
                workdir TEXT NOT NULL,
                registered_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                active INTEGER NOT NULL DEFAULT 1
            )
        """))
        await conn.execute(text("""
            CREATE TABLE task_retry_records (
                id TEXT PRIMARY KEY,
                run_id TEXT NOT NULL,
                task_run_id TEXT NOT NULL,
                task_name TEXT NOT NULL,
                retry_version INTEGER NOT NULL DEFAULT 0,
                status TEXT NOT NULL DEFAULT 'pending',
                command TEXT NOT NULL DEFAULT '',
                original_command TEXT NOT NULL DEFAULT '',
                log_path TEXT NOT NULL DEFAULT '',
                exit_code INTEGER,
                error TEXT,
                started_at TIMESTAMP,
                finished_at TIMESTAMP,
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (run_id) REFERENCES runs(id) ON DELETE CASCADE,
                FOREIGN KEY (task_run_id) REFERENCES task_runs(id) ON DELETE CASCADE
            )
        """))
    yield engine
    await engine.dispose()


@pytest.mark.asyncio
@pytest.mark.zentao("TC-S0022", domain="server/root", priority="P2")
async def test_migrate_adds_display_name(old_db_engine):
    """迁移应添加 display_name 列到 runs 表。"""
    # 验证迁移前 display_name 不存在
    async with old_db_engine.begin() as conn:
        result = await conn.execute(text("PRAGMA table_info(runs)"))
        columns = {row[1] for row in result.fetchall()}
        assert "display_name" not in columns

    # 注入 engine 到全局，让 _migrate_schema 使用它
    from taskpps.db import engine as engine_mod
    original_engine = engine_mod._engine
    engine_mod._engine = old_db_engine
    try:
        await _migrate_schema()
    finally:
        engine_mod._engine = original_engine

    # 验证迁移后 display_name 存在
    async with old_db_engine.begin() as conn:
        result = await conn.execute(text("PRAGMA table_info(runs)"))
        columns = {row[1] for row in result.fetchall()}
        assert "display_name" in columns


@pytest.mark.asyncio
@pytest.mark.zentao("TC-S0023", domain="server/root", priority="P2")
async def test_migrate_adds_all_missing_columns(old_db_engine):
    """迁移应添加 _MIGRATIONS 中定义的所有缺失列。"""
    from taskpps.db import engine as engine_mod
    original_engine = engine_mod._engine
    engine_mod._engine = old_db_engine
    try:
        await _migrate_schema()
    finally:
        engine_mod._engine = original_engine

    async with old_db_engine.begin() as conn:
        for table_name, expected_cols in _MIGRATIONS.items():
            result = await conn.execute(text(f"PRAGMA table_info({table_name})"))
            existing = {row[1] for row in result.fetchall()}
            for col_name, _ in expected_cols:
                assert col_name in existing, f"Missing column {table_name}.{col_name} after migration"


@pytest.mark.asyncio
@pytest.mark.zentao("TC-S0024", domain="server/root", priority="P2")
async def test_migrate_idempotent(old_db_engine):
    """多次执行迁移不应报错。"""
    from taskpps.db import engine as engine_mod
    original_engine = engine_mod._engine
    engine_mod._engine = old_db_engine
    try:
        await _migrate_schema()
        await _migrate_schema()  # 第二次
    finally:
        engine_mod._engine = original_engine

    # 验证列仍然正确
    async with old_db_engine.begin() as conn:
        result = await conn.execute(text("PRAGMA table_info(runs)"))
        columns = {row[1] for row in result.fetchall()}
        assert "display_name" in columns


@pytest.mark.asyncio
@pytest.mark.zentao("TC-S0025", domain="server/root", priority="P2")
async def test_migrate_preserves_existing_data(old_db_engine):
    """迁移不应丢失已有数据。"""
    # 插入一条旧数据
    async with old_db_engine.begin() as conn:
        await conn.execute(text("""
            INSERT INTO runs (id, pipeline_name, pipeline_file, status)
            VALUES ('test-run-1', 'test-pipeline', 'test.yaml', 'success')
        """))

    from taskpps.db import engine as engine_mod
    original_engine = engine_mod._engine
    engine_mod._engine = old_db_engine
    try:
        await _migrate_schema()
    finally:
        engine_mod._engine = original_engine

    # 验证数据仍在
    async with old_db_engine.begin() as conn:
        result = await conn.execute(text("SELECT id, pipeline_name, status, display_name FROM runs WHERE id = 'test-run-1'"))
        row = result.fetchone()
        assert row is not None
        assert row[0] == 'test-run-1'
        assert row[1] == 'test-pipeline'
        assert row[2] == 'success'
        assert row[3] == ''  # display_name 默认空字符串


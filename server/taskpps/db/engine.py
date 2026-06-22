from __future__ import annotations

import asyncio
import contextlib
import fcntl
import logging
import os
from pathlib import Path

from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import AsyncAdaptedQueuePool
from sqlmodel import SQLModel

from taskpps.config import get_data_dir, get_db_path

logger = logging.getLogger("taskpps.db")

_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None

# 同进程内串行化:asyncio.Lock 在同一个 event loop 里把并发 init_db 排成串行。
# 注意不能跨 event loop 用,所以下面 fcntl 负责跨进程,gunicorn 多 worker 安全。
_in_process_lock: asyncio.Lock | None = None


def _get_in_process_lock() -> asyncio.Lock:
    """Lazy create the asyncio.Lock bound to the current event loop.

    asyncio.Lock 必须绑定到具体的 event loop,所以在第一次调用时再创建。
    """
    global _in_process_lock
    if _in_process_lock is None:
        _in_process_lock = asyncio.Lock()
    return _in_process_lock


@contextlib.contextmanager
def _cross_process_lock():
    """跨进程串行化 init_db() —— fcntl 文件锁。

    gunicorn 多 worker 是不同进程,asyncio.Lock 帮不到。fcntl(LOCK_EX) 在不同进程
    间互斥(同进程内多个 fd 调 flock 不互斥,所以这一步不替代 asyncio.Lock)。
    每次调用新开一个 fd,持锁期间在调用方所在线程阻塞,典型 <1ms。

    当 data dir 为只读文件系统时，fallback 到 /tmp 创建 lock file，
    确保跨进程互斥始终生效。
    """
    _lock_fds: list[int] = []

    def _try_lock(path: Path) -> bool:
        try:
            fd = os.open(str(path), os.O_CREAT | os.O_RDWR, 0o644)
        except OSError:
            return False
        _lock_fds.append(fd)
        return True

    primary = get_data_dir() / ".db_init.lock"
    locked = _try_lock(primary)
    if not locked:
        import tempfile

        fallback = Path(tempfile.gettempdir()) / f"taskpps_db_init_{abs(hash(str(primary))) % 100000}.lock"
        logger.warning(
            "Cannot create lock file %s (read-only filesystem?), using fallback %s", primary, fallback
        )
        locked = _try_lock(fallback)
        if not locked:
            logger.error("Cannot create lock file at either location — proceeding without cross-process lock")
            yield
            return

    try:
        fcntl.flock(_lock_fds[0], fcntl.LOCK_EX)
        yield
    finally:
        for fd in _lock_fds:
            fcntl.flock(fd, fcntl.LOCK_UN)
            os.close(fd)


def get_engine() -> AsyncEngine:
    global _engine
    if _engine is None:
        db_path = get_db_path()
        db_path.parent.mkdir(parents=True, exist_ok=True)
        url = f"sqlite+aiosqlite:///{db_path}"
        logger.debug("Creating engine: url=%s db_path=%s", url, db_path)
        _engine = create_async_engine(
            url,
            echo=False,
            connect_args={"check_same_thread": False, "timeout": 30},
            poolclass=AsyncAdaptedQueuePool,
            pool_size=5,
            max_overflow=10,
            pool_timeout=30,
            pool_recycle=1800,
        )

        @event.listens_for(_engine.sync_engine, "connect")
        def _set_sqlite_pragma(dbapi_connection, connection_record):
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA busy_timeout=30000")
            cursor.close()

    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    global _session_factory
    if _session_factory is None:
        logger.debug("Creating session factory")
        _session_factory = async_sessionmaker(get_engine(), class_=AsyncSession, expire_on_commit=False)
    return _session_factory


async def get_session() -> AsyncSession:
    factory = get_session_factory()
    async with factory() as session:
        yield session


_MIGRATIONS = {
    "runs": [
        ("pipeline_id", "TEXT NOT NULL DEFAULT ''"),
        ("pipeline_version", "TEXT NOT NULL DEFAULT ''"),
        ("project_id", "TEXT"),
        ("error", "TEXT"),
        ("display_name", "TEXT NOT NULL DEFAULT ''"),
    ],
    "task_runs": [
        ("subpipeline_name", "TEXT NOT NULL DEFAULT ''"),
        ("error", "TEXT"),
        ("selected_retry_id", "TEXT"),
    ],
    "triggers": [
        ("project_id", "TEXT"),
    ],
    "projects": [
        ("last_used_at", "TIMESTAMP"),
    ],
}

# 性能优化索引：为高频查询列添加索引
# 仅在索引不存在时创建（IF NOT EXISTS），对已有数据库安全
_INDEX_MIGRATIONS = [
    "CREATE INDEX IF NOT EXISTS ix_runs_pipeline_id ON runs(pipeline_id)",
    "CREATE INDEX IF NOT EXISTS ix_runs_pipeline_file ON runs(pipeline_file)",
    "CREATE INDEX IF NOT EXISTS ix_runs_project_id ON runs(project_id)",
    "CREATE INDEX IF NOT EXISTS ix_runs_created_at ON runs(created_at)",
    "CREATE INDEX IF NOT EXISTS ix_task_runs_run_id ON task_runs(run_id)",
    "CREATE INDEX IF NOT EXISTS ix_task_retry_records_run_id ON task_retry_records(run_id)",
    "CREATE INDEX IF NOT EXISTS ix_task_retry_records_task_run_id ON task_retry_records(task_run_id)",
    "CREATE INDEX IF NOT EXISTS ix_task_retry_records_task_name ON task_retry_records(task_name)",
]


async def _migrate_schema() -> None:
    engine = get_engine()
    async with engine.begin() as conn:
        for table_name, columns in _MIGRATIONS.items():
            result = await conn.execute(text(f"PRAGMA table_info({table_name})"))
            existing = {row[1] for row in result.fetchall()}
            logger.debug("Checking table %s (existing columns: %s)", table_name, sorted(existing))
            # 表不存在时跳过迁移（create_all 应已创建，若被跳过则下次重启会创建）
            if not existing:
                logger.warning("Table '%s' does not exist — skipping migration (will retry on next restart)", table_name)
                continue
            for col_name, col_def in columns:
                if col_name not in existing:
                    logger.debug("Adding column %s.%s %s", table_name, col_name, col_def)
                    await conn.execute(text(f"ALTER TABLE {table_name} ADD COLUMN {col_name} {col_def}"))

        # 创建性能优化索引
        for idx_sql in _INDEX_MIGRATIONS:
            logger.debug("Creating index: %s", idx_sql)
            await conn.execute(text(idx_sql))


async def init_db() -> None:
    """Initialize database schema. Safe to call concurrently across processes
    and within a single process (e.g. asyncio.gather).

    gunicorn 启动时多个 worker 会同时执行 lifespan → init_db()。SQLAlchemy 的
    create_all(checkfirst=True) 是 check-then-create 模式,跨进程存在 TOCTOU 竞态
    (两个 worker 都查到表不存在,然后都尝试 CREATE,后到者失败)。

    双层锁保护:
    1. asyncio.Lock —— 同进程内并发互斥(asyncio.gather 多个 task)
    2. fcntl flock —— 跨进程互斥(gunicorn 多 worker)

    第一个调用者跑 create_all + 迁移,后续调用者等锁释放后再进,
    看到表已存在直接 no-op,迁移也跳过(已存在列)。
    """
    logger.info("Initializing database...")
    async with _get_in_process_lock():
        with _cross_process_lock():
            logger.debug("Acquired lock, creating tables")
            engine = get_engine()
            async with engine.begin() as conn:
                await conn.run_sync(SQLModel.metadata.create_all)
            logger.debug("Tables created, running schema migration")
            await _migrate_schema()
        logger.info("Database initialized")


async def close_db() -> None:
    global _engine, _session_factory
    if _engine is not None:
        logger.debug("Disposing database engine")
        await _engine.dispose()
        _engine = None
        _session_factory = None
    # init_db 的锁是栈式 contextmanager,scope 受 init_db 调用本身控制,
    # close_db 不会主动释放它(若有别的 task 正在 init_db 持锁,我们无权释放)。
    # 但 reset_engine() 走的是测试清理路径,应当假定无并发,直接放手即可。


def reset_engine() -> None:
    global _engine, _session_factory
    _engine = None
    _session_factory = None
    # Test-only: 锁是 contextmanager 栈式管理,reset_engine 只清 engine 状态,
    # 不去碰锁 fd(若有持锁的 init_db task 在飞,释放权应属于它本身)。


def set_engine(engine: AsyncEngine) -> None:
    global _engine, _session_factory
    _engine = engine
    _session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

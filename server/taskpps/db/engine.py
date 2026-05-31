from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool
from sqlmodel import SQLModel

from taskpps.config import get_db_path

_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def get_engine() -> AsyncEngine:
    global _engine
    if _engine is None:
        db_path = get_db_path()
        db_path.parent.mkdir(parents=True, exist_ok=True)
        url = f"sqlite+aiosqlite:///{db_path}"
        _engine = create_async_engine(
            url,
            echo=False,
            connect_args={"check_same_thread": False, "timeout": 30},
            poolclass=NullPool,
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
    ],
    "task_runs": [
        ("subpipeline_name", "TEXT NOT NULL DEFAULT ''"),
    ],
}


async def _migrate_schema() -> None:
    engine = get_engine()
    async with engine.begin() as conn:
        for table_name, columns in _MIGRATIONS.items():
            result = await conn.execute(text(f"PRAGMA table_info({table_name})"))
            existing = {row[1] for row in result.fetchall()}
            for col_name, col_def in columns:
                if col_name not in existing:
                    await conn.execute(text(f"ALTER TABLE {table_name} ADD COLUMN {col_name} {col_def}"))


async def init_db() -> None:
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    await _migrate_schema()


async def close_db() -> None:
    global _engine, _session_factory
    if _engine is not None:
        await _engine.dispose()
        _engine = None
        _session_factory = None


def reset_engine() -> None:
    global _engine, _session_factory
    _engine = None
    _session_factory = None


def set_engine(engine: AsyncEngine) -> None:
    global _engine, _session_factory
    _engine = engine
    _session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

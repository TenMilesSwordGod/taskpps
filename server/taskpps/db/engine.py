from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from sqlmodel import SQLModel
from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession

from taskpps.config import get_db_path

_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def get_engine() -> AsyncEngine:
    global _engine
    if _engine is None:
        db_path = get_db_path()
        db_path.parent.mkdir(parents=True, exist_ok=True)
        url = f"sqlite+aiosqlite:///{db_path}"
        _engine = create_async_engine(url, echo=False, connect_args={"check_same_thread": False})
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


async def init_db() -> None:
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)


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

import pytest
from pathlib import Path
from sqlalchemy.ext.asyncio import create_async_engine

from taskpps.db import _get_repos
from taskpps.db.repository import RunRepository, TaskRunRepository, TriggerRepository
from taskpps.db.engine import get_engine, init_db, close_db, get_engine, reset_engine, set_engine
from sqlmodel import SQLModel


def test_get_repos():
    repos = _get_repos()
    assert repos == (RunRepository, TaskRunRepository, TriggerRepository)


@pytest.mark.asyncio
async def test_get_engine_creates_new(tmp_path):
    reset_engine()
    from taskpps.config import _project_root
    old_root = _project_root
    _project_root = tmp_path
    try:
        engine = get_engine()
        assert engine is not None
        await engine.dispose()
    finally:
        _project_root = old_root
        reset_engine()


@pytest.mark.asyncio
async def test_init_db(tmp_path):
    reset_engine()
    db_file = tmp_path / "test_init.db"
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{db_file}",
        connect_args={"check_same_thread": False},
    )
    set_engine(engine)
    await init_db()
    assert db_file.exists()
    await engine.dispose()
    reset_engine()


@pytest.mark.asyncio
async def test_close_db(tmp_path):
    reset_engine()
    db_file = tmp_path / "test_close.db"
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{db_file}",
        connect_args={"check_same_thread": False},
    )
    set_engine(engine)
    await close_db()
    from taskpps.db.engine import _engine, _session_factory
    assert _engine is None
    assert _session_factory is None


@pytest.mark.asyncio
async def test_close_db_no_engine():
    reset_engine()
    await close_db()


@pytest.mark.asyncio
async def test_get_session(tmp_path):
    reset_engine()
    db_file = tmp_path / "test_session.db"
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{db_file}",
        connect_args={"check_same_thread": False},
    )
    set_engine(engine)
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)

    from taskpps.db.engine import get_session
    async for session in get_session():
        assert session is not None
        break

    await engine.dispose()
    reset_engine()


@pytest.mark.asyncio
async def test_get_engine_reuses():
    reset_engine()
    from taskpps.config import _project_root
    old_root = _project_root
    _project_root = Path("/tmp")
    try:
        engine1 = get_engine()
        engine2 = get_engine()
        assert engine1 is engine2
        await engine1.dispose()
    finally:
        _project_root = old_root
        reset_engine()

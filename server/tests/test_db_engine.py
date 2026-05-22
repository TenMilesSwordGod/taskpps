import pytest
from taskpps.db.engine import get_engine, get_session_factory, reset_engine, set_engine
from sqlalchemy.ext.asyncio import create_async_engine
from sqlmodel import SQLModel


def test_reset_engine():
    reset_engine()
    from taskpps.db import engine as eng
    assert eng._engine is None
    assert eng._session_factory is None


@pytest.mark.asyncio
async def test_set_engine(tmp_path):
    db_file = tmp_path / "custom.db"
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{db_file}",
        connect_args={"check_same_thread": False},
    )
    set_engine(engine)
    assert get_engine() is engine
    assert get_session_factory() is not None
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    await engine.dispose()
    reset_engine()

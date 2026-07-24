import os
import tempfile
import pytest

from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession


@pytest.fixture(scope="function")
def temp_db_path():
    fd, path = tempfile.mkstemp(suffix=".db", prefix="checkpoints_")
    os.close(fd)
    yield path
    try:
        os.unlink(path)
    except OSError:
        pass
    for suffix in ("-shm", "-wal"):
        wal_path = path + suffix
        try:
            os.unlink(wal_path)
        except OSError:
            pass


@pytest.fixture(scope="function")
async def db_session():
    """Create an in-memory SQLite session with all models registered."""
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        echo=False,
    )
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)

    session_factory = async_sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )
    async with session_factory() as session:
        yield session

    await engine.dispose()

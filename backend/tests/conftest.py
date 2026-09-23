import os
import tempfile
import pytest

from fastapi_cache import FastAPICache
from fastapi_cache.backends.inmemory import InMemoryBackend
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession


class TolerantInMemoryBackend(InMemoryBackend):
    """InMemoryBackend.clear(key=...) 在 key 不存在时抛 KeyError。

    生产后端是 Redis，它的 DEL 对不存在的 key 返回 0 而不报错。需要缓存后端
    的测试要的是一个行为一致的替身，否则"清理一个没被缓存过的键"会直接炸掉。
    """

    async def clear(self, namespace=None, key=None):
        try:
            await super().clear(namespace=namespace, key=key)
        except KeyError:
            pass


@pytest.fixture(scope="function")
def initialized_cache():
    """按应用运行时的方式初始化缓存后端。

    `CollectionRepo.delete` / `batch_upsert` 会直接调用 `FastAPICache.clear`，
    未初始化时抛 AssertionError（不是 SQLAlchemyError，仓库的 except 兜不住）。
    使用本 fixture 的测试结束后还原为未初始化状态。
    """
    FastAPICache.init(TolerantInMemoryBackend())
    yield
    FastAPICache.reset()


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

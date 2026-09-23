from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlmodel import SQLModel

from app.memory.sql_repository import SqlMemoryRepository
import app.models.agent_memory  # noqa: F401
import app.models.user  # noqa: F401


@pytest.mark.asyncio
async def test_repository_supports_production_sqlalchemy_async_session():
    engine = create_async_engine("sqlite+aiosqlite://")
    try:
        async with engine.begin() as connection:
            await connection.run_sync(SQLModel.metadata.create_all)

        session_factory = async_sessionmaker(
            engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )
        async with session_factory() as session:
            repository = SqlMemoryRepository(session)
            await repository.put_fact(
                "thread-1",
                "fact-1",
                "likes fantasy anime",
                0.8,
                "test",
                user_id=1,
            )
            await repository.commit()

            facts = await repository.get_facts("thread-1", user_id=1)

        assert [fact["content"] for fact in facts] == ["likes fantasy anime"]
    finally:
        await engine.dispose()

"""Exercise the actual local initialization path against its own connection."""

import pytest
from sqlalchemy import inspect, text
from sqlalchemy.ext.asyncio import create_async_engine

from app.db import database


@pytest.mark.integration
@pytest.mark.db
async def test_local_initialization_migrates_the_same_in_memory_connection(monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    monkeypatch.setattr(database, "engine", engine)
    try:
        await database.init_db()
        await database.init_db()
        async with engine.connect() as connection:
            tables = await connection.run_sync(
                lambda conn: inspect(conn).get_table_names()
            )
            assert "alembic_version" in tables
            revision = await connection.scalar(
                text("SELECT version_num FROM alembic_version")
            )
            assert revision == "c7d1e4f8a2b6"
            assert {
                "users",
                "subject",
                "collection",
                "schedules",
                "anime_broadcast_metadata",
                "agent_run",
            }.issubset(tables)
    finally:
        await engine.dispose()

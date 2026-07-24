"""Tests for MEMORY-002: SQL-backed memory repository."""

from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession

from app.memory.sql_repository import SqlMemoryRepository
from app.models.user import User


@pytest.fixture
async def repo(db_session: AsyncSession) -> SqlMemoryRepository:
    """SqlMemoryRepository backed by a test SQLite session."""
    return SqlMemoryRepository(db_session)


class TestSqlMemoryRepository:
    """CRUD, user isolation, and pagination tests."""

    @pytest.mark.asyncio
    async def test_put_and_get_facts(self, repo: SqlMemoryRepository):
        await repo.put_fact("th1", "f1", "fact one", 0.8, "test", user_id=1)
        await repo.put_fact("th1", "f2", "fact two", 0.3, "test", user_id=1)

        facts = await repo.get_facts("th1", user_id=1)
        assert len(facts) == 2
        contents = {f["content"] for f in facts}
        assert contents == {"fact one", "fact two"}

    @pytest.mark.asyncio
    async def test_put_fact_stores_kind(self, repo: SqlMemoryRepository):
        await repo.put_fact("th1", "f1", "semantic fact", 0.9, "extraction",
                            user_id=1, kind="semantic")

        facts = await repo.get_facts("th1", user_id=1, kind="semantic")
        assert len(facts) == 1
        assert facts[0]["kind"] == "semantic"

    @pytest.mark.asyncio
    async def test_put_fact_preserves_external_id_and_metadata(
        self, repo: SqlMemoryRepository
    ):
        await repo.put_fact(
            "th1",
            "stable-fact-id",
            "semantic fact",
            0.9,
            "extraction",
            user_id=1,
            kind="semantic",
            metadata={"source_run_id": "run-1"},
        )

        fact = (await repo.get_facts("th1", user_id=1))[0]
        assert fact["id"] == "stable-fact-id"
        assert fact["metadata"] == {"source_run_id": "run-1"}

    @pytest.mark.asyncio
    async def test_kind_filtering(self, repo: SqlMemoryRepository):
        await repo.put_fact("th1", "f1", "episodic", 0.5, "conv", user_id=1, kind="episodic")
        await repo.put_fact("th1", "f2", "semantic", 0.5, "extract", user_id=1, kind="semantic")

        episodic = await repo.get_facts("th1", user_id=1, kind="episodic")
        assert len(episodic) == 1
        assert episodic[0]["content"] == "episodic"

    @pytest.mark.asyncio
    async def test_user_isolation(self, repo: SqlMemoryRepository):
        await repo.put_fact("th1", "f1", "user 1 fact", 0.5, "test", user_id=1)
        await repo.put_fact("th1", "f2", "user 2 fact", 0.5, "test", user_id=2)

        u1_facts = await repo.get_facts("th1", user_id=1)
        u2_facts = await repo.get_facts("th1", user_id=2)

        assert len(u1_facts) == 1
        assert u1_facts[0]["content"] == "user 1 fact"
        assert len(u2_facts) == 1
        assert u2_facts[0]["content"] == "user 2 fact"

    @pytest.mark.asyncio
    async def test_two_users_same_thread_cannot_read_each_other(self, repo: SqlMemoryRepository):
        """Two users with the same thread id cannot read each other's memory."""
        await repo.put_fact("shared", "f1", "alice data", 0.5, "test", user_id=1)
        await repo.put_fact("shared", "f2", "bob data", 0.5, "test", user_id=2)

        alice = await repo.get_facts("shared", user_id=1)
        bob = await repo.get_facts("shared", user_id=2)

        assert len(alice) == 1
        assert alice[0]["content"] == "alice data"
        assert len(bob) == 1
        assert bob[0]["content"] == "bob data"

    @pytest.mark.asyncio
    async def test_long_term_kinds_are_user_scoped_across_threads(
        self, repo: SqlMemoryRepository
    ):
        await repo.put_fact(
            "thread-a", "semantic-a", "alice semantic", 0.7, "extract",
            user_id=1, kind="semantic",
        )
        await repo.put_fact(
            "thread-a", "profile-a", "alice profile", 0.9, "explicit",
            user_id=1, kind="profile",
        )
        await repo.put_fact(
            "thread-a", "episode-a", "alice episode", 0.5, "conversation",
            user_id=1, kind="episodic",
        )
        await repo.put_fact(
            "thread-a", "semantic-b", "bob semantic", 0.7, "extract",
            user_id=2, kind="semantic",
        )

        semantic = await repo.get_facts(
            "thread-b", user_id=1, kind="semantic"
        )
        profile = await repo.get_facts(
            "thread-b", user_id=1, kind="profile"
        )
        combined = await repo.get_facts("thread-b", user_id=1)
        episodic = await repo.get_facts(
            "thread-b", user_id=1, kind="episodic"
        )

        assert [fact["content"] for fact in semantic] == ["alice semantic"]
        assert [fact["content"] for fact in profile] == ["alice profile"]
        assert {fact["content"] for fact in combined} == {
            "alice semantic",
            "alice profile",
        }
        assert episodic == []
        assert await repo.count_facts(
            "thread-b", user_id=1, kind="semantic"
        ) == 1

    @pytest.mark.asyncio
    async def test_long_term_fact_deletion_uses_user_scope(
        self, repo: SqlMemoryRepository
    ):
        await repo.put_fact(
            "thread-a", "semantic-a", "alice semantic", 0.7, "extract",
            user_id=1, kind="semantic",
        )

        deleted = await repo.delete_fact(
            "thread-b",
            "semantic-a",
            user_id=1,
            kind="semantic",
        )

        assert deleted is True
        assert await repo.get_facts(
            "thread-a", user_id=1, kind="semantic"
        ) == []

    @pytest.mark.asyncio
    async def test_operations_require_user_ownership(
        self, repo: SqlMemoryRepository
    ):
        with pytest.raises(ValueError, match="user_id"):
            await repo.put_fact("th1", "f1", "private", 0.5, "test")
        with pytest.raises(ValueError, match="user_id"):
            await repo.get_facts("th1")
        with pytest.raises(ValueError, match="user_id"):
            await repo.count_facts("th1")

    @pytest.mark.asyncio
    async def test_delete_fact_is_owner_scoped(self, repo: SqlMemoryRepository):
        await repo.put_fact("th1", "f1", "user one", 0.5, "test", user_id=1)
        await repo.put_fact("th1", "f2", "user two", 0.5, "test", user_id=2)
        user_two = await repo.get_facts("th1", user_id=2)

        deleted = await repo.delete_fact(
            "th1", user_two[0]["id"], user_id=1
        )

        assert deleted is False
        assert len(await repo.get_facts("th1", user_id=2)) == 1

    @pytest.mark.asyncio
    async def test_delete_fact(self, repo: SqlMemoryRepository):
        await repo.put_fact("th1", "f1", "to delete", 0.5, "test", user_id=1)
        fact = (await repo.get_facts("th1", user_id=1))[0]
        deleted = await repo.delete_fact("th1", fact["id"], user_id=1)

        assert deleted is True
        facts = await repo.get_facts("th1", user_id=1)
        assert len(facts) == 0

    @pytest.mark.asyncio
    async def test_get_facts_has_deterministic_pagination(
        self, repo: SqlMemoryRepository
    ):
        for content in ("first", "second", "third"):
            await repo.put_fact(
                "th1", content, content, 0.5, "test", user_id=1
            )

        first_page = await repo.get_facts(
            "th1", user_id=1, offset=0, limit=2
        )
        second_page = await repo.get_facts(
            "th1", user_id=1, offset=2, limit=2
        )

        assert [fact["content"] for fact in first_page] == ["first", "second"]
        assert [fact["content"] for fact in second_page] == ["third"]

    @pytest.mark.asyncio
    async def test_count_facts(self, repo: SqlMemoryRepository):
        n = await repo.count_facts("th1", user_id=1)
        assert n == 0

        await repo.put_fact("th1", "f1", "a", 0.5, "test", user_id=1)
        await repo.put_fact("th1", "f2", "b", 0.5, "test", user_id=1)

        n = await repo.count_facts("th1", user_id=1)
        assert n == 2

    @pytest.mark.asyncio
    async def test_count_with_kind_filter(self, repo: SqlMemoryRepository):
        await repo.put_fact("th1", "f1", "semantic", 0.5, "extract",
                            user_id=1, kind="semantic")
        await repo.put_fact("th1", "f2", "episodic", 0.5, "conv",
                            user_id=1, kind="episodic")

        sem = await repo.count_facts("th1", user_id=1, kind="semantic")
        epi = await repo.count_facts("th1", user_id=1, kind="episodic")
        assert sem == 1
        assert epi == 1

    @pytest.mark.asyncio
    async def test_clear_user_memory(self, repo: SqlMemoryRepository):
        await repo.put_fact("th1", "f1", "a", 0.5, "test", user_id=1)
        await repo.put_fact("th1", "f2", "b", 0.5, "test", user_id=1)
        await repo.put_fact("th1", "f3", "c", 0.5, "test", user_id=2)

        deleted = await repo.clear_user_memory(1)
        assert deleted == 2

        u1 = await repo.get_facts("th1", user_id=1)
        assert len(u1) == 0
        u2 = await repo.get_facts("th1", user_id=2)
        assert len(u2) == 1

    @pytest.mark.asyncio
    async def test_clear_user_memory_by_kind(self, repo: SqlMemoryRepository):
        await repo.put_fact("th1", "f1", "episodic", 0.5, "conv",
                            user_id=1, kind="episodic")
        await repo.put_fact("th1", "f2", "semantic", 0.5, "extract",
                            user_id=1, kind="semantic")

        deleted = await repo.clear_user_memory(1, kind="episodic")
        assert deleted == 1

        remaining = await repo.get_facts("th1", user_id=1)
        assert len(remaining) == 1
        assert remaining[0]["kind"] == "semantic"

    @pytest.mark.asyncio
    async def test_memory_survives_fresh_repository_instance(self, tmp_path):
        database_path = tmp_path / "memory-restart.db"
        database_url = f"sqlite+aiosqlite:///{database_path.as_posix()}"

        first_engine = create_async_engine(database_url)
        async with first_engine.begin() as connection:
            await connection.run_sync(SQLModel.metadata.create_all)
        first_factory = async_sessionmaker(
            first_engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )
        async with first_factory() as session:
            session.add(User(id=1, username="restart-user"))
            await session.commit()
            first_repo = SqlMemoryRepository(session)
            await first_repo.put_fact(
                "thread-1",
                "persistent-fact",
                "survives restart",
                0.7,
                "test",
                user_id=1,
                kind="semantic",
            )
            await first_repo.commit()
        await first_engine.dispose()

        second_engine = create_async_engine(database_url)
        second_factory = async_sessionmaker(
            second_engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )
        async with second_factory() as session:
            second_repo = SqlMemoryRepository(session)
            facts = await second_repo.get_facts(
                "thread-1",
                user_id=1,
                kind="semantic",
            )
        await second_engine.dispose()

        assert [fact["id"] for fact in facts] == ["persistent-fact"]
        assert [fact["content"] for fact in facts] == ["survives restart"]

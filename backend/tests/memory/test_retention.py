"""Tests for MEMORY-002 Step 04: retention and deletion."""

from __future__ import annotations

import pytest

from tests.memory.test_service_typed import (
    FakeRepository,
    _make_svc,
)


class TestRetentionEnforcement:
    """Per-kind retention capacity tests."""

    @pytest.mark.asyncio
    async def test_kind_separate_limits(self):
        """Episodic retention does not evict profile memory."""
        repo = FakeRepository()
        svc = _make_svc(repo=repo)

        # Set limits small: override kind-specific + global
        svc.max_facts = 2  # episodic retains max 2

        # Store 3 episodic facts and 1 profile fact
        for i in range(3):
            await svc.store_fact(
                "th1", f"ep-{i}", importance=0.1, user_id=1, kind="episodic"
            )
        await svc.store_fact(
            "th1", "profile-taste", importance=0.9, user_id=1, kind="profile"
        )

        # Episodic should be at limit (2), profile should still be present
        epi = await repo.get_facts("th1", user_id=1, kind="episodic")
        pro = await repo.get_facts("th1", user_id=1, kind="profile")

        assert len(epi) == 2  # evicted to 2
        assert len(pro) == 1  # never touched by episodic retention
        assert pro[0]["content"] == "profile-taste"

    @pytest.mark.asyncio
    async def test_profile_memory_not_evicted_by_episodic_retention(self):
        """Profile records survive when episodic retention fires."""
        repo = FakeRepository()
        svc = _make_svc(repo=repo)
        svc.max_facts = 1

        # profile stored first
        await svc.store_fact(
            "th1", "profile-entry", importance=0.8, user_id=1, kind="profile"
        )
        # Then many episodic entries
        for i in range(3):
            await svc.store_fact(
                "th1", f"ep-{i}", importance=0.1, user_id=1, kind="episodic"
            )

        pro = await repo.get_facts("th1", user_id=1, kind="profile")
        assert len(pro) == 1

    @pytest.mark.asyncio
    async def test_profile_memory_requires_explicit_deletion(self):
        repo = FakeRepository()
        svc = _make_svc(repo=repo)
        svc.max_facts = 1

        await svc.store_fact("th1", "profile-one", user_id=1, kind="profile")
        await svc.store_fact("th1", "profile-two", user_id=1, kind="profile")

        profile = await repo.get_facts("th1", user_id=1, kind="profile")
        assert len(profile) == 2


class TestRepositoryDeletion:
    """Repository-level deletion tests (require SQL fixture)."""

    @pytest.mark.asyncio
    async def test_clear_user_memory_idempotent(self, db_session):
        from app.memory.sql_repository import SqlMemoryRepository

        repo = SqlMemoryRepository(db_session)
        deleted = await repo.clear_user_memory(999)
        assert deleted == 0

    @pytest.mark.asyncio
    async def test_clear_thread_memory(self, db_session):
        from app.memory.sql_repository import SqlMemoryRepository

        repo = SqlMemoryRepository(db_session)
        await repo.put_fact("th1", "1", "a", 0.5, "test", user_id=1)
        await repo.put_fact("th2", "1", "b", 0.5, "test", user_id=1)

        deleted = await repo.clear_thread_memory("th1", user_id=1)
        assert deleted == 1

        remaining = await repo.get_facts("th1", user_id=1)
        assert len(remaining) == 0
        other = await repo.get_facts("th2", user_id=1)
        assert len(other) == 1

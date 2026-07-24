"""Tests for MEMORY-002 Step 03: kind-aware typed memory service."""

from __future__ import annotations

import asyncio

import pytest

from app.memory.interfaces import MemoryContext, MemoryRepository, MemoryService
from app.memory.service import MemoryServiceImpl


def _make_unique_embed():
    """Return an embed function that produces orthogonal vectors per text."""
    seen = {}

    async def _embed(texts):
        results = []
        for text in texts:
            if text not in seen:
                seen[text] = len(seen)
            v = [0.0] * max(seen[text] + 1, 2)
            v[seen[text]] = 1.0
            results.append(v)
        return results

    return _embed


class FakeRepository(MemoryRepository):
    """Dict-backed fake that supports user_id and kind filtering."""

    def __init__(self) -> None:
        self._store: dict[str, list[dict]] = {}

    def _ns(self, key: str) -> list[dict]:
        if key not in self._store:
            self._store[key] = []
        return self._store[key]

    async def put_fact(
        self, thread_id: str, fact_id: str, content: str,
        importance: float, source: str,
        user_id: int | None = None, kind: str = "episodic",
        metadata: dict | None = None,
    ) -> None:
        self._ns(thread_id).append({
            "id": fact_id,
            "content": content,
            "importance": importance,
            "source": source,
            "timestamp": "2026-01-01T00:00:00",
            "kind": kind,
            "user_id": user_id or 0,
            "metadata": metadata or {},
        })

    async def get_facts(
        self,
        thread_id: str,
        user_id: int | None = None,
        kind: str | None = None,
        offset: int = 0,
        limit: int = 100,
    ) -> list[dict]:
        facts = self._ns(thread_id)
        if user_id is not None:
            facts = [f for f in facts if f.get("user_id") == user_id]
        if kind is not None:
            facts = [f for f in facts if f.get("kind") == kind]
        return list(facts[offset:offset + limit])

    async def delete_fact(
        self,
        thread_id: str,
        fact_id: str,
        user_id: int | None = None,
        kind: str | None = None,
    ) -> bool:
        before = len(self._store.get(thread_id, []))
        self._store[thread_id] = [
            f
            for f in self._store.get(thread_id, [])
            if not (
                f["id"] == fact_id
                and (user_id is None or f.get("user_id") == user_id)
                and (kind is None or f.get("kind") == kind)
            )
        ]
        return len(self._store[thread_id]) < before

    async def count_facts(
        self, thread_id: str, user_id: int | None = None, kind: str | None = None,
    ) -> int:
        return len(await self.get_facts(thread_id, user_id=user_id, kind=kind))


class FakeExtractor:
    """Always returns a fixed set of facts."""

    def __init__(self, facts: list[dict] | None = None) -> None:
        self._facts = facts or []

    async def extract(self, messages: list[dict]) -> list[dict]:
        return self._facts


def _make_svc(repo=None, extractor=None):
    repo = repo or FakeRepository()
    extractor = extractor or FakeExtractor()
    return MemoryServiceImpl(
        repository=repo,
        extractor=extractor,
        api_key="sk-test",
        base_url="https://test",
    )


class TestServiceKindAware:
    """Kind-scoped store and retrieve operations."""

    @pytest.mark.asyncio
    async def test_store_fact_with_kind(self):
        repo = FakeRepository()
        svc = _make_svc(repo=repo)

        async def fake_embed(texts):
            return [[0.5] * 10 for _ in texts]

        svc._vector.embed = fake_embed

        await svc.store_fact("th1", "episodic fact", kind="episodic", user_id=1)
        await svc.store_fact("th1", "semantic fact", kind="semantic", user_id=1)

        episodic = await repo.get_facts("th1", kind="episodic")
        semantic = await repo.get_facts("th1", kind="semantic")

        assert len(episodic) == 1
        assert episodic[0]["content"] == "episodic fact"
        assert len(semantic) == 1
        assert semantic[0]["content"] == "semantic fact"

    @pytest.mark.asyncio
    async def test_retrieve_context_respects_kind(self):
        repo = FakeRepository()
        svc = _make_svc(repo=repo)

        async def fake_embed(texts):
            return [[0.5] * 10 for _ in texts]

        svc._vector.embed = fake_embed

        await svc.store_fact("th1", "episodic", kind="episodic", user_id=1)
        await svc.store_fact("th1", "semantic", kind="semantic", user_id=1)

        ctx_epi = await svc.retrieve_context("th1", "query", kind="episodic", user_id=1)
        ctx_sem = await svc.retrieve_context("th1", "query", kind="semantic", user_id=1)

        assert len(ctx_epi.long_term_facts) == 1
        assert ctx_epi.long_term_facts[0]["content"] == "episodic"
        assert len(ctx_sem.long_term_facts) == 1
        assert ctx_sem.long_term_facts[0]["content"] == "semantic"

    @pytest.mark.asyncio
    async def test_search_facts_respects_user_id(self):
        repo = FakeRepository()
        svc = _make_svc(repo=repo)

        async def fake_embed(texts):
            return [[0.5] * 10 for _ in texts]

        svc._vector.embed = fake_embed

        await svc.store_fact("th1", "alice's fact", user_id=1)
        await svc.store_fact("th1", "bob's fact", user_id=2)

        alice = await svc.search_facts("th1", "fact", user_id=1)
        bob = await svc.search_facts("th1", "fact", user_id=2)

        assert len(alice) == 1
        assert alice[0]["content"] == "alice's fact"
        assert len(bob) == 1
        assert bob[0]["content"] == "bob's fact"


class TestRetention:
    """Per-kind retention limits."""

    @pytest.mark.asyncio
    async def test_episodic_retention_enforced(self):
        repo = FakeRepository()
        svc = _make_svc(repo=repo)
        svc.max_facts = 2
        _unique_embed = _make_unique_embed()
        svc._vector.embed = _unique_embed

        for i in range(3):
            await svc.store_fact("th1", f"fact-{i}", importance=0.1, user_id=1)

        # With max_facts=2, only 2 survive (evict lowest (importance, age) first).
        facts = await repo.get_facts("th1", user_id=1)
        assert len(facts) == 2

    @pytest.mark.asyncio
    async def test_extraction_failure_returns_zero(self):
        """Extraction failure returns 0 and does not fail the caller."""
        svc = _make_svc()

        # No checkpointer — extraction returns 0 rather than crashing.
        count = await svc.extract_and_store_facts("th1")
        assert count == 0

    @pytest.mark.asyncio
    async def test_extracted_facts_are_semantic_and_user_scoped(self):
        repo = FakeRepository()
        svc = _make_svc(
            repo=repo,
            extractor=FakeExtractor([
                {"content": "likes science fiction", "importance": 0.8}
            ]),
        )
        svc._vector.embed = _make_unique_embed()

        count = await svc.extract_and_store_facts("th1", user_id=7)

        assert count == 1
        stored = await repo.get_facts(
            "th1", user_id=7, kind="semantic"
        )
        assert [fact["content"] for fact in stored] == [
            "likes science fiction"
        ]

    @pytest.mark.asyncio
    async def test_anonymous_extraction_does_not_create_durable_memory(self):
        repo = FakeRepository()
        svc = _make_svc(
            repo=repo,
            extractor=FakeExtractor([{"content": "private fact"}]),
        )

        count = await svc.extract_and_store_facts("th1", user_id=None)

        assert count == 0
        assert repo._store == {}

    @pytest.mark.asyncio
    async def test_concurrent_inserts_preserve_capacity(self):
        class DelayedRepository(FakeRepository):
            async def get_facts(self, *args, **kwargs):
                facts = await super().get_facts(*args, **kwargs)
                await asyncio.sleep(0.02)
                return facts

        repo = DelayedRepository()
        svc = _make_svc(repo=repo)
        svc.max_facts = 1
        svc._vector.embed = _make_unique_embed()

        await asyncio.gather(
            svc.store_fact("th1", "first", user_id=1),
            svc.store_fact("th1", "second", user_id=1),
        )

        facts = await repo.get_facts("th1", user_id=1, kind="episodic")
        assert len(facts) == 1


class TestServiceContract:
    """MemoryServiceImpl satisfies MemoryService contract."""

    @pytest.mark.asyncio
    async def test_implements_memory_service(self):
        svc = _make_svc()
        assert isinstance(svc, MemoryService)

    @pytest.mark.asyncio
    async def test_retrieve_context_no_checkpointer(self):
        svc = _make_svc()
        ctx = await svc.retrieve_context("th1", "query")
        assert isinstance(ctx, MemoryContext)
        assert ctx.short_term_messages == []
        assert ctx.long_term_facts == []

    @pytest.mark.asyncio
    async def test_search_facts_empty_repo(self):
        svc = _make_svc()
        results = await svc.search_facts("th1", "query")
        assert results == []

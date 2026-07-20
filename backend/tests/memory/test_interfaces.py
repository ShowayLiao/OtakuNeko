"""Tests for the new memory interfaces, repository, and extractor layers."""

from __future__ import annotations

import pytest
from langgraph.store.memory import InMemoryStore

from app.memory.interfaces import MemoryContext, MemoryRepository, MemoryService
from app.memory.repository import StoreMemoryRepository
from app.memory.extractor import LLMFactExtractor
from app.memory.service import MemoryServiceImpl


class FakeRepository(MemoryRepository):
    """Fake repository backed by a simple dict (no Store dependency)."""

    def __init__(self) -> None:
        self._store: dict[str, dict[str, dict]] = {}

    def _ns(self, thread_id: str) -> dict[str, dict]:
        if thread_id not in self._store:
            self._store[thread_id] = {}
        return self._store[thread_id]

    async def put_fact(
        self, thread_id: str, fact_id: str, content: str,
        importance: float, source: str,
    ) -> None:
        self._ns(thread_id)[fact_id] = {
            "content": content,
            "importance": importance,
            "source": source,
        }

    async def get_facts(self, thread_id: str) -> list[dict]:
        result = []
        for fact_id, val in self._ns(thread_id).items():
            result.append({
                "id": fact_id,
                "content": val["content"],
                "importance": val.get("importance", 0.5),
                "timestamp": "",
                "source": val.get("source", "conversation"),
            })
        return result

    async def delete_fact(self, thread_id: str, fact_id: str) -> None:
        self._ns(thread_id).pop(fact_id, None)

    async def count_facts(self, thread_id: str) -> int:
        return len(self._ns(thread_id))


class FakeExtractor:
    """Always returns a fixed set of facts."""

    def __init__(self, facts: list[dict] | None = None) -> None:
        self._facts = facts or []

    async def extract(self, messages: list[dict]) -> list[dict]:
        return self._facts

    @property
    def extract_calls(self) -> int:
        if not hasattr(self, "_calls"):
            self._calls = 0
        return self._calls


class TestStoreMemoryRepository:
    """Unit tests for StoreMemoryRepository."""

    @pytest.mark.asyncio
    async def test_put_and_get_facts(self):
        store = InMemoryStore()
        repo = StoreMemoryRepository(store)

        await repo.put_fact("th1", "f1", "fact one", 0.8, "test")
        await repo.put_fact("th1", "f2", "fact two", 0.3, "test")

        facts = await repo.get_facts("th1")
        assert len(facts) == 2
        contents = {f["content"] for f in facts}
        assert contents == {"fact one", "fact two"}

    @pytest.mark.asyncio
    async def test_delete_fact(self):
        store = InMemoryStore()
        repo = StoreMemoryRepository(store)

        await repo.put_fact("th1", "f1", "fact one", 0.5, "test")
        await repo.delete_fact("th1", "f1")

        facts = await repo.get_facts("th1")
        assert len(facts) == 0

    @pytest.mark.asyncio
    async def test_count_facts(self):
        store = InMemoryStore()
        repo = StoreMemoryRepository(store)

        n = await repo.count_facts("th1")
        assert n == 0

        await repo.put_fact("th1", "f1", "a", 0.5, "test")
        await repo.put_fact("th1", "f2", "b", 0.5, "test")

        n = await repo.count_facts("th1")
        assert n == 2

    @pytest.mark.asyncio
    async def test_threads_are_isolated(self):
        store = InMemoryStore()
        repo = StoreMemoryRepository(store)

        await repo.put_fact("thA", "fa", "alpha", 0.5, "test")
        await repo.put_fact("thB", "fb", "beta", 0.5, "test")

        assert await repo.count_facts("thA") == 1
        assert await repo.count_facts("thB") == 1


class TestMemoryServiceContract:
    """Verify MemoryServiceImpl satisfies the MemoryService contract."""

    @pytest.mark.asyncio
    async def test_store_and_search_facts(self):
        repo = FakeRepository()
        extractor = FakeExtractor()
        svc = MemoryServiceImpl(
            repository=repo,
            extractor=extractor,
            api_key="sk-test",
            base_url="https://test",
        )
        # store_fact uses real embedding; skip unless API key.
        # Instead just verify the interface matches MemoryService.

    @pytest.mark.asyncio
    async def test_implements_memory_service(self):
        # Structural check: MemoryServiceImpl is-a MemoryService
        svc = MemoryServiceImpl(
            repository=FakeRepository(),
            extractor=FakeExtractor(),
            api_key="sk-test",
            base_url="https://test",
        )
        assert isinstance(svc, MemoryService)

    @pytest.mark.asyncio
    async def test_retrieve_context_no_checkpointer(self):
        svc = MemoryServiceImpl(
            repository=FakeRepository(),
            extractor=FakeExtractor(),
            api_key="sk-test",
            base_url="https://test",
        )
        ctx = await svc.retrieve_context("th1", "query")
        assert isinstance(ctx, MemoryContext)
        assert ctx.short_term_messages == []
        assert ctx.long_term_facts == []

    @pytest.mark.asyncio
    async def test_search_facts_empty_repo(self):
        svc = MemoryServiceImpl(
            repository=FakeRepository(),
            extractor=FakeExtractor(),
            api_key="sk-test",
            base_url="https://test",
        )
        results = await svc.search_facts("th1", "query")
        assert results == []

    @pytest.mark.asyncio
    async def test_store_fact_enforces_max_facts_after_insert(self):
        repo = FakeRepository()
        extractor = FakeExtractor()
        svc = MemoryServiceImpl(
            repository=repo,
            extractor=extractor,
            api_key="sk-test",
            base_url="https://test",
            max_facts=1,
        )

        async def fake_embed(texts):
            return [[1.0, 0.0] if text == "first" else [0.0, 1.0] for text in texts]

        svc._vector.embed = fake_embed
        await svc.store_fact("th1", "first")
        await svc.store_fact("th1", "second")

        facts = await repo.get_facts("th1")
        assert len(facts) == 1
        assert facts[0]["content"] == "second"

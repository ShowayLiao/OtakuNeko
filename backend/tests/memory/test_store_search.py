import pytest
from unittest.mock import AsyncMock, patch
from langgraph.store.memory import InMemoryStore
from app.memory.manager import MemoryManager


class TestStoreSearch:
    """Phase D — Store.asearch 语义搜索测试"""

    @pytest.mark.asyncio
    async def test_search_returns_matching_facts(self):
        store = InMemoryStore()
        await store.aput(("facts", "thread-1"), "k1", {"content": "喜欢科幻", "importance": 0.9, "timestamp": "2025", "embedding": [0.1] * 1536, "source": "conv"})
        await store.aput(("facts", "thread-1"), "k2", {"content": "讨厌恐怖片", "importance": 0.7, "timestamp": "2025", "embedding": [0.2] * 1536, "source": "conv"})

        items = await store.asearch(("facts", "thread-1"))
        assert len(items) == 2

    @pytest.mark.asyncio
    async def test_search_on_empty_namespace_returns_empty(self):
        store = InMemoryStore()
        items = await store.asearch(("facts", "ghost-thread"))
        assert items == []

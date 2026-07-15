import pytest
from unittest.mock import AsyncMock, patch
from langgraph.store.memory import InMemoryStore
from app.memory.manager import MemoryManager, MemoryContext


class MockMessage:
    def __init__(self, msg_type, content):
        self.type = msg_type
        self.content = content


def _make_checkpoint(messages):
    class FakeCheckpoint:
        pass
    cp = FakeCheckpoint()
    cp.checkpoint = {"channel_values": {"messages": messages}}
    return cp


def _mock_embed():
    return patch.object(
        MemoryManager, "_get_facts",
        new=AsyncMock(return_value=[])
    )


class TestMemoryManagerPhaseBC:
    """Phase B+C — ShortTermMemory 下线 + Store 迁入后 MemoryManager 测试"""

    @pytest.mark.asyncio
    async def test_load_context_from_checkpoint_returns_messages(self):
        checkpointer = AsyncMock()
        messages = [MockMessage("human", "你好"), MockMessage("ai", "你好！")]
        checkpointer.aget_tuple = AsyncMock(return_value=_make_checkpoint(messages))

        store = InMemoryStore()
        mgr = MemoryManager(api_key="sk-test", base_url="https://test",
                            checkpointer=checkpointer, store=store)

        ctx = await mgr.load_context("thread-1", "继续聊天")
        assert isinstance(ctx, MemoryContext)
        assert len(ctx.short_term_messages) == 2
        assert "近期对话" in ctx.summary

    @pytest.mark.asyncio
    async def test_load_context_nonexistent_thread_returns_empty(self):
        checkpointer = AsyncMock()
        checkpointer.aget_tuple = AsyncMock(return_value=None)

        store = InMemoryStore()
        mgr = MemoryManager(api_key="sk-test", base_url="https://test",
                            checkpointer=checkpointer, store=store)

        ctx = await mgr.load_context("ghost-thread", "随便聊聊")
        assert ctx.short_term_messages == []
        assert ctx.summary == ""

    @pytest.mark.asyncio
    async def test_load_context_injects_long_term_facts_from_store(self):
        checkpointer = AsyncMock()
        messages = [MockMessage("human", "我喜欢科幻片")]
        checkpointer.aget_tuple = AsyncMock(return_value=_make_checkpoint(messages))

        store = InMemoryStore()
        await store.aput(("facts", "thread-facts"), "fact-1",
                         {"content": "用户偏好科幻类型", "importance": 0.9,
                          "timestamp": "2025-01-01", "source": "conversation",
                          "embedding": [0.1] * 1536})
        await store.aput(("facts", "thread-facts"), "fact-2",
                         {"content": "用户喜欢宫崎骏", "importance": 0.7,
                          "timestamp": "2025-01-02", "source": "conversation",
                          "embedding": [0.2] * 1536})

        mgr = MemoryManager(api_key="sk-test", base_url="https://test",
                            checkpointer=checkpointer, store=store)

        with patch.object(mgr.hybrid, "retrieve", new=AsyncMock(return_value=[
            {"content": "用户偏好科幻类型", "importance": 0.9}
        ])):
            ctx = await mgr.load_context("thread-facts", "推荐动画")
            assert len(ctx.long_term_facts) >= 1

    @pytest.mark.asyncio
    async def test_load_context_without_store_returns_empty_facts(self):
        checkpointer = AsyncMock()
        messages = [MockMessage("human", "hello")]
        checkpointer.aget_tuple = AsyncMock(return_value=_make_checkpoint(messages))

        mgr = MemoryManager(api_key="sk-test", base_url="https://test",
                            checkpointer=checkpointer, store=None)

        ctx = await mgr.load_context("no-store-thread", "查询")
        assert ctx.short_term_messages != []
        assert ctx.long_term_facts == []

    @pytest.mark.asyncio
    async def test_add_and_retrieve_fact_via_store(self):
        store = InMemoryStore()
        mgr = MemoryManager(api_key="sk-test", base_url="https://test",
                            store=store)

        with patch.object(mgr.vector, "embed", new=AsyncMock(return_value=[[0.0] * 1536])):
            fact_id = await mgr._add_fact("thread-add", "用户喜欢Python", importance=0.8)
            assert fact_id is not None

        facts = await mgr._get_facts("thread-add")
        assert len(facts) == 1
        assert facts[0]["content"] == "用户喜欢Python"
        assert facts[0]["importance"] == 0.8

    @pytest.mark.asyncio
    async def test_extract_and_store_facts_without_store_returns_zero(self):
        checkpointer = AsyncMock()
        messages = [MockMessage("human", f"msg{i}") for i in range(10)]
        checkpointer.aget_tuple = AsyncMock(return_value=_make_checkpoint(messages))

        mgr = MemoryManager(api_key="sk-test", base_url="https://test",
                            checkpointer=checkpointer, store=None)

        count = await mgr.extract_and_store_facts("thread-no-store")
        assert count == 0

import pytest
from unittest.mock import AsyncMock, patch
from app.memory.manager import MemoryManager


class MockMessage:
    def __init__(self, msg_type, content):
        self.type = msg_type
        self.content = content


def _make_checkpoint(messages, completed_steps=None, last_terminal_output=""):
    class FakeCheckpoint:
        pass

    cp = FakeCheckpoint()
    cp.checkpoint = {
        "channel_values": {
            "messages": messages,
            "completed_steps": completed_steps or [],
            "last_terminal_output": last_terminal_output,
        }
    }
    return cp


class TestMemoryLogging:
    """Phase D — 内存模块日志输出测试"""

    @pytest.mark.asyncio
    async def test_load_context_logs_thread_info(self):
        with patch("app.memory.manager.logger") as mock_logger:
            checkpointer = AsyncMock()
            checkpointer.aget_tuple = AsyncMock(
                return_value=_make_checkpoint(
                    [MockMessage("human", "hello")],
                    completed_steps=["step-1"],
                )
            )

            mgr = MemoryManager(
                api_key="sk-test",
                base_url="https://test",
                checkpointer=checkpointer,
                store=None,
            )

            with patch.object(mgr, "_get_facts", new=AsyncMock(return_value=[])):
                await mgr.load_context("log-thread", "test query")

            assert mock_logger.info.called

    @pytest.mark.asyncio
    async def test_context_includes_completed_steps_in_summary(self):
        checkpointer = AsyncMock()
        checkpointer.aget_tuple = AsyncMock(
            return_value=_make_checkpoint(
                [MockMessage("human", "hi")],
                completed_steps=["search_bangumi", "fetch_reviews"],
                last_terminal_output="Found 42 results",
            )
        )

        mgr = MemoryManager(
            api_key="sk-test",
            base_url="https://test",
            checkpointer=checkpointer,
            store=None,
        )

        with patch.object(mgr, "_get_facts", new=AsyncMock(return_value=[])):
            ctx = await mgr.load_context("ctx-thread", "query")

        assert "[执行进度]" in ctx.summary
        assert "search_bangumi" in ctx.summary
        assert "[终端输出]" in ctx.summary
        assert "Found 42 results" in ctx.summary

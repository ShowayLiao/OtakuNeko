"""Tests for AGENT-001: LangGraphAdapter."""

import pytest

from app.agents.base import BaseAgent
from app.agents.langgraph_adapter import LangGraphAdapter


class FakeChatWorkflow:
    """Fake ChatWorkflow that yields the same event shape as the real one."""

    def __init__(self):
        self.last_kwargs = None

    async def stream_chat(self, **kwargs):
        self.last_kwargs = kwargs
        yield {"type": "thinking_start"}
        yield {"type": "message_chunk", "content": "Hello "}
        yield {"type": "message_chunk", "content": "World"}
        yield {"type": "message_end"}


class TestLangGraphAdapter:
    @pytest.fixture
    def adapter(self):
        return LangGraphAdapter(FakeChatWorkflow())

    def test_is_base_agent(self, adapter):
        assert isinstance(adapter, BaseAgent)

    def test_exposes_workflow(self, adapter):
        assert isinstance(adapter.workflow, FakeChatWorkflow)

    @pytest.mark.asyncio
    async def test_execute_collects_chunks(self, adapter):
        result = await adapter.execute(FakeTaskStub())
        assert result["text"] == "Hello World"
        assert len(result["all_events"]) == 4

    @pytest.mark.asyncio
    async def test_execute_forwards_prompt_and_provider_options(self, adapter):
        task = FakeTaskStub(
            metadata={
                "model": "deepseek-chat",
                "messages": [{"role": "user", "content": "hello"}],
                "temperature": 0.2,
                "thread_id": "thread-1",
                "speak_prompt": "Answer concisely",
                "deepseek_options": {"thinking": True, "reasoning_effort": "high"},
            }
        )

        await adapter.execute(task)

        assert adapter.workflow.last_kwargs["speak_prompt"] == "Answer concisely"
        assert adapter.workflow.last_kwargs["deepseek_options"]["thinking"] is True

    @pytest.mark.asyncio
    async def test_execute_with_tool_calls(self):
        class WorkflowWithTool:
            async def stream_chat(self, **kwargs):
                yield {"type": "tool_call_end", "name": "search",
                       "output": {"data": "result"}, "status": "success"}

        adapter = LangGraphAdapter(WorkflowWithTool())
        result = await adapter.execute(FakeTaskStub())
        assert len(result["tool_calls"]) == 1
        assert result["tool_calls"][0]["name"] == "search"

    @pytest.mark.asyncio
    async def test_plan_returns_structured_plan(self, adapter):
        plan = await adapter.plan(FakeTaskStub(goal="find anime"))
        assert plan["goal"] == "find anime"
        assert len(plan["steps"]) == 3

    @pytest.mark.asyncio
    async def test_reflect_returns_observations(self, adapter):
        reflection = await adapter.reflect(None, "some result")
        assert reflection["goal_achieved"] is True


class FakeTaskStub:
    """Minimal task stub matching the shape the adapter reads."""

    def __init__(self, goal="test goal", metadata=None):
        self.goal = goal
        self.metadata = metadata or {
            "model": "fake-model",
            "messages": [{"role": "user", "content": goal}],
            "thread_id": "test-thread",
        }

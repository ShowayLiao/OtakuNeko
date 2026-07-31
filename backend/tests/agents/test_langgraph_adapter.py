"""Tests for AGENT-001: LangGraphAdapter."""

import pytest

from app.agents.base import BaseAgent
from app.agents.langgraph_adapter import (
    LangGraphAdapter,
    adapt_langgraph_event,
    adapt_langgraph_events,
)


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


def test_adapt_langgraph_event_redacts_raw_tool_output_and_error_detail():
    tool_event = adapt_langgraph_event(
        {
            "type": "tool_call_end",
            "id": "tool-1",
            "name": "anime.search",
            "output": {"secret": "do-not-publish"},
            "status": "success",
        },
        run_id="run-1",
        sequence=3,
    )
    error_event = adapt_langgraph_event(
        {"type": "error", "detail": "raw provider secret"},
        run_id="run-1",
        sequence=4,
    )

    assert tool_event is not None
    assert tool_event.event_type == "tool_call_end"
    assert tool_event.invocation_id == "tool-1"
    assert "secret" not in str(tool_event.payload)
    assert error_event is not None
    assert error_event.payload == {"error_code": "permanent"}
    assert "raw provider secret" not in str(error_event.payload)


def test_adapt_langgraph_events_assigns_stable_sequences_and_ids():
    events = list(
        adapt_langgraph_events(
            [
                {"type": "thinking_start"},
                {"type": "tool_call_start", "id": "tool-1", "name": "search", "inputs": {"q": "x"}},
                {"type": "message_chunk", "content": "answer"},
                {"type": "unknown", "ignored": True},
                {"type": "message_end"},
            ],
            run_id="run-1",
        )
    )

    assert [event.sequence for event in events] == [1, 2, 3, 4]
    assert [event.event_type for event in events] == [
        "thinking_start",
        "tool_call_start",
        "message_chunk",
        "message_end",
    ]
    assert events[1].invocation_id == "tool-1"
    assert events[2].payload == {"content": "answer"}


class FakeTaskStub:
    """Minimal task stub matching the shape the adapter reads."""

    def __init__(self, goal="test goal", metadata=None):
        self.goal = goal
        self.metadata = metadata or {
            "model": "fake-model",
            "messages": [{"role": "user", "content": goal}],
            "thread_id": "test-thread",
        }

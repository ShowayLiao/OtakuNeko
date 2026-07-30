"""Deterministic end-to-end scenarios for the V3 runtime boundary."""

from __future__ import annotations

import pytest

from app.harness.runtime import AgentRuntime
from app.harness.task import AgentTask
from app.trace import TraceEventType
from app.trace.store import InMemoryTraceStore


class StubAdapter:
    async def run(self, state):
        return {"text": "ok"}

    async def stream(self, state, **kwargs):
        yield {"type": "message_chunk", "content": "hello"}
        yield {"type": "message_end"}


class FailingAdapter:
    async def run(self, state):
        raise RuntimeError("adapter failed")


def _event_types(trace) -> set[TraceEventType]:
    return {
        event.event_type
        for step in trace.steps
        for event in step.events
    }


class TestAcceptance:
    """Runtime scenarios that cross task, state, adapter, and trace layers."""

    @pytest.mark.asyncio
    async def test_execute_records_completed_runtime_lifecycle(self):
        store = InMemoryTraceStore()
        runtime = AgentRuntime(StubAdapter(), trace_store=store)

        state = await runtime.execute(
            AgentTask(user_id=1, goal="推荐动漫")
        )

        assert state.status == "completed"
        assert state.result == {"text": "ok"}
        [trace] = await store.list_recent(limit=1, user_id=1)
        assert trace.status == "completed"
        assert trace.user_id == 1
        assert {
            TraceEventType.NODE_START,
            TraceEventType.NODE_END,
        } <= _event_types(trace)

    @pytest.mark.asyncio
    async def test_execute_failure_records_failed_runtime_lifecycle(self):
        store = InMemoryTraceStore()
        runtime = AgentRuntime(FailingAdapter(), trace_store=store)

        with pytest.raises(RuntimeError, match="adapter failed"):
            await runtime.execute(
                AgentTask(user_id=1, goal="failing task")
            )

        [trace] = await store.list_recent(limit=1, user_id=1)
        assert trace.status == "failed"
        assert {
            TraceEventType.FAILURE,
            TraceEventType.NODE_END,
        } <= _event_types(trace)

    @pytest.mark.asyncio
    async def test_trace_queries_are_user_isolated(self):
        store = InMemoryTraceStore()
        runtime = AgentRuntime(StubAdapter(), trace_store=store)
        await runtime.execute(AgentTask(user_id=1, goal="user1 task"))

        assert await store.list_recent(limit=10, user_id=2) == []

    @pytest.mark.asyncio
    async def test_streaming_records_completed_runtime_lifecycle(self):
        store = InMemoryTraceStore()
        runtime = AgentRuntime(StubAdapter(), trace_store=store)

        chunks = [
            chunk
            async for chunk in runtime.stream(
                AgentTask(user_id=1, goal="stream")
            )
        ]

        assert chunks == [
            {"type": "message_chunk", "content": "hello"},
            {"type": "message_end"},
        ]
        [trace] = await store.list_recent(limit=1, user_id=1)
        assert trace.status == "completed"
        assert {
            TraceEventType.NODE_START,
            TraceEventType.NODE_END,
        } <= _event_types(trace)

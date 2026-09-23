"""Tests for the agent trace system."""

from __future__ import annotations

import json
import pytest

from app.trace import AgentTrace, TraceStep, TraceEvent
from app.trace.store import InMemoryTraceStore
from app.harness.runtime import AgentRuntime
from app.harness.task import AgentTask


class TestTraceModels:
    """Unit tests for trace data models."""

    def test_agent_trace_creation(self):
        trace = AgentTrace(
            task_id=1,
            user_id=42,
            agent_name="AgentRuntime",
            goal="Find me an anime",
        )
        assert trace.trace_id is not None
        assert len(trace.trace_id) == 32
        assert trace.task_id == 1
        assert trace.user_id == 42
        assert trace.status == "running"
        assert trace.steps == []
        assert trace.error is None

    def test_mark_completed(self):
        trace = AgentTrace()
        trace.mark_completed()
        assert trace.status == "completed"
        assert trace.completed_at is not None
        assert trace.total_duration_ms is not None

    def test_mark_failed(self):
        trace = AgentTrace()
        trace.mark_failed("timeout")
        assert trace.status == "failed"
        assert trace.error == "timeout"
        assert trace.completed_at is not None

    def test_add_step(self):
        trace = AgentTrace()
        step = TraceStep(
            step_index=0,
            step_label="execute",
            agent_name="TestAgent",
        )
        trace.add_step(step)
        assert len(trace.steps) == 1
        assert trace.steps[0].step_label == "execute"

    def test_serializable_to_json(self):
        trace = AgentTrace(task_id=5, goal="test")
        trace.mark_completed()
        data = trace.model_dump(mode="json")
        # Round-trip through JSON
        reloaded = json.loads(json.dumps(data))
        assert reloaded["task_id"] == 5
        assert reloaded["status"] == "completed"

    def test_trace_step_complete(self):
        step = TraceStep(step_index=1, step_label="think", agent_name="T")
        assert step.status == "running"
        step.complete()
        assert step.status == "completed"
        assert step.completed_at is not None

    def test_trace_step_fail(self):
        step = TraceStep(step_index=1, step_label="think", agent_name="T")
        step.fail("bad tool call")
        assert step.status == "failed"

    def test_trace_event(self):
        evt = TraceEvent(
            event_type="tool_call_start",
            data={"name": "search", "args": {}},
        )
        assert evt.event_type == "tool_call_start"
        assert evt.timestamp is not None


class TestInMemoryTraceStore:
    """Unit tests for the in-memory trace store."""

    @pytest.mark.asyncio
    async def test_record_and_query(self):
        store = InMemoryTraceStore()
        trace = AgentTrace(task_id=1, goal="test")
        await store.record(trace)

        found = await store.query(trace.trace_id)
        assert found is not None
        assert found.task_id == 1

    @pytest.mark.asyncio
    async def test_query_missing_returns_none(self):
        store = InMemoryTraceStore()
        found = await store.query("nonexistent")
        assert found is None

    @pytest.mark.asyncio
    async def test_list_recent_orders_by_time(self):
        store = InMemoryTraceStore()
        t1 = AgentTrace(task_id=1, goal="first")
        await store.record(t1)
        # Force a small delay so timestamps differ
        import asyncio

        await asyncio.sleep(0.01)
        t2 = AgentTrace(task_id=2, goal="second")
        await store.record(t2)

        recent = await store.list_recent(limit=10)
        assert len(recent) == 2
        assert recent[0].task_id == 2  # Most recent first

    @pytest.mark.asyncio
    async def test_list_recent_filters_by_user(self):
        store = InMemoryTraceStore()
        await store.record(AgentTrace(task_id=1, user_id=10, goal="u10"))
        await store.record(AgentTrace(task_id=2, user_id=20, goal="u20"))

        recent = await store.list_recent(limit=10, user_id=10)
        assert len(recent) == 1
        assert recent[0].user_id == 10

    @pytest.mark.asyncio
    async def test_max_traces_enforced(self):
        store = InMemoryTraceStore(max_traces=2)
        await store.record(AgentTrace(task_id=1))
        await store.record(AgentTrace(task_id=2))
        await store.record(AgentTrace(task_id=3))

        recent = await store.list_recent(limit=10)
        assert len(recent) == 2

    @pytest.mark.asyncio
    async def test_evicts_oldest(self):
        store = InMemoryTraceStore(max_traces=2)
        t1 = AgentTrace(task_id=1, goal="oldest")
        await store.record(t1)
        await store.record(AgentTrace(task_id=2))

        recent = await store.list_recent(limit=10)
        assert len(recent) <= 2

        class FakeAdapter:
            async def run(self, state):
                return {"text": "ok"}

        runtime = AgentRuntime(FakeAdapter())
        # Default: no trace store
        assert runtime.trace_store is None
        assert runtime.adapter_name == "FakeAdapter"

    @pytest.mark.asyncio
    async def test_execute_with_trace_store(self):
        class FakeAdapter:
            async def run(self, state):
                return {"text": "hello"}

        trace_store = InMemoryTraceStore()
        runtime = AgentRuntime(FakeAdapter(), trace_store=trace_store)

        task = AgentTask(user_id=1, goal="say hello")
        state = await runtime.execute(task)

        assert state.status == "completed"

        # Trace should have been recorded
        recent = await trace_store.list_recent(limit=1)
        assert len(recent) == 1
        trace = recent[0]
        assert trace.user_id == 1
        assert trace.goal == "[REDACTED]"
        assert trace.status == "completed"

    @pytest.mark.asyncio
    async def test_execute_failure_records_trace(self):
        class FailingAdapter:
            async def run(self, state):
                raise RuntimeError("boom")

        trace_store = InMemoryTraceStore()
        runtime = AgentRuntime(FailingAdapter(), trace_store=trace_store)

        task = AgentTask(user_id=1, goal="will fail")
        with pytest.raises(RuntimeError):
            await runtime.execute(task)

        recent = await trace_store.list_recent(limit=1)
        assert len(recent) == 1
        trace = recent[0]
        assert trace.status == "failed"
        assert trace.error is not None

    @pytest.mark.asyncio
    async def test_execute_without_trace_store_no_overhead(self):
        class FakeAdapter:
            async def run(self, state):
                return {"text": "ok"}

        runtime = AgentRuntime(FakeAdapter())  # No trace_store

        task = AgentTask(user_id=1, goal="no trace")
        state = await runtime.execute(task)
        assert state.status == "completed"

    @pytest.mark.asyncio
    async def test_adapter_name_derived_from_class(self):
        class MyAgentAdapter:
            async def run(self, state):
                return {}

        runtime = AgentRuntime(MyAgentAdapter())
        assert runtime.adapter_name == "MyAgentAdapter"

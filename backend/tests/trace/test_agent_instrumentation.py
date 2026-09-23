"""Tests for TRACE-002 Step 02: runtime instrumentation and Step 03: boundary spans."""

from __future__ import annotations

import asyncio
import pytest

from app.trace.store import InMemoryTraceStore
from app.harness.runtime import AgentRuntime
from app.harness.task import AgentTask


class TestRuntimeInstrumentation:
    """TRACE-002 Step 02: Runtime emits trace events for start/end/failure."""

    @pytest.mark.asyncio
    async def test_successful_execution_records_trace(self):
        class FakeAdapter:
            async def run(self, state):
                return {"text": "ok"}

        store = InMemoryTraceStore()
        runtime = AgentRuntime(FakeAdapter(), trace_store=store)
        task = AgentTask(user_id=1, goal="test")
        state = await runtime.execute(task)

        assert state.status == "completed"
        recent = await store.list_recent(limit=1)
        assert len(recent) == 1
        assert recent[0].status == "completed"

    @pytest.mark.asyncio
    async def test_failed_execution_records_failed_trace(self):
        class FailingAdapter:
            async def run(self, state):
                raise RuntimeError("service down")

        store = InMemoryTraceStore()
        runtime = AgentRuntime(FailingAdapter(), trace_store=store)
        task = AgentTask(user_id=1, goal="fail")

        with pytest.raises(RuntimeError):
            await runtime.execute(task)

        recent = await store.list_recent(limit=1)
        assert len(recent) == 1
        assert recent[0].status == "failed"

    @pytest.mark.asyncio
    async def test_stream_failure_records_trace(self):
        class FailingStreamAdapter:
            async def stream(self, state, **kwargs):
                yield {"type": "message_chunk", "content": "hello"}
                raise RuntimeError("stream error")

        store = InMemoryTraceStore()
        runtime = AgentRuntime(FailingStreamAdapter(), trace_store=store)
        task = AgentTask(user_id=1, goal="fail stream")

        with pytest.raises(RuntimeError):
            async for _ in runtime.stream(task):
                pass

        recent = await store.list_recent(limit=1)
        assert len(recent) == 1

    @pytest.mark.asyncio
    async def test_no_trace_store_no_overhead(self):
        class FakeAdapter:
            async def run(self, state):
                return {"text": "ok"}

        runtime = AgentRuntime(FakeAdapter())
        task = AgentTask(user_id=1, goal="no trace")
        state = await runtime.execute(task)
        assert state.status == "completed"

    @pytest.mark.asyncio
    async def test_execution_records_step_events(self):
        class StepRecordingAdapter:
            async def run(self, state):
                return {"text": "done", "tool_calls": [{"name": "search"}]}

        store = InMemoryTraceStore()
        runtime = AgentRuntime(StepRecordingAdapter(), trace_store=store)
        task = AgentTask(user_id=1, goal="step test")
        await runtime.execute(task)

        recent = await store.list_recent(limit=1)
        assert len(recent) == 1
        trace = recent[0]
        assert any(s.step_label == "scheduled_context" for s in trace.steps)

    @pytest.mark.asyncio
    async def test_storage_failure_does_not_replace_success(self):
        class FakeAdapter:
            async def run(self, state):
                return {"text": "ok"}

        class FailingStore:
            async def record(self, trace):
                raise RuntimeError("database unavailable")

        runtime = AgentRuntime(FakeAdapter(), trace_store=FailingStore())
        state = await runtime.execute(AgentTask(user_id=1, goal="test"))
        assert state.status == "completed"
        assert state.result == {"text": "ok"}

    @pytest.mark.asyncio
    async def test_storage_failure_does_not_replace_agent_error(self):
        class FailingAdapter:
            async def run(self, state):
                raise ValueError("original agent error")

        class FailingStore:
            async def record(self, trace):
                raise RuntimeError("database unavailable")

        runtime = AgentRuntime(FailingAdapter(), trace_store=FailingStore())
        with pytest.raises(ValueError, match="original agent error"):
            await runtime.execute(AgentTask(user_id=1, goal="test"))

    @pytest.mark.asyncio
    async def test_cancelled_stream_records_cancelled_terminal_state(self):
        started = asyncio.Event()

        class SlowAdapter:
            async def stream(self, state, **kwargs):
                started.set()
                while True:
                    await asyncio.sleep(1)
                    yield {"type": "message_chunk", "content": "private"}

        store = InMemoryTraceStore()
        runtime = AgentRuntime(SlowAdapter(), trace_store=store)

        async def consume():
            async for _ in runtime.stream(AgentTask(user_id=1, goal="private")):
                pass

        consumer = asyncio.create_task(consume())
        await started.wait()
        consumer.cancel()
        with pytest.raises(asyncio.CancelledError):
            await consumer

        traces = await store.list_recent(limit=1, user_id=1)
        assert traces[0].status == "cancelled"
        assert any(
            event.status == "cancelled"
            for step in traces[0].steps
            for event in step.events
        )

    @pytest.mark.asyncio
    async def test_cancelled_execution_records_cancelled_terminal_state(self):
        started = asyncio.Event()

        class SlowAdapter:
            async def run(self, state):
                started.set()
                await asyncio.sleep(60)

        store = InMemoryTraceStore()
        runtime = AgentRuntime(SlowAdapter(), trace_store=store)
        execution = asyncio.create_task(
            runtime.execute(AgentTask(user_id=1, goal="private"))
        )
        await started.wait()
        execution.cancel()

        with pytest.raises(asyncio.CancelledError):
            await execution

        traces = await store.list_recent(limit=1, user_id=1)
        assert traces[0].status == "cancelled"

    @pytest.mark.asyncio
    async def test_closed_stream_records_cancelled_events(self):
        class Adapter:
            async def stream(self, state, **kwargs):
                yield {"type": "message_chunk", "content": "private"}
                await asyncio.sleep(60)

        class RecordingCheckpointStore:
            def __init__(self):
                self.statuses = []

            async def save_state(self, state):
                self.statuses.append(state.status)

            async def load_state(self, task_id):
                return None

        store = InMemoryTraceStore()
        checkpoints = RecordingCheckpointStore()
        runtime = AgentRuntime(
            Adapter(),
            checkpoint_store=checkpoints,
            trace_store=store,
        )
        stream = runtime.stream(AgentTask(task_id=99, user_id=1, goal="private"))

        await anext(stream)
        await stream.aclose()

        traces = await store.list_recent(limit=1, user_id=1)
        assert traces[0].status == "cancelled"
        terminal_events = [
            event
            for step in traces[0].steps
            for event in step.events
            if event.event_type == "node_end"
        ]
        assert terminal_events[-1].status == "cancelled"
        assert checkpoints.statuses[-1] == "cancelled"

    @pytest.mark.asyncio
    async def test_stream_projection_assigns_shared_run_ids_and_sequences(self):
        class RoutingStreamAdapter:
            async def stream(self, state, **kwargs):
                yield {
                    "type": "route_decision",
                    "route": "chat",
                    "agent": "chat",
                    "confidence": 1.0,
                }
                yield {
                    "type": "agent_result",
                    "agent": "chat",
                    "kind": "subagent",
                    "result": {"status": "completed", "data": {}},
                }

        store = InMemoryTraceStore()
        runtime = AgentRuntime(RoutingStreamAdapter(), trace_store=store)

        [chunk async for chunk in runtime.stream(AgentTask(user_id=1, goal="route"))]

        [trace] = await store.list_recent(limit=1, user_id=1)
        events = [event for step in trace.steps for event in step.events]
        assert events
        assert all(event.run_id == trace.run_id for event in events)
        assert all(event.sequence is not None for event in events)
        assert [event.sequence for event in events] == sorted(
            event.sequence for event in events
        )

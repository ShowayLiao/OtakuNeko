"""Tests for AgentRuntime (HARNESS-001 Step 03)."""

import pytest

from app.harness.task import AgentTask
from app.harness.state import AgentState
from app.harness.runtime import AgentRuntime
from app.harness.checkpoint import InMemoryCheckpointStore
from app.trace.store import InMemoryTraceStore


class MockAdapter:
    """A mock agent adapter for testing the runtime in isolation."""

    def __init__(self, result: object = None, should_fail: bool = False):
        self.result = result or {"answer": "Hello from mock"}
        self.should_fail = should_fail
        self.last_state = None

    async def run(self, state: AgentState) -> object:
        self.last_state = state.model_copy()
        if self.should_fail:
            raise RuntimeError("Mock adapter failure")
        return self.result


class MockStreamingAdapter:
    async def stream(self, state: AgentState, **kwargs: object):
        yield {"type": "message_chunk", "content": state.task.goal}


class TestAgentRuntime:
    async def test_execute_returns_completed_state(self) -> None:
        task = AgentTask(user_id=1, goal="test")
        adapter = MockAdapter()
        runtime = AgentRuntime(adapter=adapter)
        state = await runtime.execute(task)
        assert state.status == "completed"
        assert state.result == {"answer": "Hello from mock"}

    async def test_execute_passes_state_to_adapter(self) -> None:
        task = AgentTask(user_id=42, goal="Find anime")
        adapter = MockAdapter()
        runtime = AgentRuntime(adapter=adapter)
        await runtime.execute(task)
        assert adapter.last_state is not None
        assert adapter.last_state.task.user_id == 42
        assert adapter.last_state.status == "running"

    async def test_execute_failure_sets_failed_status(self) -> None:
        task = AgentTask(task_id=13, user_id=1, goal="test")
        adapter = MockAdapter(should_fail=True)
        checkpoints = InMemoryCheckpointStore()
        runtime = AgentRuntime(adapter=adapter, checkpoint_store=checkpoints)
        with pytest.raises(RuntimeError, match="Mock adapter failure"):
            await runtime.execute(task)
        saved = await checkpoints.load_state(13)
        assert saved is not None
        assert saved.status == "failed"

    async def test_execute_preserves_task_in_state(self) -> None:
        task = AgentTask(user_id=99, goal="deep test")
        adapter = MockAdapter()
        runtime = AgentRuntime(adapter=adapter)
        state = await runtime.execute(task)
        assert state.task == task
        assert state.task.user_id == 99
        assert state.task.goal == "deep test"

    async def test_stream_saves_completed_checkpoint(self) -> None:
        task = AgentTask(task_id=11, user_id=1, goal="stream test")
        checkpoints = InMemoryCheckpointStore()
        runtime = AgentRuntime(MockStreamingAdapter(), checkpoint_store=checkpoints)

        chunks = [chunk async for chunk in runtime.stream(task, model="test")]

        assert chunks == [{"type": "message_chunk", "content": "stream test"}]
        saved = await checkpoints.load_state(11)
        assert saved is not None
        assert saved.status == "completed"

    async def test_stream_saves_failed_checkpoint(self) -> None:
        class FailingStreamingAdapter:
            async def stream(self, state: AgentState, **kwargs: object):
                raise RuntimeError("stream failure")
                yield  # pragma: no cover

        task = AgentTask(task_id=12, user_id=1, goal="stream failure")
        checkpoints = InMemoryCheckpointStore()
        runtime = AgentRuntime(FailingStreamingAdapter(), checkpoint_store=checkpoints)

        with pytest.raises(RuntimeError, match="stream failure"):
            _ = [chunk async for chunk in runtime.stream(task)]

        saved = await checkpoints.load_state(12)
        assert saved is not None
        assert saved.status == "failed"

    async def test_stream_records_routing_decision_in_trace(self) -> None:
        class RoutingAdapter:
            async def stream(self, state, **kwargs):
                yield {
                    "type": "route_decision",
                    "route": "recommendation",
                    "agent": "recommendation",
                    "confidence": 1.0,
                    "rationale": "keyword",
                }
                yield {"type": "message_chunk", "content": "ok"}

        traces = InMemoryTraceStore()
        runtime = AgentRuntime(RoutingAdapter(), trace_store=traces)
        task = AgentTask(user_id=1, goal="recommend")
        _ = [chunk async for chunk in runtime.stream(task)]

        recorded = await traces.list_recent(limit=1)
        assert len(recorded) == 1
        events = [event for step in recorded[0].steps for event in step.events]
        assert any(event.event_type == "route_decision" for event in events)

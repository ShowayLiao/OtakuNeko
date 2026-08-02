from __future__ import annotations

import pytest

from app.harness.contracts import ErrorCode
from app.harness.coordinator import RunCoordinator
from app.harness.checkpoint import InMemoryCheckpointStore
from app.harness.runtime import AgentRuntime
from app.harness.state import AgentState
from app.harness.task import AgentTask


class SuccessAdapter:
    async def run(self, state: AgentState):
        return {"content": "ok"}

    async def stream(self, state: AgentState, **kwargs):
        yield {"type": "message_chunk", "content": "ok"}


class MemoryRunStore:
    def __init__(self) -> None:
        self.statuses: list[str] = []

    async def create(self, run):
        self.statuses.append(run.status)
        return run

    async def transition(self, run_id, status, *, error_code=None):
        self.statuses.append(status)


class MemoryEventStore:
    def __init__(self) -> None:
        self.events = []

    async def append(self, event):
        self.events.append(event)
        return event


@pytest.mark.asyncio
async def test_execute_and_stream_share_one_terminal_contract() -> None:
    runtime = AgentRuntime(SuccessAdapter())
    executed = await runtime.execute(AgentTask(task_id=1, user_id=7, goal="execute"))
    checkpoints = InMemoryCheckpointStore()
    stream_runtime = AgentRuntime(SuccessAdapter(), checkpoint_store=checkpoints)
    streamed = [
        item async for item in stream_runtime.stream(
            AgentTask(task_id=2, user_id=7, goal="stream")
        )
    ]
    saved_stream = await checkpoints.load_state(2)

    assert executed.terminal_result is not None
    assert executed.terminal_result.status == "completed"
    assert streamed[-1]["type"] == "message_chunk"
    assert saved_stream is not None
    assert saved_stream.terminal_result is not None
    assert saved_stream.terminal_result.status == "completed"


@pytest.mark.asyncio
async def test_coordinator_execute_persists_one_terminal_event_and_cannot_overwrite_it() -> None:
    run_store = MemoryRunStore()
    event_store = MemoryEventStore()
    coordinator = RunCoordinator(
        SuccessAdapter(),
        run_store=run_store,
        event_store=event_store,
    )

    state = await coordinator.execute(
        AgentTask(task_id=3, user_id=7, goal="persist", metadata={"run_id": "run-3"})
    )
    await coordinator._persist_terminal()

    assert state.terminal_result == coordinator.terminal_result
    assert state.terminal_result is not None
    assert state.terminal_result.status == "completed"
    terminal_events = [event for event in event_store.events if event.event_type == "run.succeeded"]
    assert len(terminal_events) == 1
    assert run_store.statuses[-1] == "succeeded"


@pytest.mark.asyncio
async def test_persistence_failure_is_not_reported_as_success() -> None:
    class FailingEvents(MemoryEventStore):
        async def append(self, event):
            if event.event_type.startswith("run.") and event.event_type != "run.started":
                raise RuntimeError("event store unavailable")
            return await super().append(event)

    coordinator = RunCoordinator(
        SuccessAdapter(),
        run_store=MemoryRunStore(),
        event_store=FailingEvents(),
    )
    state = await coordinator.execute(
        AgentTask(task_id=4, user_id=7, goal="persistence", metadata={"run_id": "run-4"})
    )

    assert state.terminal_result is not None
    assert state.terminal_result.status == "failed"
    assert state.terminal_result.error_code == ErrorCode.PERMANENT

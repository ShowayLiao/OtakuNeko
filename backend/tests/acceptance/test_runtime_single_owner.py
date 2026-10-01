from __future__ import annotations

import json

import pytest

from app.harness.contracts import ErrorCode
from app.harness.coordinator import RunCoordinator
from app.harness.checkpoint import InMemoryCheckpointStore
from app.harness.contracts import RunEvent
from app.harness.persistence.event_store import EventStore
from app.harness.persistence.run_store import RunStore
from app.harness.runtime import AgentRuntime
from app.harness.state import AgentState
from app.harness.task import AgentTask
from app.models.agent_run import AgentInvocation, AgentRun, AgentRunEvent


class SuccessAdapter:
    async def run(self, state: AgentState):
        return {"content": "ok"}

    async def stream(self, state: AgentState, **kwargs):
        yield {"type": "message_chunk", "content": "ok"}


class MemoryRunStore(RunStore):
    def __init__(self) -> None:
        self.statuses: list[str] = []
        self.runs: dict[str, AgentRun] = {}
        self.invocations: dict[str, AgentInvocation] = {}

    async def create(self, run: AgentRun | None = None, **fields: object) -> AgentRun:
        if run is None:
            run = AgentRun(**fields)
        elif fields:
            raise TypeError("provide either an AgentRun or create fields, not both")
        self.runs.setdefault(run.run_id, run)
        self.statuses.append(run.status)
        return self.runs[run.run_id]

    async def transition(
        self, run_id: str, status: str, *, error_code: str | None = None
    ) -> AgentRun:
        run = self.runs[run_id]
        run.status = status
        run.error_code = error_code
        self.statuses.append(status)
        return run

    async def get(self, run_id: str, *, user_id: int | None = None) -> AgentRun | None:
        run = self.runs.get(run_id)
        if run is not None and user_id is not None and run.user_id != user_id:
            return None
        return run

    async def create_invocation(
        self,
        *,
        run_id: str,
        invocation_id: str,
        sequence: int,
        capability: str,
        capability_version: str = "v1",
        input_payload: dict[str, object] | None = None,
        idempotency_key: str | None = None,
    ) -> AgentInvocation:
        del input_payload
        invocation = AgentInvocation(
            invocation_id=invocation_id,
            run_id=run_id,
            sequence=sequence,
            capability=capability,
            capability_version=capability_version,
            status="running",
            idempotency_key=idempotency_key,
        )
        self.invocations.setdefault(invocation_id, invocation)
        return self.invocations[invocation_id]

    async def finish_invocation(
        self, invocation_id: str, status: str, *, error_code: str | None = None
    ) -> AgentInvocation:
        invocation = self.invocations[invocation_id]
        invocation.status = status
        invocation.error_code = error_code
        return invocation


class MemoryEventStore(EventStore):
    def __init__(self) -> None:
        self.events: list[AgentRunEvent] = []

    async def append(
        self,
        event: RunEvent | AgentRunEvent,
        *,
        event_id: str | None = None,
    ) -> AgentRunEvent:
        if isinstance(event, AgentRunEvent):
            stored = event
        else:
            stored = AgentRunEvent(
                event_id=event_id or f"evt-{event.run_id}-{event.sequence}",
                run_id=event.run_id,
                sequence=event.sequence,
                event_type=event.event_type,
                invocation_id=event.invocation_id,
                payload_json=json.dumps(event.payload),
            )
        self.events.append(stored)
        return stored

    async def list_after(
        self, run_id: str, after_sequence: int = 0, *, limit: int = 500
    ) -> list[AgentRunEvent]:
        return [
            event
            for event in self.events
            if event.run_id == run_id and event.sequence > after_sequence
        ][:limit]


@pytest.mark.asyncio
async def test_execute_and_stream_share_one_terminal_contract() -> None:
    runtime = AgentRuntime(SuccessAdapter())
    executed = await runtime.execute(AgentTask(task_id=1, user_id=7, goal="execute"))
    checkpoints = InMemoryCheckpointStore()
    stream_runtime = AgentRuntime(SuccessAdapter(), checkpoint_store=checkpoints)
    streamed = [
        item
        async for item in stream_runtime.stream(
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
async def test_coordinator_execute_persists_one_terminal_event_and_cannot_overwrite_it() -> (
    None
):
    run_store = MemoryRunStore()
    event_store = MemoryEventStore()
    coordinator = RunCoordinator(
        SuccessAdapter(),
        run_store=run_store,
        event_store=event_store,
    )

    state = await coordinator.execute(
        AgentTask(
            task_id=3,
            user_id=7,
            goal="persist",
            task_metadata={"run_id": "run-3"},
        )
    )
    await coordinator._persist_terminal()

    assert state.terminal_result == coordinator.terminal_result
    assert state.terminal_result is not None
    assert state.terminal_result.status == "completed"
    terminal_events = [
        event for event in event_store.events if event.event_type == "run.succeeded"
    ]
    assert len(terminal_events) == 1
    assert run_store.statuses[-1] == "succeeded"


@pytest.mark.asyncio
async def test_persistence_failure_is_not_reported_as_success() -> None:
    class FailingEvents(MemoryEventStore):
        async def append(
            self,
            event: RunEvent | AgentRunEvent,
            *,
            event_id: str | None = None,
        ) -> AgentRunEvent:
            if (
                event.event_type.startswith("run.")
                and event.event_type != "run.started"
            ):
                raise RuntimeError("event store unavailable")
            return await super().append(event, event_id=event_id)

    coordinator = RunCoordinator(
        SuccessAdapter(),
        run_store=MemoryRunStore(),
        event_store=FailingEvents(),
    )
    state = await coordinator.execute(
        AgentTask(
            task_id=4,
            user_id=7,
            goal="persistence",
            task_metadata={"run_id": "run-4"},
        )
    )

    assert state.terminal_result is not None
    assert state.terminal_result.status == "failed"
    assert state.terminal_result.error_code == ErrorCode.PERMANENT

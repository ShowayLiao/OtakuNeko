from __future__ import annotations

import pytest

from app.capabilities.registry import CapabilityRegistry
from app.capabilities.types import ActionDescriptor, CapabilityResult
from app.harness.contracts import ExecutionContext, RunEvent
from app.harness.dispatcher import Dispatcher
from app.harness.model_types import ModelCallResult
from app.harness.persistence.event_store import EventStore
from app.harness.persistence.run_store import RunStore
from app.harness.runtime import AgentRuntime
from app.harness.task import AgentTask
from app.models.agent_run import AgentRun


class _MemoryRunStore:
    def __init__(self) -> None:
        self.runs: dict[str, AgentRun] = {}
        self.invocations: dict[str, dict] = {}

    async def create(self, run: AgentRun) -> AgentRun:
        return self.runs.setdefault(run.run_id, run)

    async def get(self, run_id: str, *, user_id: int | None = None):
        run = self.runs.get(run_id)
        if run is not None and user_id is not None and run.user_id != user_id:
            return None
        return run

    async def transition(self, run_id: str, status: str, *, error_code=None):
        run = self.runs[run_id]
        run.status = status
        run.error_code = error_code
        return run

    async def create_invocation(self, **fields):
        current = self.invocations.get(fields["invocation_id"])
        if current is not None:
            return current
        self.invocations[fields["invocation_id"]] = dict(fields, status="running")
        return self.invocations[fields["invocation_id"]]

    async def finish_invocation(self, invocation_id: str, status: str, *, error_code=None):
        self.invocations[invocation_id].update(status=status, error_code=error_code)
        return self.invocations[invocation_id]


class _MemoryEventStore:
    def __init__(self) -> None:
        self.events: list[RunEvent] = []

    async def append(self, event: RunEvent, **kwargs):
        existing = next(
            (item for item in self.events if item.run_id == event.run_id and item.sequence == event.sequence),
            None,
        )
        if existing is not None:
            assert existing.model_dump() == event.model_dump()
            return existing
        self.events.append(event)
        return event

    async def list_after(self, run_id: str, after_sequence: int = 0, **kwargs):
        return [item for item in self.events if item.run_id == run_id and item.sequence > after_sequence]


class _Catalog:
    name = "catalog"

    def actions(self):
        return [
            ActionDescriptor(
                name="search",
                public_name="catalog.search",
                description="search",
                input_schema={"type": "object"},
            )
        ]

    async def execute(self, action: str, **kwargs):
        return CapabilityResult.ok(items=["anime-a"]).to_dict()


class _Gateway:
    def __init__(self, run_id: str = "run-canonical") -> None:
        self.calls = 0
        self.run_id = run_id

    async def infer(self, **kwargs):
        self.calls += 1
        decision = (
            {
                "schema_version": "v1",
                "decision_id": "decision-canonical",
                "run_id": self.run_id,
                "action": "invoke",
                "capability": "catalog.search",
                "capability_version": "v1",
                "arguments": {},
            }
            if self.calls == 1
            else {
                "schema_version": "v1",
                "decision_id": "decision-answer",
                "run_id": self.run_id,
                "action": "respond",
                "content": "done",
            }
        )
        return ModelCallResult(
            provider="fake",
            model="fake-model",
            operation="infer",
            status="completed",
            decision=decision,
        )


def _runtime(run_store=None, event_store=None, gateway=None):
    registry = CapabilityRegistry()
    registry.register(_Catalog())
    return AgentRuntime(
        object(),
        model_gateway=gateway or _Gateway(),
        dispatcher=Dispatcher(registry),
        run_store=run_store,
        event_store=event_store,
    )


@pytest.mark.asyncio
async def test_primary_runtime_persists_one_replayable_canonical_sequence() -> None:
    run_store = _MemoryRunStore()
    event_store = _MemoryEventStore()
    gateway = _Gateway()
    runtime = _runtime(run_store, event_store, gateway)

    events = [
        event
        async for event in runtime.stream_decision(
            AgentTask(
                user_id=7,
                goal="search",
                metadata={"run_id": "run-canonical", "thread_id": "thread-1", "messages": []},
            ),
            context=ExecutionContext(
                principal_id=7,
                run_id="run-canonical",
                trace_id="trace-canonical",
                capability_allowlist=frozenset({"catalog.search"}),
            ),
        )
    ]

    persisted = await event_store.list_after("run-canonical")
    assert events[-1]["type"] == "run_completed"
    assert [event.sequence for event in persisted] == list(range(1, len(persisted) + 1))
    assert persisted[0].event_type == "run.started"
    assert persisted[-1].event_type == "run.succeeded"
    assert any(event.event_type == "tool_call_start" for event in persisted)
    assert any(event.event_type == "tool_call_end" for event in persisted)
    assert run_store.runs["run-canonical"].status == "succeeded"
    assert len(run_store.invocations) == 1
    assert next(iter(run_store.invocations.values()))["status"] == "succeeded"
    assert gateway.calls == 2


@pytest.mark.asyncio
async def test_primary_runtime_does_not_report_success_when_event_persistence_fails() -> None:
    class _FailingEventStore(_MemoryEventStore):
        async def append(self, event: RunEvent, **kwargs):
            if event.event_type != "run.started":
                raise RuntimeError("event store unavailable")
            return await super().append(event, **kwargs)

    run_store = _MemoryRunStore()
    runtime = _runtime(run_store, _FailingEventStore())

    events = [
        event
        async for event in runtime.stream_decision(
            AgentTask(user_id=7, goal="persist", metadata={"run_id": "run-fail", "messages": []}),
            context=ExecutionContext(
                principal_id=7,
                run_id="run-fail",
                trace_id="trace-fail",
                capability_allowlist=frozenset({"catalog.search"}),
            ),
        )
    ]

    assert events[-1]["type"] == "run_failed"
    assert run_store.runs["run-fail"].status == "failed"


@pytest.mark.asyncio
async def test_primary_runtime_replay_of_terminal_run_does_not_invoke_gateway_again() -> None:
    run_store = _MemoryRunStore()
    event_store = _MemoryEventStore()
    first_gateway = _Gateway()
    first_runtime = _runtime(run_store, event_store, first_gateway)
    task = AgentTask(
        user_id=7,
        goal="search",
        metadata={"run_id": "run-canonical", "messages": []},
    )
    context = ExecutionContext(
        principal_id=7,
        run_id="run-canonical",
        trace_id="trace-replay-primary",
        capability_allowlist=frozenset({"catalog.search"}),
    )

    first = [event async for event in first_runtime.stream_decision(task, context=context)]
    second_gateway = _Gateway()
    second = [
        event
        async for event in _runtime(run_store, event_store, second_gateway).stream_decision(
            task,
            context=context,
        )
    ]

    assert first[-1]["type"] == "run_completed"
    assert second[-1]["type"] == "run_completed"
    assert second_gateway.calls == 0
    assert len(event_store.events) == len(await event_store.list_after("run-canonical"))


@pytest.mark.asyncio
async def test_primary_runtime_replay_preserves_persisted_terminal_error_code() -> None:
    run_store = _MemoryRunStore()
    run_store.runs["run-failed"] = AgentRun(
        run_id="run-failed",
        status="failed",
        error_code="invalid_request",
    )
    gateway = _Gateway("run-failed")
    runtime = _runtime(run_store, _MemoryEventStore(), gateway)

    events = [
        event
        async for event in runtime.stream_decision(
            AgentTask(
                user_id=7,
                goal="search",
                metadata={"run_id": "run-failed", "messages": []},
            ),
            context=ExecutionContext(
                principal_id=7,
                run_id="run-failed",
                trace_id="trace-failed-replay",
            ),
        )
    ]

    assert events[-1]["type"] == "run_failed"
    assert events[-1]["error_code"] == "invalid_request"
    assert gateway.calls == 0


@pytest.mark.asyncio
async def test_primary_runtime_writes_sql_canonical_facts(db_session) -> None:
    runtime = _runtime(
        RunStore(db_session),
        EventStore(db_session),
        _Gateway("run-sql-primary"),
    )
    task = AgentTask(
        user_id=7,
        goal="search",
        metadata={"run_id": "run-sql-primary", "thread_id": "thread-1", "messages": []},
    )
    context = ExecutionContext(
        principal_id=7,
        run_id="run-sql-primary",
        trace_id="trace-sql-primary",
        capability_allowlist=frozenset({"catalog.search"}),
    )

    events = [event async for event in runtime.stream_decision(task, context=context)]
    stored_run = await RunStore(db_session).get("run-sql-primary", user_id=7)
    persisted = await EventStore(db_session).list_after("run-sql-primary")

    assert events[-1]["type"] == "run_completed"
    assert stored_run is not None and stored_run.status == "succeeded"
    assert [event.sequence for event in persisted] == list(range(1, len(persisted) + 1))
    assert persisted[-1].event_type == "run.succeeded"
    assert {event.invocation_id for event in persisted if event.invocation_id} == {
        "decision-canonical"
    }

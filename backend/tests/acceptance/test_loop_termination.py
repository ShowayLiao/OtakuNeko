"""Acceptance tests for terminal reasons on the durable Decision Runtime path."""

from __future__ import annotations

from collections.abc import AsyncIterator, Sequence
import json
from pathlib import Path
from time import monotonic
from typing import Any, Literal

import pytest
from sqlmodel.ext.asyncio.session import AsyncSession

from app.capabilities.base import BaseCapability
from app.capabilities.registry import CapabilityRegistry
from app.capabilities.types import ActionDescriptor, CapabilityResult
from app.harness.budget import CancellationToken, RunBudget
from app.harness.contracts import (
    ErrorCode,
    ExecutionContext,
    RunRequest,
    RunResult,
)
from app.harness.debug import DebugRunReport, run_debug
from app.harness.dispatcher import Dispatcher
from app.harness.model_gateway import ModelGateway
from app.harness.model_types import ModelCallResult, ModelStreamEvent
from app.harness.persistence.event_store import EventStore
from app.harness.persistence.run_store import RunStore
from app.harness.runtime import AgentRuntime
from app.harness.task import AgentTask
from app.models.agent_run import AgentRunEvent


_ACTION = "loop_fixture.inspect"
_TERMINAL_EVENT_TYPES = {"run.succeeded", "run.failed", "run.cancelled"}


class _ScriptedGateway(ModelGateway):
    """Deterministic external-provider boundary around the real Runtime."""

    def __init__(self, responses: Sequence[dict[str, Any] | ModelCallResult]) -> None:
        self._responses = list(responses)
        self.calls = 0

    async def infer(
        self,
        *,
        goal: str,
        messages: list[dict[str, Any]],
        context: dict[str, Any] | None = None,
        run_id: str | None = None,
        trace_id: str | None = None,
        call_id: str | None = None,
        cancellation: CancellationToken | None = None,
        deadline: float | None = None,
        budget: dict[str, Any] | None = None,
        capability_catalog: list[dict[str, Any]] | None = None,
        **kwargs: Any,
    ) -> ModelCallResult:
        del (
            goal,
            messages,
            context,
            trace_id,
            call_id,
            cancellation,
            deadline,
            budget,
            capability_catalog,
            kwargs,
        )
        self.calls += 1
        if not self._responses:
            raise AssertionError("Runtime requested an unconfigured Decision")
        response = self._responses.pop(0)
        if isinstance(response, ModelCallResult):
            return response.model_copy(deep=True)
        return ModelCallResult(
            provider="fixture",
            model="termination-test",
            operation="infer",
            status="completed",
            decision=dict(response),
        )

    async def stream_infer(
        self,
        *,
        goal: str,
        messages: list[dict[str, Any]],
        context: dict[str, Any] | None = None,
        run_id: str | None = None,
        trace_id: str | None = None,
        call_id: str | None = None,
        cancellation: CancellationToken | None = None,
        deadline: float | None = None,
        budget: dict[str, Any] | None = None,
        capability_catalog: list[dict[str, Any]] | None = None,
        **kwargs: Any,
    ) -> AsyncIterator[ModelStreamEvent]:
        result = await self.infer(
            goal=goal,
            messages=messages,
            context=context,
            run_id=run_id,
            trace_id=trace_id,
            call_id=call_id,
            cancellation=cancellation,
            deadline=deadline,
            budget=budget,
            capability_catalog=capability_catalog,
            **kwargs,
        )
        yield ModelStreamEvent(result=result)

    async def synthesize(
        self,
        *,
        goal: str,
        messages: list[dict[str, Any]],
        results: Sequence[Any],
        cancellation: CancellationToken | None = None,
        deadline: float | None = None,
        budget: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> str:
        raise AssertionError("Decision termination must not synthesize")

    async def synthesize_result(
        self,
        *,
        goal: str,
        messages: list[dict[str, Any]],
        results: Sequence[Any],
        cancellation: CancellationToken | None = None,
        deadline: float | None = None,
        budget: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> ModelCallResult:
        raise AssertionError("Decision termination must not synthesize")


class _ReadOnlyFixtureCapability(BaseCapability):
    name = "loop_fixture"
    description = "Synthetic read-only action used by Runtime termination tests"

    def __init__(self) -> None:
        self.calls: list[str] = []

    def actions(self) -> list[ActionDescriptor]:
        return [
            ActionDescriptor(
                name="inspect",
                public_name=_ACTION,
                description="Return one synthetic value",
                input_schema={
                    "type": "object",
                    "properties": {"value": {"type": "string"}},
                    "required": ["value"],
                },
                requires_auth=True,
            )
        ]

    async def execute(self, action: str, **kwargs: Any) -> dict[str, Any]:
        assert action == "inspect"
        value = str(kwargs["value"])
        self.calls.append(value)
        return CapabilityResult.ok(value=value).to_dict()


class _PagedEventStore(EventStore):
    """Exercise durable terminal lookup when event history spans pages."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session)
        self.page_reads = 0

    async def list_after(
        self, run_id: str, after_sequence: int = 0, *, limit: int = 500
    ) -> list[AgentRunEvent]:
        self.page_reads += 1
        return await super().list_after(
            run_id, after_sequence=after_sequence, limit=min(limit, 2)
        )


def _request(run_id: str) -> RunRequest:
    return RunRequest(
        run_id=run_id,
        goal="Exercise the versioned Decision loop",
        messages=[{"role": "user", "content": "Inspect two fixture values"}],
        model="termination-test",
    )


def _context(run_id: str) -> ExecutionContext:
    return ExecutionContext(
        principal_id=41,
        run_id=run_id,
        trace_id=f"trace-{run_id}",
        thread_id=f"thread-{run_id}",
        capability_allowlist=frozenset({_ACTION}),
    )


def _decision(
    run_id: str,
    decision_id: str,
    action: str,
    *,
    value: str | None = None,
    content: str | None = None,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "schema_version": "v1",
        "decision_id": decision_id,
        "run_id": run_id,
        "action": action,
    }
    if action == "invoke":
        result.update(
            {
                "capability": _ACTION,
                "capability_version": "v1",
                "arguments": {"value": value or "fixture"},
            }
        )
    if content is not None:
        result["content"] = content
    return result


def _runtime(
    session: AsyncSession,
    gateway: _ScriptedGateway,
    capability: _ReadOnlyFixtureCapability | None = None,
    event_store: EventStore | None = None,
) -> AgentRuntime:
    registry = CapabilityRegistry()
    if capability is not None:
        registry.register(capability)
    return AgentRuntime(
        None,
        model_gateway=gateway,
        dispatcher=Dispatcher(registry),
        run_store=RunStore(session),
        event_store=event_store or EventStore(session),
    )


def _terminal(report: DebugRunReport) -> Any:
    terminal_events = [
        event for event in report.events if event.event_type in _TERMINAL_EVENT_TYPES
    ]
    assert len(terminal_events) == 1
    terminal = terminal_events[0]
    reason = terminal.payload.get("termination_reason")
    assert isinstance(reason, str) and reason.strip()
    assert report.termination_reason == reason
    return terminal


def _record_metrics(
    report: DebugRunReport,
    gateway: _ScriptedGateway,
    capability: _ReadOnlyFixtureCapability | None,
    record_property: Any,
) -> None:
    terminal = _terminal(report)
    record_property("termination_reason", terminal.payload["termination_reason"])
    record_property("model_call_count", gateway.calls)
    record_property(
        "tool_dispatch_count", len(capability.calls) if capability is not None else 0
    )
    record_property("terminal_event_count", 1)


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.db
@pytest.mark.parametrize("final_action", ["respond", "finish"])
async def test_debug_loop_continues_through_tools_then_persists_final_reason(
    db_session: AsyncSession, final_action: str, record_property: Any
) -> None:
    run_id = f"loop-final-{final_action}"
    capability = _ReadOnlyFixtureCapability()
    gateway = _ScriptedGateway(
        [
            _decision(run_id, "invoke-one", "invoke", value="one"),
            _decision(run_id, "invoke-two", "invoke", value="two"),
            _decision(
                run_id,
                "final-answer",
                final_action,
                content="Two fixture values inspected",
            ),
        ]
    )
    report = await run_debug(
        _request(run_id),
        _context(run_id),
        runtime=_runtime(db_session, gateway, capability),
    )

    assert report.status == "succeeded"
    assert gateway.calls == 3
    assert capability.calls == ["one", "two"]
    model_decisions = [
        event for event in report.events if event.event_type == "model_decision"
    ]
    assert len(model_decisions) == 3
    assert all(event.schema_version == "v1" for event in model_decisions)
    terminal = _terminal(report)
    assert terminal.event_type == "run.succeeded"
    assert terminal.payload["termination_reason"] == final_action
    record_property("decision_schema_version", "v1")
    _record_metrics(report, gateway, capability, record_property)


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.db
async def test_semantically_repeated_decisions_with_new_ids_stop_at_max_steps(
    db_session: AsyncSession, record_property: Any
) -> None:
    run_id = "loop-semantic-repeat"
    capability = _ReadOnlyFixtureCapability()

    def same_action(decision_id: str) -> dict[str, Any]:
        return _decision(run_id, decision_id, "invoke", value="same")

    gateway = _ScriptedGateway([same_action("invoke-one"), same_action("invoke-two")])
    budget = RunBudget(max_steps=2, max_model_calls=6)

    report = await run_debug(
        _request(run_id),
        _context(run_id),
        runtime=_runtime(db_session, gateway, capability),
        budget=budget,
    )

    assert report.status == "failed"
    assert report.error_code == ErrorCode.BUDGET_EXCEEDED.value
    assert report.termination_reason == "max_steps"
    assert gateway.calls == 2
    assert capability.calls == ["same", "same"]
    _record_metrics(report, gateway, capability, record_property)


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.db
async def test_exact_repeated_decision_id_fails_before_second_dispatch(
    db_session: AsyncSession, record_property: Any
) -> None:
    run_id = "loop-exact-repeat"
    capability = _ReadOnlyFixtureCapability()
    repeated = _decision(run_id, "same-id", "invoke", value="once")
    gateway = _ScriptedGateway([repeated, repeated])

    report = await run_debug(
        _request(run_id),
        _context(run_id),
        runtime=_runtime(db_session, gateway, capability),
    )

    assert report.status == "failed"
    assert report.error_code == ErrorCode.INVALID_REQUEST.value
    assert report.termination_reason == "repeated_decision"
    assert gateway.calls == 2
    assert capability.calls == ["once"]
    _record_metrics(report, gateway, capability, record_property)


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.db
@pytest.mark.parametrize("invalid_action", ["unknown", "final"])
async def test_unknown_action_gets_one_repair_then_fails_closed(
    db_session: AsyncSession, invalid_action: str, record_property: Any
) -> None:
    run_id = f"loop-invalid-{invalid_action}"
    invalid = _decision(run_id, "invalid-action", invalid_action)
    capability = _ReadOnlyFixtureCapability()
    gateway = _ScriptedGateway([invalid, invalid])

    report = await run_debug(
        _request(run_id),
        _context(run_id),
        runtime=_runtime(db_session, gateway, capability),
    )

    assert report.status == "failed"
    assert report.error_code == ErrorCode.INVALID_REQUEST.value
    assert report.termination_reason == "invalid_decision"
    assert gateway.calls == 2
    assert capability.calls == []
    _record_metrics(report, gateway, capability, record_property)


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.db
@pytest.mark.parametrize(
    ("control", "expected_status", "expected_reason"),
    [
        ("cancelled", "cancelled", "cancelled"),
        ("budget", "failed", "max_steps"),
        ("timeout", "failed", "timeout"),
        ("provider_error", "failed", "provider_error"),
    ],
)
async def test_control_and_provider_terminations_have_durable_reasons(
    db_session: AsyncSession,
    control: str,
    expected_status: str,
    expected_reason: str,
    record_property: Any,
) -> None:
    run_id = f"loop-control-{control}"
    gateway_response: list[dict[str, Any] | ModelCallResult] = []
    budget: RunBudget | None = None
    cancellation = CancellationToken()
    if control == "cancelled":
        cancellation.cancel()
    elif control == "budget":
        budget = RunBudget(max_steps=0)
    elif control == "timeout":
        budget = RunBudget(deadline_seconds=10)
        budget.started_at = monotonic() - 20
    else:
        gateway_response.append(
            ModelCallResult(
                provider="fixture",
                model="termination-test",
                operation="infer",
                status="failed",
                error_code="permanent",
            )
        )
    gateway = _ScriptedGateway(gateway_response)
    report = await run_debug(
        _request(run_id),
        _context(run_id),
        runtime=_runtime(db_session, gateway),
        budget=budget,
        cancellation=cancellation,
    )

    assert report.status == expected_status
    assert report.termination_reason == expected_reason
    if control in {"cancelled", "budget", "timeout"}:
        assert gateway.calls == 0
    else:
        assert gateway.calls == 1
    terminal = _terminal(report)
    if control == "timeout":
        assert terminal.payload.get("status") == "timeout"
    _record_metrics(report, gateway, None, record_property)


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.db
@pytest.mark.parametrize("legacy_event", [False, True])
async def test_terminal_replay_keeps_persisted_reason_without_calling_gateway_again(
    db_session: AsyncSession, legacy_event: bool, record_property: Any
) -> None:
    run_id = "loop-terminal-replay"
    gateway = _ScriptedGateway(
        [_decision(run_id, "final-answer", "respond", content="Done")]
    )
    event_store = _PagedEventStore(db_session)
    runtime = _runtime(db_session, gateway, event_store=event_store)
    request = _request(run_id)
    context = _context(run_id)

    report = await run_debug(request, context, runtime=runtime)
    assert report.termination_reason == "respond"
    assert gateway.calls == 1
    assert len(report.events) > 2
    if legacy_event:
        stored = (await EventStore(db_session).list_after(run_id))[-1]
        payload = stored.payload
        payload.pop("termination_reason")
        stored.payload_json = json.dumps(payload)
        db_session.add(stored)
        await db_session.commit()
    expected_reason = "completed" if legacy_event else report.termination_reason
    assert event_store.page_reads > 1
    page_reads_before_replay = event_store.page_reads

    task = AgentTask(
        user_id=41,
        goal=request.goal,
        task_metadata={
            "run_id": run_id,
            "trace_id": context.trace_id,
            "thread_id": context.thread_id,
            "model": request.model,
            "messages": request.messages,
        },
    )
    replay = [event async for event in runtime.stream_decision(task, context=context)]

    assert gateway.calls == 1
    assert len(replay) == 1
    assert replay[0]["type"] == "run_completed"
    assert replay[0]["termination_reason"] == expected_reason
    assert event_store.page_reads - page_reads_before_replay >= 2
    terminal = _terminal(report)
    assert terminal.payload["termination_reason"] == "respond"
    record_property("replay_termination_reason", replay[0]["termination_reason"])
    _record_metrics(report, gateway, None, record_property)


@pytest.mark.parametrize(
    ("status", "error_code", "expected_reason"),
    [
        ("completed", None, "completed"),
        ("failed", ErrorCode.PROVIDER_ERROR, "provider_error"),
        ("cancelled", ErrorCode.CANCELLED, "cancelled"),
        ("timeout", ErrorCode.TIMEOUT, "timeout"),
    ],
)
def test_legacy_run_result_construction_populates_nonempty_reason(
    status: Literal["completed", "failed", "cancelled", "timeout"],
    error_code: ErrorCode | None,
    expected_reason: str,
) -> None:
    result = RunResult(run_id="legacy-result", status=status, error_code=error_code)
    assert result.termination_reason == expected_reason
    assert result.model_dump(mode="json")["termination_reason"] == expected_reason


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.db
@pytest.mark.parametrize("invalid", ["configuration", "identity"])
async def test_runtime_preflight_failures_also_explain_termination(
    db_session: AsyncSession, invalid: str, record_property: Any
) -> None:
    run_id = f"loop-preflight-{invalid}"
    gateway = _ScriptedGateway([])
    runtime = _runtime(db_session, gateway)
    context = _context(run_id)
    if invalid == "configuration":
        runtime.model_gateway = None
    else:
        context.run_id = "different-run"
    events = [
        event
        async for event in runtime.stream_decision(
            AgentTask(user_id=41, goal="preflight", task_metadata={"run_id": run_id}),
            context=context,
        )
    ]
    assert len(events) == 1 and events[0]["type"] == "run_failed"
    assert events[0]["termination_reason"] == (
        "runtime_not_configured" if invalid == "configuration" else "invalid_request"
    )
    assert gateway.calls == 0
    record_property("early_termination_reason", events[0]["termination_reason"])


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.db
async def test_persistence_failure_explains_returned_terminal_even_without_event_write(
    db_session: AsyncSession, record_property: Any
) -> None:
    class UnavailableEventStore(EventStore):
        async def append(self, *args: Any, **kwargs: Any) -> AgentRunEvent:
            raise RuntimeError("injected event writer failure")

    run_id = "loop-persistence-failure"
    gateway = _ScriptedGateway([])
    runtime = _runtime(
        db_session, gateway, event_store=UnavailableEventStore(db_session)
    )
    events = [
        event
        async for event in runtime.stream_decision(
            AgentTask(user_id=41, goal="persist", task_metadata={"run_id": run_id}),
            context=_context(run_id),
        )
    ]
    assert events[-1]["type"] == "run_failed"
    assert events[-1]["termination_reason"] == "persistence_error"
    stored = await RunStore(db_session).get(run_id, user_id=41)
    assert stored is not None and stored.status == "failed"
    assert await EventStore(db_session).list_after(run_id) == []
    assert gateway.calls == 0
    record_property("early_termination_reason", "persistence_error")
    record_property("event_writer_failure_not_falsely_persisted", "true")


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.db
async def test_checkpoint_lease_refusal_returns_a_termination_reason(
    db_session: AsyncSession, tmp_path: Path, record_property: Any
) -> None:
    from app.harness.checkpoint import SqliteCheckpointStore

    run_id = "loop-existing-lease"
    context = _context(run_id)
    assert context.thread_id is not None
    store = SqliteCheckpointStore(str(tmp_path / "lease.db"))
    try:
        lease = await store.claim_lease(run_id, context.thread_id, "lease-owner", 60)
        assert lease is not None
        gateway = _ScriptedGateway([])
        runtime = _runtime(db_session, gateway)
        runtime.checkpoint_store = store
        events = [
            event
            async for event in runtime.stream_decision(
                AgentTask(
                    user_id=41,
                    goal="lease",
                    task_metadata={
                        "run_id": run_id,
                        "thread_id": context.thread_id,
                    },
                ),
                context=context,
            )
        ]
        assert events[-1]["type"] == "run_failed"
        assert events[-1]["termination_reason"] == "checkpoint_lease_lost"
        assert gateway.calls == 0
        record_property("early_termination_reason", "checkpoint_lease_lost")
    finally:
        await store.close()

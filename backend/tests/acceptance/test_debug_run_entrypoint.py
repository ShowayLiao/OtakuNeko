"""Backend-only acceptance coverage for the durable debug Run entrypoint."""

from __future__ import annotations

from collections.abc import AsyncIterator, Sequence
from typing import Any

import pytest
from sqlalchemy import func, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.capabilities.base import BaseCapability
from app.capabilities.registry import CapabilityRegistry
from app.capabilities.types import ActionDescriptor, CapabilityResult
from app.harness.budget import CancellationToken, RunBudget
from app.harness.contracts import ExecutionContext, RunRequest
from app.harness.dispatcher import Dispatcher
from app.harness.model_gateway import ModelGateway
from app.harness.model_types import ModelCallResult, ModelStreamEvent
from app.harness.persistence.event_store import EventStore
from app.harness.persistence.run_store import InvalidRunTransition, RunStore
from app.harness.runtime import AgentRuntime
from app.models.agent_run import AgentInvocation, AgentRun, AgentRunEvent


class _DecisionGateway(ModelGateway):
    """Deterministic provider boundary; Runtime and Dispatcher stay real."""

    def __init__(self, decisions: list[dict[str, Any]]) -> None:
        self.decisions = list(decisions)
        self.calls: list[dict[str, Any]] = []

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
        del cancellation, deadline, budget, capability_catalog
        self.calls.append(
            {
                "goal": goal,
                "messages": messages,
                "context": context,
                "run_id": run_id,
                "trace_id": trace_id,
                "call_id": call_id,
                **kwargs,
            }
        )
        if not self.decisions:
            raise AssertionError("Runtime requested more Decisions than configured")
        return ModelCallResult(
            provider="fake",
            model="debug-test",
            operation="infer",
            status="completed",
            decision=self.decisions.pop(0),
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
        raise AssertionError("debug Decision path must not synthesize")

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
        raise AssertionError("debug Decision path must not synthesize")


class _IdentityCapability(BaseCapability):
    @property
    def name(self) -> str:
        return "debug_catalog"

    @property
    def description(self) -> str:
        return "Read-only capability for debug-entrypoint acceptance tests"

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def actions(self) -> list[ActionDescriptor]:
        return [
            ActionDescriptor(
                name="inspect",
                public_name="debug_catalog.inspect",
                description="Return a small synthetic catalog result",
                input_schema={"type": "object", "properties": {}},
                requires_auth=True,
            )
        ]

    async def execute(self, action: str, **kwargs: Any) -> dict[str, Any]:
        self.calls.append({"action": action, **kwargs})
        return CapabilityResult.ok(item="synthetic-entry").to_dict()


class _TwoEventPageStore(EventStore):
    """Exercise debug pagination against the real SQL event store."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session)
        self.page_sizes: list[int] = []

    async def list_after(
        self, run_id: str, after_sequence: int = 0, *, limit: int = 500
    ) -> list[AgentRunEvent]:
        self.page_sizes.append(limit)
        return await super().list_after(
            run_id, after_sequence=after_sequence, limit=min(limit, 2)
        )


def _request(run_id: str, *, user_id: int | None = None) -> RunRequest:
    return RunRequest(
        run_id=run_id,
        user_id=user_id,
        goal="Inspect a synthetic catalog entry",
        messages=[{"role": "user", "content": "Find one entry"}],
        model="debug-test",
    )


def _context(
    run_id: str,
    *,
    principal_id: int | None = 41,
    capability_allowlist: frozenset[str] = frozenset(),
) -> ExecutionContext:
    return ExecutionContext(
        principal_id=principal_id,
        run_id=run_id,
        trace_id=f"trace-{run_id}",
        thread_id=f"thread-{run_id}",
        capability_allowlist=capability_allowlist,
    )


def _runtime(
    session: AsyncSession,
    gateway: _DecisionGateway,
    *,
    capability: BaseCapability | None = None,
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


async def _row_count(session: AsyncSession, model: type[Any]) -> int:
    result = await session.execute(select(func.count()).select_from(model))
    return int(result.scalar_one())


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.db
async def test_run_debug_returns_versioned_report_from_durable_runtime(
    db_session: AsyncSession, record_property: Any
) -> None:
    from app.harness.debug import DebugRunReport, run_debug

    run_id = "debug-entry-success"
    gateway = _DecisionGateway(
        [
            {
                "schema_version": "v1",
                "decision_id": "debug-respond",
                "run_id": run_id,
                "action": "respond",
                "content": "Synthetic result",
            }
        ]
    )
    runtime = _runtime(db_session, gateway)

    report = await run_debug(_request(run_id), _context(run_id), runtime=runtime)

    assert isinstance(report, DebugRunReport)
    assert report.schema_version == "v1"
    assert report.run_id == run_id
    assert report.principal_id == 41
    assert report.status == "succeeded"
    assert {event.event_type for event in report.events} >= {
        "run.started",
        "run.succeeded",
    }
    assert [event.sequence for event in report.events] == list(
        range(1, len(report.events) + 1)
    )
    assert all(event.schema_version == "v1" for event in report.events)
    assert len(gateway.calls) == 1
    assert gateway.calls[0]["run_id"] == run_id
    run_store = RunStore(db_session)
    stored = await run_store.get(run_id, user_id=41)
    assert stored is not None and stored.user_id == 41
    assert await run_store.get(run_id, user_id=92) is None
    with pytest.raises(InvalidRunTransition):
        await run_store.transition(run_id, "running")
    unchanged = await run_store.get(run_id, user_id=41)
    assert unchanged is not None and unchanged.status == "succeeded"
    record_property("debug_run_status", report.status)
    record_property("debug_persisted_event_count", len(report.events))
    record_property("terminal_transition_rejected", "succeeded_to_running")


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.db
async def test_run_debug_dispatches_with_trusted_principal_and_reads_all_event_pages(
    db_session: AsyncSession, record_property: Any
) -> None:
    from app.harness.debug import run_debug

    run_id = "debug-entry-tool"
    capability = _IdentityCapability()
    gateway = _DecisionGateway(
        [
            {
                "schema_version": "v1",
                "decision_id": "debug-invoke",
                "run_id": run_id,
                "action": "invoke",
                "capability": "debug_catalog.inspect",
                "capability_version": "v1",
                "arguments": {},
            },
            {
                "schema_version": "v1",
                "decision_id": "debug-respond-after-tool",
                "run_id": run_id,
                "action": "respond",
                "content": "Synthetic result found",
            },
        ]
    )
    event_store = _TwoEventPageStore(db_session)
    runtime = _runtime(
        db_session, gateway, capability=capability, event_store=event_store
    )
    context = _context(
        run_id,
        capability_allowlist=frozenset({"debug_catalog.inspect"}),
    )

    report = await run_debug(_request(run_id), context, runtime=runtime)

    assert report.status == "succeeded"
    assert capability.calls == [{"action": "inspect", "user_id": 41}]
    assert event_store.page_sizes.count(1000) >= 2
    persisted = await EventStore(db_session).list_after(run_id, after_sequence=0)
    assert len(persisted) > 2
    assert [event.sequence for event in report.events] == [
        event.sequence for event in persisted
    ]
    assert [event.event_type for event in report.events] == [
        event.event_type for event in persisted
    ]
    invocation_result = await db_session.execute(select(AgentInvocation))
    invocations = list(invocation_result.scalars().all())
    assert len(invocations) == 1
    assert invocations[0].status == "succeeded"
    record_property("debug_tool_dispatches", len(capability.calls))
    record_property("debug_event_pages", event_store.page_sizes.count(1000))


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.db
@pytest.mark.parametrize(
    ("request_run_id", "request_user_id", "principal_id"),
    [
        ("different-run", None, 41),
        ("debug-invalid-identity", 99, 41),
        ("debug-invalid-identity", None, 0),
        ("debug-invalid-identity", None, None),
    ],
)
async def test_run_debug_rejects_untrusted_or_mismatched_identity_before_io(
    db_session: AsyncSession,
    request_run_id: str,
    request_user_id: int | None,
    principal_id: int | None,
    record_property: Any,
) -> None:
    from app.harness.debug import run_debug

    run_id = "debug-invalid-identity"
    gateway = _DecisionGateway([])
    runtime = _runtime(db_session, gateway)

    with pytest.raises(ValueError):
        await run_debug(
            _request(request_run_id, user_id=request_user_id),
            _context(run_id, principal_id=principal_id),
            runtime=runtime,
        )

    assert gateway.calls == []
    assert await _row_count(db_session, AgentRun) == 0
    assert await _row_count(db_session, AgentRunEvent) == 0
    record_property("debug_identity_rejections", 1)


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.db
async def test_run_debug_rejects_future_request_schema_before_io(
    db_session: AsyncSession,
) -> None:
    from app.harness.debug import run_debug

    run_id = "debug-future-request-schema"
    request = RunRequest.model_construct(
        schema_version="v2",
        run_id=run_id,
        user_id=None,
        goal="must reject",
        messages=[],
        model="debug-test",
    )
    gateway = _DecisionGateway([])
    runtime = _runtime(db_session, gateway)

    with pytest.raises(ValueError):
        await run_debug(request, _context(run_id), runtime=runtime)

    assert gateway.calls == []
    assert await _row_count(db_session, AgentRun) == 0
    assert await _row_count(db_session, AgentRunEvent) == 0


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.db
@pytest.mark.parametrize(
    "invalid_decision", ["future_schema", "forged_user", "wrong_run"]
)
async def test_run_debug_fails_closed_on_invalid_decisions_without_dispatch(
    db_session: AsyncSession, invalid_decision: str, record_property: Any
) -> None:
    from app.harness.debug import run_debug

    run_id = f"debug-invalid-decision-{invalid_decision}"
    response: dict[str, Any] = {
        "schema_version": "v1",
        "decision_id": f"decision-{invalid_decision}",
        "run_id": run_id,
        "action": "respond",
        "content": "invalid decisions must fail closed",
    }
    if invalid_decision == "future_schema":
        response["schema_version"] = "v2"
    elif invalid_decision == "forged_user":
        response.update(
            {
                "action": "invoke",
                "capability": "debug_catalog.inspect",
                "capability_version": "v1",
                "arguments": {"user_id": 999},
            }
        )
    else:
        response["run_id"] = "another-run"

    capability = _IdentityCapability()
    gateway = _DecisionGateway([response.copy(), response.copy()])
    runtime = _runtime(db_session, gateway, capability=capability)

    report = await run_debug(_request(run_id), _context(run_id), runtime=runtime)

    assert report.status == "failed"
    assert report.error_code == "invalid_request"
    assert capability.calls == []
    assert len(gateway.calls) == (2 if invalid_decision == "future_schema" else 1)
    assert {event.event_type for event in report.events} >= {
        "run.started",
        "run.failed",
    }
    assert await _row_count(db_session, AgentInvocation) == 0
    record_property("debug_invalid_decision_failures", 1)
    record_property("invalid_decision_category", invalid_decision)
    record_property("persisted_error_code", report.error_code)
    record_property("tool_dispatch_count", len(capability.calls))


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.db
@pytest.mark.parametrize(
    "missing", ["run_store", "event_store", "model_gateway", "dispatcher"]
)
async def test_run_debug_requires_complete_runtime_dependencies(
    db_session: AsyncSession, missing: str
) -> None:
    from app.harness.debug import run_debug

    run_id = f"debug-missing-{missing}"
    gateway = _DecisionGateway([])
    runtime = _runtime(db_session, gateway)
    setattr(runtime, missing, None)

    with pytest.raises(ValueError):
        await run_debug(_request(run_id), _context(run_id), runtime=runtime)

    assert gateway.calls == []
    assert await _row_count(db_session, AgentRun) == 0
    assert await _row_count(db_session, AgentRunEvent) == 0


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.db
@pytest.mark.parametrize("existing_owner", [41, 92])
async def test_run_debug_refuses_existing_owned_or_foreign_run_without_changes(
    db_session: AsyncSession, existing_owner: int, record_property: Any
) -> None:
    from app.harness.debug import run_debug

    run_id = f"debug-existing-owner-{existing_owner}"
    run_store = RunStore(db_session)
    await run_store.create(
        AgentRun(
            run_id=run_id,
            user_id=existing_owner,
            thread_id=f"thread-{run_id}",
            status="succeeded",
            goal_hash="existing-goal",
            model="existing-model",
        )
    )
    gateway = _DecisionGateway([])
    runtime = _runtime(db_session, gateway)

    with pytest.raises(ValueError):
        await run_debug(_request(run_id), _context(run_id), runtime=runtime)

    stored = await run_store.get(run_id)
    assert stored is not None
    assert stored.status == "succeeded"
    assert stored.user_id == existing_owner
    assert gateway.calls == []
    assert await _row_count(db_session, AgentRun) == 1
    assert await _row_count(db_session, AgentRunEvent) == 0
    record_property("debug_existing_run_rejections", 1)


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.db
@pytest.mark.parametrize("control", ["cancelled", "budget_exceeded"])
async def test_run_debug_forwards_runtime_cancellation_and_budget(
    db_session: AsyncSession, control: str, record_property: Any
) -> None:
    from app.harness.debug import run_debug

    run_id = f"debug-controls-{control}"
    gateway = _DecisionGateway([])
    token = CancellationToken()
    budget = RunBudget(max_steps=1)
    if control == "cancelled":
        token.cancel()
    else:
        budget.consume_step()
    report = await run_debug(
        _request(run_id),
        _context(run_id),
        runtime=_runtime(db_session, gateway),
        budget=budget,
        cancellation=token,
    )
    assert report.status == ("cancelled" if control == "cancelled" else "failed")
    assert report.error_code == control
    assert gateway.calls == []
    assert report.events[-1].event_type == (
        "run.cancelled" if control == "cancelled" else "run.failed"
    )
    record_property("trusted_control_rejection", control)
    record_property("gateway_calls_after_control", len(gateway.calls))

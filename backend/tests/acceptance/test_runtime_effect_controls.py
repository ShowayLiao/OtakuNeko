"""Persisted acceptance coverage for Runtime approval, failure, and retry controls."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from copy import deepcopy
import json
from typing import Any, cast
from uuid import uuid4

import pytest
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.capabilities.base import BaseCapability
from app.capabilities.registry import CapabilityRegistry
from app.capabilities.types import ActionDescriptor, CapabilityResult
from app.harness.budget import CancellationToken
from app.harness.checkpoint import SqliteCheckpointStore
from app.harness.contracts import ExecutionContext
from app.harness.dispatcher import Dispatcher
from app.harness.model_gateway import ModelGateway
from app.harness.model_types import ModelCallResult, ModelStreamEvent
from app.harness.persistence.event_store import EventStore
from app.harness.persistence.idempotency import SqlIdempotencyStore
from app.harness.persistence.run_store import RunStore
from app.harness.policy import Approval, PolicyEngine
from app.harness.runtime import AgentRuntime
from app.harness.task import AgentTask
from app.models import User
from app.models.agent_run import AgentInvocation, AgentRun, AgentRunEvent


_WRITE_ACTION = "controls_fixture.write"
_READ_ACTION = "controls_fixture.inspect"
_TERMINAL_EVENTS = {"run.succeeded", "run.failed", "run.cancelled"}
_RAW_FAILURE = "RAW_FAILURE_DETAIL_SENTINEL"


@pytest.fixture(
    params=[
        pytest.param(("sqlite", "db_session"), id="sqlite"),
        pytest.param(
            ("postgres", "postgres_session"),
            id="postgres",
            marks=pytest.mark.postgres,
        ),
    ]
)
def acceptance_database(
    request: pytest.FixtureRequest,
) -> tuple[str, AsyncSession]:
    database_name, fixture_name = request.param
    return database_name, request.getfixturevalue(fixture_name)


@pytest.fixture(autouse=True)
async def seeded_runtime_principal(
    acceptance_database: tuple[str, AsyncSession],
) -> None:
    _, session = acceptance_database
    session.add(User(id=41, username="runtime-effect-controls-principal"))
    await session.commit()


class _ScriptedGateway(ModelGateway):
    """Return fixed Decisions and retain call-time input snapshots."""

    def __init__(self, decisions: list[dict[str, Any]]) -> None:
        self._decisions = list(decisions)
        self.calls: list[dict[str, Any]] = []

    async def infer(self, **kwargs: Any) -> ModelCallResult:
        snapshot = dict(kwargs)
        cancellation = snapshot.pop("cancellation", None)
        snapshot["cancellation_cancelled"] = bool(
            cancellation is not None and cancellation.is_cancelled()
        )
        self.calls.append(deepcopy(snapshot))
        decision = deepcopy(self._decisions.pop(0))
        return ModelCallResult(
            provider="fixture",
            model="runtime-effect-controls",
            operation="infer",
            status="completed",
            decision=decision,
            trace_id=kwargs.get("trace_id"),
        )

    async def stream_infer(self, **kwargs: Any) -> AsyncIterator[ModelStreamEvent]:
        yield ModelStreamEvent(result=await self.infer(**kwargs))

    async def synthesize(self, **kwargs: Any) -> str:
        del kwargs
        raise AssertionError("The structured Decision path must not synthesize")

    async def synthesize_result(self, **kwargs: Any) -> ModelCallResult:
        del kwargs
        raise AssertionError("The structured Decision path must not synthesize")


class _ControlsCapability(BaseCapability):
    name = "controls_fixture"
    description = (
        "Synthetic read and write actions for Runtime controls acceptance tests"
    )

    def __init__(self, *, write_mode: str = "success") -> None:
        self.write_mode = write_mode
        self.read_mode = "transient"
        self.calls: list[dict[str, Any]] = []
        self.started = asyncio.Event()

    def actions(self) -> list[ActionDescriptor]:
        return [
            ActionDescriptor(
                name="write",
                public_name=_WRITE_ACTION,
                description="Write one synthetic value",
                input_schema={
                    "type": "object",
                    "properties": {
                        "value": {"type": "string"},
                        "idempotency_key": {"type": "string"},
                    },
                    "required": ["value", "idempotency_key"],
                    "additionalProperties": False,
                },
                requires_auth=True,
                is_side_effect=True,
                idempotency_mode="required",
                retry_class="transient",
                timeout_seconds=0.5,
            ),
            ActionDescriptor(
                name="inspect",
                public_name=_READ_ACTION,
                description="Inspect one synthetic value",
                input_schema={
                    "type": "object",
                    "properties": {"value": {"type": "string"}},
                    "required": ["value"],
                    "additionalProperties": False,
                },
                requires_auth=True,
                retry_class="transient",
                timeout_seconds=2.0,
            ),
        ]

    async def execute(self, action: str, **kwargs: Any) -> dict[str, Any]:
        self.calls.append({"action": action, **deepcopy(kwargs)})
        if action == "inspect":
            if self.read_mode == "transient":
                return {
                    "success": False,
                    "error_type": "transient",
                    "retryable": True,
                    "detail": _RAW_FAILURE,
                }
            return CapabilityResult.ok(value=kwargs["value"]).to_dict()

        if action != "write":
            raise AssertionError(f"Unexpected capability action: {action}")
        if self.write_mode == "raise":
            raise RuntimeError("RAW_WRITE_EXCEPTION_SENTINEL")
        if self.write_mode in {"timeout", "cancel"}:
            self.started.set()
            await asyncio.Event().wait()
        return CapabilityResult.ok(value=kwargs["value"]).to_dict()


def _run_id() -> str:
    return f"runtime-controls-{uuid4().hex}"


def _decision(
    run_id: str,
    action: str,
    *,
    capability: str | None = None,
    arguments: dict[str, Any] | None = None,
    content: str | None = None,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "schema_version": "v1",
        "decision_id": f"decision-{uuid4().hex}",
        "run_id": run_id,
        "action": action,
    }
    if action == "invoke":
        result.update(
            {
                "capability": capability,
                "capability_version": "v1",
                "arguments": deepcopy(arguments or {}),
            }
        )
    if content is not None:
        result["content"] = content
    return result


def _task_context(
    run_id: str,
    *,
    principal_id: int = 41,
) -> tuple[AgentTask, ExecutionContext]:
    thread_id = f"thread-{run_id}"
    task = AgentTask(
        user_id=principal_id,
        goal="Execute one controlled synthetic action and report its result",
        task_metadata={
            "run_id": run_id,
            "thread_id": thread_id,
            "model": "runtime-effect-controls",
            "messages": [
                {"role": "user", "content": "Run the requested controlled action"}
            ],
        },
    )
    context = ExecutionContext(
        principal_id=principal_id,
        run_id=run_id,
        trace_id=f"trace-{run_id}",
        thread_id=thread_id,
        capability_allowlist=frozenset({_READ_ACTION, _WRITE_ACTION}),
    )
    return task, context


def _gateway(
    run_id: str,
    *,
    action_arguments: dict[str, Any] | None = None,
    capability: str = _WRITE_ACTION,
    responds: bool = False,
) -> _ScriptedGateway:
    decisions = [
        _decision(
            run_id,
            "invoke",
            capability=capability,
            arguments=action_arguments,
        )
    ]
    if responds:
        decisions.append(_decision(run_id, "respond", content="Action completed"))
    return _ScriptedGateway(decisions)


def _runtime(
    session: AsyncSession,
    gateway: _ScriptedGateway,
    capability: _ControlsCapability,
    *,
    allow_side_effects: bool = True,
    checkpoint_store: SqliteCheckpointStore | None = None,
) -> AgentRuntime:
    registry = CapabilityRegistry()
    registry.register(capability)
    policy = PolicyEngine(allow_side_effects=allow_side_effects)
    dispatcher = Dispatcher(
        registry,
        policy_engine=policy,
        idempotency_store=SqlIdempotencyStore(session),
    )
    return AgentRuntime(
        None,
        checkpoint_store=checkpoint_store,
        model_gateway=gateway,
        dispatcher=dispatcher,
        run_store=RunStore(session),
        event_store=EventStore(session),
    )


async def _stream(
    runtime: AgentRuntime,
    task: AgentTask,
    context: ExecutionContext,
    *,
    cancellation: CancellationToken | None = None,
    approval: Approval | None = None,
) -> list[dict[str, Any]]:
    return [
        deepcopy(event)
        async for event in runtime.stream_decision(
            task,
            context=context,
            cancellation=cancellation,
            approval=approval,
        )
    ]


async def _run_events(session: AsyncSession, run_id: str) -> list[AgentRunEvent]:
    rows = await session.execute(
        select(AgentRunEvent)
        .where(AgentRunEvent.run_id == run_id)
        .order_by(cast(Any, AgentRunEvent.sequence))
    )
    return list(rows.scalars().all())


async def _invocations(session: AsyncSession, run_id: str) -> list[AgentInvocation]:
    rows = await session.execute(
        select(AgentInvocation)
        .where(AgentInvocation.run_id == run_id)
        .order_by(cast(Any, AgentInvocation.sequence))
    )
    return list(rows.scalars().all())


def _stream_terminal(events: list[dict[str, Any]]) -> dict[str, Any]:
    terminal = [
        event
        for event in events
        if event["type"]
        in {"run_completed", "run_failed", "run_cancelled", "run_timeout"}
    ]
    assert len(terminal) == 1
    assert isinstance(terminal[0].get("termination_reason"), str)
    assert terminal[0]["termination_reason"].strip()
    return terminal[0]


async def _canonical_terminal(
    session: AsyncSession,
    run_id: str,
) -> tuple[list[AgentRunEvent], AgentRunEvent]:
    events = await _run_events(session, run_id)
    terminal = [event for event in events if event.event_type in _TERMINAL_EVENTS]
    assert len(terminal) == 1
    payload = terminal[0].payload
    assert isinstance(payload.get("termination_reason"), str)
    assert payload["termination_reason"].strip()
    return events, terminal[0]


def _record(
    record_property: Any,
    *,
    scenario: str,
    database_name: str,
    model_calls: int,
    effect_calls: int,
    terminal_count: int,
    error_code: Any,
    retryable: bool,
    replay_write_count: int | None = None,
) -> None:
    record_property("scenario", scenario)
    record_property("database", database_name)
    record_property("model_calls", model_calls)
    record_property("effect_calls", effect_calls)
    record_property("terminal_count", terminal_count)
    record_property("error_code", str(error_code or "none"))
    record_property("retryable", retryable)
    if replay_write_count is not None:
        record_property("replay_write_count", replay_write_count)


async def _run_write(
    session: AsyncSession,
    capability: _ControlsCapability,
    *,
    value: str,
    key: str,
    principal_id: int = 41,
    approval: Approval | None = None,
    checkpoint_store: SqliteCheckpointStore | None = None,
) -> tuple[str, _ScriptedGateway, list[dict[str, Any]]]:
    run_id = _run_id()
    task, context = _task_context(run_id, principal_id=principal_id)
    gateway = _gateway(
        run_id,
        action_arguments={"value": value, "idempotency_key": key},
        responds=True,
    )
    events = await _stream(
        _runtime(
            session,
            gateway,
            capability,
            checkpoint_store=checkpoint_store,
        ),
        task,
        context,
        approval=approval
        or Approval(
            approval_id=f"approved-{run_id}",
            principal_id=principal_id,
            action="write",
        ),
    )
    return run_id, gateway, events


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.db
async def test_missing_approval_pauses_then_resumes_persisted_runtime_once(
    acceptance_database: tuple[str, AsyncSession],
    tmp_path: Any,
    record_property: Any,
) -> None:
    database_name, session = acceptance_database
    run_id = _run_id()
    task, context = _task_context(run_id)
    capability = _ControlsCapability()
    checkpoint = SqliteCheckpointStore(str(tmp_path / "approval-checkpoint.db"))
    key = f"approval-key-{uuid4().hex}"
    first_gateway = _gateway(
        run_id,
        action_arguments={"value": "approved-value", "idempotency_key": key},
    )

    first_events = await _stream(
        _runtime(session, first_gateway, capability, checkpoint_store=checkpoint),
        task,
        context,
    )
    assert first_events[-1]["type"] == "approval_required"
    assert not any(
        event["type"] in {"run_completed", "run_failed", "run_cancelled", "run_timeout"}
        for event in first_events
    )
    assert len(first_gateway.calls) == 1
    assert capability.calls == []
    run = await session.get(AgentRun, run_id)
    assert run is not None and run.status == "paused"
    paused_events = await _run_events(session, run_id)
    assert any(event.event_type == "run.paused" for event in paused_events)
    assert not any(event.event_type in _TERMINAL_EVENTS for event in paused_events)
    paused_invocations = await _invocations(session, run_id)
    assert len(paused_invocations) == 1
    assert paused_invocations[0].status == "denied"

    resumed_gateway = _ScriptedGateway(
        [_decision(run_id, "respond", content="Approval accepted")]
    )
    approved_runtime = _runtime(
        session,
        resumed_gateway,
        capability,
        checkpoint_store=checkpoint,
    )
    approval = Approval(
        approval_id=f"approval:{run_id}:{paused_invocations[0].invocation_id}",
        principal_id=41,
        action="write",
    )
    resumed_events = await _stream(
        approved_runtime,
        task,
        context,
        approval=approval,
    )
    assert _stream_terminal(resumed_events)["type"] == "run_completed"
    assert len(resumed_gateway.calls) == 1
    assert capability.calls == [
        {
            "action": "write",
            "value": "approved-value",
            "idempotency_key": key,
            "user_id": 41,
        }
    ]
    persisted_invocations = await _invocations(session, run_id)
    assert len(persisted_invocations) == 1
    assert persisted_invocations[0].status == "succeeded"
    assert persisted_invocations[0].error_code is None
    persisted_events, terminal = await _canonical_terminal(session, run_id)
    assert terminal.event_type == "run.succeeded"
    assert sum(event.event_type == "run.paused" for event in persisted_events) == 1

    replay_gateway = _ScriptedGateway([_decision(run_id, "respond", content="unused")])
    replay_events = await _stream(
        _runtime(
            session,
            replay_gateway,
            capability,
            checkpoint_store=checkpoint,
        ),
        task,
        context,
    )
    assert _stream_terminal(replay_events)["type"] == "run_completed"
    assert replay_gateway.calls == []
    assert len(capability.calls) == 1
    _record(
        record_property,
        scenario="genuine approval pause, restart, resume, and Run replay",
        database_name=database_name,
        model_calls=len(first_gateway.calls) + len(resumed_gateway.calls),
        effect_calls=len(capability.calls),
        terminal_count=1,
        error_code=terminal.payload.get("error_code"),
        retryable=False,
        replay_write_count=len(capability.calls),
    )


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.db
async def test_disabled_side_effect_policy_is_terminal_refusal(
    acceptance_database: tuple[str, AsyncSession],
    record_property: Any,
) -> None:
    database_name, session = acceptance_database
    run_id = _run_id()
    task, context = _task_context(run_id)
    capability = _ControlsCapability()
    gateway = _gateway(
        run_id,
        action_arguments={"value": "refused", "idempotency_key": "disabled-policy"},
    )
    events = await _stream(
        _runtime(
            session,
            gateway,
            capability,
            allow_side_effects=False,
        ),
        task,
        context,
    )
    terminal_stream = _stream_terminal(events)
    assert terminal_stream["type"] == "run_failed"
    assert terminal_stream["termination_reason"] == "policy_denied"
    assert not any(event["type"] == "approval_required" for event in events)
    assert len(gateway.calls) == 1
    assert capability.calls == []
    _, terminal = await _canonical_terminal(session, run_id)
    assert terminal.event_type == "run.failed"
    persisted_run = await session.get(AgentRun, run_id)
    assert persisted_run is not None
    assert persisted_run.status == "failed"
    invocation = (await _invocations(session, run_id))[0]
    assert invocation.status == "denied"
    call_end = next(event for event in events if event["type"] == "tool_call_end")
    assert call_end["retryable"] is False
    _record(
        record_property,
        scenario="side effects disabled with missing approval remains terminal",
        database_name=database_name,
        model_calls=len(gateway.calls),
        effect_calls=len(capability.calls),
        terminal_count=1,
        error_code=terminal.payload.get("error_code"),
        retryable=call_end["retryable"],
    )


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.db
@pytest.mark.parametrize("approval_case", ["denied", "wrong_principal", "wrong_action"])
async def test_invalid_trusted_approval_is_terminal_and_never_pauses(
    acceptance_database: tuple[str, AsyncSession],
    approval_case: str,
    record_property: Any,
) -> None:
    database_name, session = acceptance_database
    run_id = _run_id()
    task, context = _task_context(run_id)
    capability = _ControlsCapability()
    gateway = _gateway(
        run_id,
        action_arguments={"value": "denied", "idempotency_key": f"{approval_case}-key"},
    )
    approval = Approval(
        approval_id=f"approval-{approval_case}-{run_id}",
        approved=approval_case != "denied",
        principal_id=42 if approval_case == "wrong_principal" else 41,
        action="other" if approval_case == "wrong_action" else "write",
    )
    events = await _stream(
        _runtime(session, gateway, capability),
        task,
        context,
        approval=approval,
    )
    terminal_stream = _stream_terminal(events)
    assert terminal_stream["type"] == "run_failed"
    assert terminal_stream["termination_reason"] == "policy_denied"
    assert not any(event["type"] == "approval_required" for event in events)
    assert len(gateway.calls) == 1
    assert capability.calls == []
    persisted_events, terminal = await _canonical_terminal(session, run_id)
    assert terminal.event_type == "run.failed"
    assert not any(event.event_type == "run.paused" for event in persisted_events)
    invocation = (await _invocations(session, run_id))[0]
    assert invocation.status == "denied"
    call_end = next(event for event in events if event["type"] == "tool_call_end")
    assert call_end["retryable"] is False
    _record(
        record_property,
        scenario=f"{approval_case} approval refusal",
        database_name=database_name,
        model_calls=len(gateway.calls),
        effect_calls=len(capability.calls),
        terminal_count=1,
        error_code=terminal.payload.get("error_code"),
        retryable=call_end["retryable"],
    )


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.db
async def test_sql_idempotency_replay_conflict_and_principal_scope(
    acceptance_database: tuple[str, AsyncSession],
    record_property: Any,
) -> None:
    database_name, session = acceptance_database
    session.add(User(id=42, username="runtime-effect-controls-second-principal"))
    await session.commit()
    capability = _ControlsCapability()
    key = f"shared-key-{uuid4().hex}"
    results: list[tuple[str, list[dict[str, Any]], _ScriptedGateway]] = []
    for principal_id, value in (
        (41, "same"),
        (41, "same"),
        (41, "changed"),
        (42, "same"),
    ):
        run_id, gateway, events = await _run_write(
            session,
            capability,
            value=value,
            key=key,
            principal_id=principal_id,
        )
        results.append((run_id, events, gateway))

    terminals = [await _canonical_terminal(session, run_id) for run_id, _, _ in results]
    assert [terminal.event_type for _, terminal in terminals] == [
        "run.succeeded",
        "run.succeeded",
        "run.failed",
        "run.succeeded",
    ]
    assert [_stream_terminal(events)["type"] for _, events, _ in results] == [
        "run_completed",
        "run_completed",
        "run_failed",
        "run_completed",
    ]
    assert [len(await _invocations(session, run_id)) for run_id, _, _ in results] == [
        1,
        1,
        1,
        1,
    ]
    assert len(capability.calls) == 2
    assert [call["user_id"] for call in capability.calls] == [41, 42]
    conflict_end = next(
        event for event in results[2][1] if event["type"] == "tool_call_end"
    )
    assert conflict_end["error_code"] == "idempotency_conflict"
    assert conflict_end["retryable"] is False
    assert (
        len(
            {
                event["invocation_id"]
                for _, events, _ in results
                for event in events
                if event["type"] == "tool_call_start"
            }
        )
        == 4
    )
    _record(
        record_property,
        scenario="same key replay, argument conflict, and principal isolation",
        database_name=database_name,
        model_calls=sum(len(gateway.calls) for _, _, gateway in results),
        effect_calls=len(capability.calls),
        terminal_count=len(terminals),
        error_code=terminals[2][1].payload.get("error_code"),
        retryable=conflict_end["retryable"],
        replay_write_count=len(capability.calls),
    )


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.db
async def test_uncertain_write_failure_replays_attention_without_reexecution(
    acceptance_database: tuple[str, AsyncSession],
    record_property: Any,
) -> None:
    database_name, session = acceptance_database
    capability = _ControlsCapability(write_mode="raise")
    key = f"raise-key-{uuid4().hex}"
    first_run, first_gateway, first_events = await _run_write(
        session,
        capability,
        value="mutate-then-raise",
        key=key,
    )
    replay_run, replay_gateway, replay_events = await _run_write(
        session,
        capability,
        value="mutate-then-raise",
        key=key,
    )
    first_stream_terminal = _stream_terminal(first_events)
    replay_stream_terminal = _stream_terminal(replay_events)
    assert (
        first_stream_terminal["type"] == replay_stream_terminal["type"] == "run_failed"
    )
    assert first_stream_terminal["termination_reason"] == "attention_required"
    assert replay_stream_terminal["termination_reason"] == "attention_required"
    _, first_terminal = await _canonical_terminal(session, first_run)
    _, replay_terminal = await _canonical_terminal(session, replay_run)
    assert first_terminal.event_type == replay_terminal.event_type == "run.failed"
    assert len(capability.calls) == 1
    assert len(first_gateway.calls) == len(replay_gateway.calls) == 1
    assert _RAW_FAILURE not in json.dumps(first_events, ensure_ascii=False)
    assert "RAW_WRITE_EXCEPTION_SENTINEL" not in json.dumps(
        first_events, ensure_ascii=False
    )
    for events in (first_events, replay_events):
        call_end = next(event for event in events if event["type"] == "tool_call_end")
        assert call_end["retryable"] is False
    _record(
        record_property,
        scenario="mutate then raise is persisted and replayed as attention required",
        database_name=database_name,
        model_calls=len(first_gateway.calls) + len(replay_gateway.calls),
        effect_calls=len(capability.calls),
        terminal_count=2,
        error_code=first_terminal.payload.get("error_code"),
        retryable=False,
        replay_write_count=len(capability.calls),
    )


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.db
async def test_write_timeout_is_terminal_and_replay_does_not_execute_again(
    acceptance_database: tuple[str, AsyncSession],
    record_property: Any,
) -> None:
    database_name, session = acceptance_database
    capability = _ControlsCapability(write_mode="timeout")
    key = f"timeout-key-{uuid4().hex}"
    first_run, first_gateway, first_events = await _run_write(
        session,
        capability,
        value="timeout-after-start",
        key=key,
    )
    assert capability.started.is_set()
    first_stream_terminal = _stream_terminal(first_events)
    assert first_stream_terminal["type"] == "run_timeout"
    _, first_terminal = await _canonical_terminal(session, first_run)
    assert first_terminal.event_type == "run.failed"
    first_invocation = (await _invocations(session, first_run))[0]
    assert first_invocation.status == "timed_out"
    timeout_end = next(
        event for event in first_events if event["type"] == "tool_call_end"
    )
    assert timeout_end["status"] == "timeout"
    assert timeout_end["retryable"] is False

    replay_run, replay_gateway, replay_events = await _run_write(
        session,
        capability,
        value="timeout-after-start",
        key=key,
    )
    replay_stream_terminal = _stream_terminal(replay_events)
    assert replay_stream_terminal["type"] == "run_failed"
    assert replay_stream_terminal["termination_reason"] == "attention_required"
    _, replay_terminal = await _canonical_terminal(session, replay_run)
    assert replay_terminal.event_type == "run.failed"
    replay_end = next(
        event for event in replay_events if event["type"] == "tool_call_end"
    )
    assert replay_end["retryable"] is False
    assert len(capability.calls) == 1
    assert len(first_gateway.calls) == len(replay_gateway.calls) == 1
    _record(
        record_property,
        scenario="write timeout remains non-retryable and SQL replay is attention required",
        database_name=database_name,
        model_calls=len(first_gateway.calls) + len(replay_gateway.calls),
        effect_calls=len(capability.calls),
        terminal_count=2,
        error_code=first_terminal.payload.get("error_code"),
        retryable=timeout_end["retryable"],
        replay_write_count=len(capability.calls),
    )


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.db
async def test_inflight_write_cancellation_is_terminal_and_not_replayed(
    acceptance_database: tuple[str, AsyncSession],
    record_property: Any,
) -> None:
    database_name, session = acceptance_database
    capability = _ControlsCapability(write_mode="cancel")
    key = f"cancel-key-{uuid4().hex}"
    run_id = _run_id()
    task, context = _task_context(run_id)
    gateway = _gateway(
        run_id,
        action_arguments={"value": "cancel-after-start", "idempotency_key": key},
    )
    cancellation = CancellationToken()
    consumer = asyncio.create_task(
        _stream(
            _runtime(session, gateway, capability),
            task,
            context,
            cancellation=cancellation,
            approval=Approval(
                approval_id=f"approved-{run_id}",
                principal_id=41,
                action="write",
            ),
        )
    )
    try:
        await asyncio.wait_for(capability.started.wait(), timeout=5)
        cancellation.cancel()
        events = await asyncio.wait_for(consumer, timeout=5)
    finally:
        if not consumer.done():
            cancellation.cancel()
            consumer.cancel()
            await asyncio.gather(consumer, return_exceptions=True)
    terminal_stream = _stream_terminal(events)
    assert terminal_stream["type"] == "run_cancelled"
    _, terminal = await _canonical_terminal(session, run_id)
    assert terminal.event_type == "run.cancelled"
    cancelled_invocation = (await _invocations(session, run_id))[0]
    assert cancelled_invocation.status == "cancelled"
    cancel_end = next(event for event in events if event["type"] == "tool_call_end")
    assert cancel_end["status"] == "cancelled"
    assert cancel_end["retryable"] is False
    assert len(gateway.calls) == 1

    replay_run, replay_gateway, replay_events = await _run_write(
        session,
        capability,
        value="cancel-after-start",
        key=key,
    )
    replay_stream_terminal = _stream_terminal(replay_events)
    assert replay_stream_terminal["type"] == "run_failed"
    assert replay_stream_terminal["termination_reason"] == "attention_required"
    _, replay_terminal = await _canonical_terminal(session, replay_run)
    assert replay_terminal.event_type == "run.failed"
    replay_end = next(
        event for event in replay_events if event["type"] == "tool_call_end"
    )
    assert replay_end["retryable"] is False
    assert len(capability.calls) == 1
    assert len(replay_gateway.calls) == 1
    _record(
        record_property,
        scenario="in-flight write cancellation persists one terminal and blocks replay execution",
        database_name=database_name,
        model_calls=len(gateway.calls) + len(replay_gateway.calls),
        effect_calls=len(capability.calls),
        terminal_count=2,
        error_code=terminal.payload.get("error_code"),
        retryable=cancel_end["retryable"],
        replay_write_count=len(capability.calls),
    )


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.db
async def test_transient_read_failure_retries_only_in_an_explicit_new_run(
    acceptance_database: tuple[str, AsyncSession],
    record_property: Any,
) -> None:
    database_name, session = acceptance_database
    capability = _ControlsCapability()
    first_run = _run_id()
    first_task, first_context = _task_context(first_run)
    first_gateway = _gateway(
        first_run,
        action_arguments={"value": "read-value"},
        capability=_READ_ACTION,
    )
    first_events = await _stream(
        _runtime(session, first_gateway, capability),
        first_task,
        first_context,
    )
    first_stream_terminal = _stream_terminal(first_events)
    assert first_stream_terminal["type"] == "run_failed"
    assert first_stream_terminal["termination_reason"] == "transient"
    first_end = next(
        event for event in first_events if event["type"] == "tool_call_end"
    )
    assert first_end["error_code"] == "transient"
    assert first_end["retryable"] is True
    _, first_terminal = await _canonical_terminal(session, first_run)
    first_invocation = (await _invocations(session, first_run))[0]
    assert first_invocation.status == "failed"
    assert len(first_gateway.calls) == 1
    assert len(capability.calls) == 1
    assert _RAW_FAILURE not in json.dumps(first_events, ensure_ascii=False)

    capability.read_mode = "success"
    second_run = _run_id()
    second_task, second_context = _task_context(second_run)
    second_gateway = _gateway(
        second_run,
        action_arguments={"value": "read-value"},
        capability=_READ_ACTION,
        responds=True,
    )
    second_events = await _stream(
        _runtime(session, second_gateway, capability),
        second_task,
        second_context,
    )
    assert _stream_terminal(second_events)["type"] == "run_completed"
    _, second_terminal = await _canonical_terminal(session, second_run)
    assert second_terminal.event_type == "run.succeeded"
    second_invocation = (await _invocations(session, second_run))[0]
    assert second_invocation.status == "succeeded"
    assert first_invocation.invocation_id != second_invocation.invocation_id
    assert len(second_gateway.calls) == 2
    assert len(capability.calls) == 2
    _record(
        record_property,
        scenario="transient read retry occurs only in a fresh explicit Run",
        database_name=database_name,
        model_calls=len(first_gateway.calls) + len(second_gateway.calls),
        effect_calls=len(capability.calls),
        terminal_count=2,
        error_code=first_terminal.payload.get("error_code"),
        retryable=first_end["retryable"],
    )

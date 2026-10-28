"""A-L4-03: controlled failure, approval, cancellation and recovery paths."""

from __future__ import annotations

from copy import deepcopy
from typing import Any
from uuid import uuid4

import pytest
from sqlmodel.ext.asyncio.session import AsyncSession

from app.capabilities.base import BaseCapability
from app.capabilities.registry import CapabilityRegistry
from app.capabilities.types import ActionDescriptor, CapabilityResult
from app.evaluation.scripted_llm import (
    ObservationExpectation,
    ScriptedLLM,
    ScriptedStep,
)
from app.harness.budget import CancellationToken
from app.harness.checkpoint import SqliteCheckpointStore
from app.harness.contracts import ExecutionContext
from app.harness.execution import build_runtime
from app.harness.policy import Approval
from app.harness.task import AgentTask
from app.models import User
from app.schemas.user import UserRead
from tests.harness_support import harness_task

_READ = "failure_fixture.read_fail"
_WRITE = "failure_fixture.write"
_TERMINALS = {"run_completed", "run_failed", "run_cancelled", "run_timeout"}
_MESSAGES = [{"role": "user", "content": "Exercise the controlled failure fixture"}]

pytestmark = [pytest.mark.integration, pytest.mark.db]


class _FailureCapability(BaseCapability):
    name = "failure_fixture"
    description = "Controlled failure, approval and unknown-outcome capability"

    def __init__(self, *, write_mode: str = "ok") -> None:
        self.write_mode = write_mode
        self.calls: list[dict[str, Any]] = []
        self.sink: list[str] = []

    def actions(self) -> list[ActionDescriptor]:
        common: dict[str, Any] = {
            "requires_auth": True,
            "input_schema": {
                "type": "object",
                "properties": {
                    "value": {"type": "string"},
                    "idempotency_key": {"type": "string"},
                },
                "required": ["value"],
            },
        }
        return [
            ActionDescriptor(
                name="read_fail",
                public_name=_READ,
                description="Return a controlled read failure",
                is_side_effect=False,
                **common,
            ),
            ActionDescriptor(
                name="write",
                public_name=_WRITE,
                description="Controlled side effect",
                is_side_effect=True,
                approval_required=True,
                idempotency_mode="required",
                **common,
            ),
        ]

    async def execute(self, action: str, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(deepcopy(kwargs))
        if action == "read_fail":
            return CapabilityResult.fail(
                "read unavailable", error_type="read_failure"
            ).to_dict()
        assert action == "write"
        if self.write_mode == "unknown":
            self.sink.append(str(kwargs["value"]))
            return CapabilityResult.fail(
                "operation state unknown", error_type="attention_required"
            ).to_dict()
        self.sink.append(str(kwargs["value"]))
        return CapabilityResult.ok(value=kwargs["value"]).to_dict()


@pytest.fixture
async def principal(db_session: AsyncSession) -> tuple[AsyncSession, UserRead]:
    row = User(username=f"failure-path-{uuid4().hex}")
    db_session.add(row)
    await db_session.commit()
    await db_session.refresh(row)
    return db_session, UserRead.model_validate(row)


def _run_id(label: str) -> str:
    return f"failure-{label}-{uuid4().hex}"


def _invoke(run_id: str, decision_id: str, action: str, **arguments: Any):
    return {
        "schema_version": "v1",
        "decision_id": decision_id,
        "run_id": run_id,
        "action": "invoke",
        "capability": action,
        "capability_version": "v1",
        "arguments": arguments,
    }


def _respond(run_id: str, decision_id: str, content: str):
    return {
        "schema_version": "v1",
        "decision_id": decision_id,
        "run_id": run_id,
        "action": "respond",
        "content": content,
    }


def _context(run_id: str, user_id: int, allowlist: set[str]) -> ExecutionContext:
    return ExecutionContext(
        principal_id=user_id,
        run_id=run_id,
        trace_id=f"trace-{run_id}",
        thread_id=f"thread-{run_id}",
        capability_allowlist=frozenset(allowlist),
    )


def _task(run_id: str, user_id: int) -> AgentTask:
    return harness_task(
        user_id=user_id,
        goal="Exercise controlled failures",
        metadata={
            "run_id": run_id,
            "trace_id": f"trace-{run_id}",
            "thread_id": f"thread-{run_id}",
            "model": "scripted-v1",
            "messages": _MESSAGES,
        },
    )


def _runtime(
    session: AsyncSession,
    user: UserRead,
    capability: _FailureCapability,
    gateway: ScriptedLLM,
    *,
    allow_side_effects: bool = True,
    checkpoint_store: SqliteCheckpointStore | None = None,
):
    registry = CapabilityRegistry()
    registry.register(capability)
    return build_runtime(
        session=session,
        user=user,
        registry=registry,
        model_gateway=gateway,
        trace_store=None,
        durable=True,
        allow_side_effects=allow_side_effects,
        checkpoint_store=checkpoint_store,
    )


async def _events(
    runtime: Any,
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


def _terminal(events: list[dict[str, Any]]) -> dict[str, Any]:
    terminals = [event for event in events if event["type"] in _TERMINALS]
    assert len(terminals) == 1
    return terminals[0]


@pytest.mark.asyncio
async def test_read_only_error_is_fed_back_and_run_continues(
    principal: tuple[AsyncSession, UserRead],
) -> None:
    session, user = principal
    run_id = _run_id("read-continue")
    capability = _FailureCapability()
    gateway = ScriptedLLM(
        [
            ScriptedStep(
                decision=_invoke(run_id, "read-1", _READ, value="x"),
                expect=ObservationExpectation(tool_results=0),
            ),
            ScriptedStep(
                decision=_respond(run_id, "read-final", "Recovered safely"),
                expect=ObservationExpectation(
                    tool_results=1,
                    last_tool_result={"safe_output": {"error_type": "read_failure"}},
                ),
            ),
        ]
    )
    runtime = _runtime(session, user, capability, gateway)

    events = await _events(
        runtime,
        _task(run_id, user.id),
        _context(run_id, user.id, {_READ}),
    )

    assert _terminal(events)["type"] == "run_completed"
    assert len(gateway.calls) == 2
    assert capability.calls == [{"value": "x", "user_id": user.id}]
    assert gateway.calls[1].tool_results[0]["safe_output"]["error_type"] == (
        "read_failure"
    )
    run = await runtime.run_store.get(run_id, user_id=user.id)
    assert run is not None and run.status == "succeeded"


@pytest.mark.asyncio
async def test_policy_denial_is_terminal_without_capability_execution(
    principal: tuple[AsyncSession, UserRead],
) -> None:
    session, user = principal
    run_id = _run_id("denied")
    capability = _FailureCapability()
    gateway = ScriptedLLM(
        [
            ScriptedStep(
                decision=_invoke(run_id, "read-denied", _READ, value="x"),
                expect=ObservationExpectation(tool_results=0),
            )
        ]
    )
    runtime = _runtime(session, user, capability, gateway)

    events = await _events(
        runtime,
        _task(run_id, user.id),
        _context(run_id, user.id, {"other.capability"}),
    )

    assert _terminal(events)["type"] == "run_failed"
    assert capability.calls == []
    tool_end = next(event for event in events if event["type"] == "tool_call_end")
    assert tool_end["status"] == "denied"
    assert tool_end["error_code"] == "policy_denied"
    failed_run = await runtime.run_store.get(run_id, user_id=user.id)
    assert failed_run is not None and failed_run.status == "failed"


@pytest.mark.asyncio
async def test_write_requires_approval_and_runs_once_after_resume(
    principal: tuple[AsyncSession, UserRead],
    tmp_path: Any,
) -> None:
    session, user = principal
    run_id = _run_id("approval")
    capability = _FailureCapability()
    key = f"approval-key-{uuid4().hex}"
    checkpoint = SqliteCheckpointStore(str(tmp_path / "approval.db"))
    first_gateway = ScriptedLLM(
        [
            ScriptedStep(
                decision=_invoke(
                    run_id,
                    "write-1",
                    _WRITE,
                    value="approved",
                    idempotency_key=key,
                ),
                expect=ObservationExpectation(tool_results=0),
            )
        ]
    )
    first_runtime = _runtime(
        session,
        user,
        capability,
        first_gateway,
        checkpoint_store=checkpoint,
    )
    task = _task(run_id, user.id)
    context = _context(run_id, user.id, {_WRITE})

    first = await _events(first_runtime, task, context)

    assert first[-1]["type"] == "approval_required"
    assert not any(event["type"] in _TERMINALS for event in first)
    assert capability.calls == []
    run = await first_runtime.run_store.get(run_id, user_id=user.id)
    assert run is not None and run.status == "paused"

    resumed_gateway = ScriptedLLM(
        [
            ScriptedStep(
                decision=_respond(run_id, "approval-final", "Approved and done"),
                expect=ObservationExpectation(tool_results=1),
            )
        ]
    )
    resumed_runtime = _runtime(
        session,
        user,
        capability,
        resumed_gateway,
        checkpoint_store=checkpoint,
    )
    approval = Approval(
        approval_id=f"approval:{run_id}:write-1",
        principal_id=user.id,
        action="write",
    )
    resumed = await _events(
        resumed_runtime,
        task,
        context,
        approval=approval,
    )

    assert _terminal(resumed)["type"] == "run_completed"
    assert capability.sink == ["approved"]
    assert capability.calls == [
        {"value": "approved", "idempotency_key": key, "user_id": user.id}
    ]
    assert len(resumed_gateway.calls) == 1


@pytest.mark.asyncio
async def test_cancellation_stops_before_any_side_effect(
    principal: tuple[AsyncSession, UserRead],
) -> None:
    session, user = principal
    run_id = _run_id("cancelled")
    capability = _FailureCapability()
    gateway = ScriptedLLM(
        [
            ScriptedStep(
                decision=_invoke(
                    run_id,
                    "write-cancelled",
                    _WRITE,
                    value="never",
                    idempotency_key=f"cancel-{uuid4().hex}",
                )
            )
        ]
    )
    runtime = _runtime(session, user, capability, gateway)
    token = CancellationToken()
    token.cancel()

    events = await _events(
        runtime,
        _task(run_id, user.id),
        _context(run_id, user.id, {_WRITE}),
        cancellation=token,
    )

    assert _terminal(events)["type"] == "run_cancelled"
    assert capability.calls == []
    assert capability.sink == []
    assert gateway.calls == []


@pytest.mark.asyncio
async def test_unknown_write_outcome_is_attention_and_never_duplicated(
    principal: tuple[AsyncSession, UserRead],
) -> None:
    session, user = principal
    capability = _FailureCapability(write_mode="unknown")
    key = f"unknown-key-{uuid4().hex}"

    async def run_once(label: str) -> tuple[list[dict[str, Any]], Any]:
        run_id = _run_id(label)
        gateway = ScriptedLLM(
            [
                ScriptedStep(
                    decision=_invoke(
                        run_id,
                        f"write-{label}",
                        _WRITE,
                        value="one-shot",
                        idempotency_key=key,
                    ),
                    expect=ObservationExpectation(tool_results=0),
                )
            ]
        )
        runtime = _runtime(session, user, capability, gateway)
        events = await _events(
            runtime,
            _task(run_id, user.id),
            _context(run_id, user.id, {_WRITE}),
            approval=Approval(
                approval_id=f"approval:{run_id}:write-{label}",
                principal_id=user.id,
                action="write",
            ),
        )
        return events, runtime

    first, first_runtime = await run_once("unknown-first")
    second, second_runtime = await run_once("unknown-replay")

    for events in (first, second):
        terminal = _terminal(events)
        assert terminal["type"] == "run_failed"
        assert terminal["termination_reason"] == "attention_required"
    assert capability.sink == ["one-shot"]
    assert len(capability.calls) == 1
    first_run = await first_runtime.run_store.get(first[0]["run_id"], user_id=user.id)
    second_run = await second_runtime.run_store.get(
        second[0]["run_id"], user_id=user.id
    )
    assert first_run is not None and first_run.status == "failed"
    assert second_run is not None and second_run.status == "failed"

"""Shared primary composition recovers reads without test-only task metadata."""

from uuid import uuid4
from typing import Any

import pytest
from sqlmodel.ext.asyncio.session import AsyncSession

from app.capabilities.registry import CapabilityRegistry
from app.evaluation.scripted_llm import (
    ObservationExpectation,
    ScriptedLLM,
    ScriptedStep,
)
from app.harness.contracts import ExecutionContext
from app.harness.execution import build_runtime
from app.harness.recovery import RecoveryPolicy
from app.harness.recovery import recoverable_read_failure
from app.harness.contracts import InvocationResult
from app.harness.task import AgentTask
from tests.acceptance.test_runtime_failure_paths import _FailureCapability, _READ


@pytest.mark.asyncio
@pytest.mark.parametrize("repeat", [False, True])
@pytest.mark.parametrize("stream", [False, True])
@pytest.mark.parametrize("disabled", [False, True])
async def test_primary_default_recovers_read_and_blocks_unchanged_retry(
    db_session: AsyncSession, repeat: bool, stream: bool, disabled: bool
) -> None:
    from app.models import User
    from app.schemas.user import UserRead

    row = User(username=f"recovery-{uuid4().hex}")
    db_session.add(row)
    await db_session.commit()
    await db_session.refresh(row)
    assert row.id is not None
    run_id = uuid4().hex
    invoke = {
        "schema_version": "v1",
        "decision_id": "read-1",
        "run_id": run_id,
        "action": "invoke",
        "capability": _READ,
        "capability_version": "v1",
        "arguments": {"value": "x"},
    }
    second = (
        {**invoke, "decision_id": "read-2"}
        if repeat
        else {
            "schema_version": "v1",
            "decision_id": "done",
            "run_id": run_id,
            "action": "respond",
            "content": "Read failed; explained safely",
        }
    )
    gateway = ScriptedLLM(
        [
            ScriptedStep(
                decision=invoke, expect=ObservationExpectation(tool_results=0)
            ),
            ScriptedStep(
                decision=second,
                expect=ObservationExpectation(
                    tool_results=1,
                    last_tool_result={"safe_output": {"error_type": "read_failure"}},
                ),
            ),
        ]
    )
    capability = _FailureCapability()
    registry = CapabilityRegistry()
    registry.register(capability)
    options: dict[str, Any] = {"recovery_policy": RecoveryPolicy()} if disabled else {}
    runtime = build_runtime(
        session=db_session,
        user=UserRead.model_validate(row),
        registry=registry,
        model_gateway=gateway,
        trace_store=None,
        **options,
    )
    task = AgentTask(
        user_id=row.id,
        goal="Recover",
        task_metadata={
            "run_id": run_id,
            "messages": [{"role": "user", "content": "Read x"}],
            # A trusted factory policy takes precedence over legacy metadata.
            **({"continue_on_read_only_error": True} if disabled else {}),
        },
    )
    context = ExecutionContext(
        principal_id=row.id,
        run_id=run_id,
        trace_id=run_id,
        capability_allowlist=frozenset({_READ}),
    )
    if stream:
        events = [item async for item in runtime.stream_decision(task, context=context)]
        terminal = events[-1]
        assert terminal["type"] == (
            "run_failed" if repeat or disabled else "run_completed"
        )
        if repeat and not disabled:
            assert terminal["termination_reason"] == "repeated_failed_action"
    else:
        result = await runtime.execute_decision(task, context=context)
        assert result.status == ("failed" if repeat or disabled else "completed")
        if repeat and not disabled:
            assert result.termination_reason == "repeated_failed_action"
    assert len(gateway.calls) == (1 if disabled else 2)
    assert len(capability.calls) == 1


@pytest.mark.parametrize(
    "kwargs",
    [
        {"read_only_errors": "true"},
        {"max_repeated_failures": 0},
        {"max_repeated_failures": True},
    ],
)
def test_invalid_recovery_policy_is_rejected(kwargs: dict) -> None:
    with pytest.raises(ValueError):
        RecoveryPolicy(**kwargs)


@pytest.mark.parametrize(
    "code",
    [
        "forbidden",
        "not_found",
        "internal",
        "invalid_output",
        "qb_authentication_failed",
        "policy_denied",
        "attention_required",
        "unclassified_error",
    ],
)
def test_unclassified_security_and_contract_errors_remain_terminal(code: str) -> None:
    result = InvocationResult(invocation_id="fixture", status="failed", error_code=code)
    assert not recoverable_read_failure(result)


@pytest.mark.asyncio
async def test_failed_read_counter_survives_approval_checkpoint_resume(
    db_session: AsyncSession, tmp_path
) -> None:
    from app.harness.checkpoint import SqliteCheckpointStore
    from app.harness.policy import Approval
    from app.models import User
    from app.schemas.user import UserRead
    from tests.acceptance.test_runtime_failure_paths import _WRITE, _invoke, _runtime

    row = User(username=f"checkpoint-recovery-{uuid4().hex}")
    db_session.add(row)
    await db_session.commit()
    await db_session.refresh(row)
    assert row.id is not None
    user = UserRead.model_validate(row)
    run_id = uuid4().hex
    capability = _FailureCapability()
    checkpoint = SqliteCheckpointStore(str(tmp_path / "recovery.db"))
    context = ExecutionContext(
        principal_id=row.id,
        run_id=run_id,
        trace_id=run_id,
        thread_id=run_id,
        capability_allowlist=frozenset({_READ, _WRITE}),
    )
    task = AgentTask(
        user_id=row.id,
        goal="Read then approve",
        task_metadata={
            "run_id": run_id,
            "thread_id": run_id,
            "messages": [{"role": "user", "content": "Read then approve"}],
        },
    )
    first = ScriptedLLM(
        [
            ScriptedStep(decision=_invoke(run_id, "read-1", _READ, value="x")),
            ScriptedStep(
                decision=_invoke(
                    run_id,
                    "write-1",
                    _WRITE,
                    value="approved",
                    idempotency_key="checkpoint-fixture-key",
                ),
                expect=ObservationExpectation(tool_results=1),
            ),
        ]
    )
    try:
        runtime = _runtime(
            db_session, user, capability, first, checkpoint_store=checkpoint
        )
        events = [
            event async for event in runtime.stream_decision(task, context=context)
        ]
        assert events[-1]["type"] == "approval_required"
        stored = await checkpoint.load(run_id, run_id)
        assert stored is not None
        assert list(stored.context["failed_read_actions"].values()) == [1]
        second = ScriptedLLM(
            [
                ScriptedStep(
                    decision=_invoke(run_id, "read-2", _READ, value="x"),
                    expect=ObservationExpectation(tool_results=2),
                )
            ]
        )
        resumed = _runtime(
            db_session, user, capability, second, checkpoint_store=checkpoint
        )
        events = [
            event
            async for event in resumed.stream_decision(
                task,
                context=context,
                approval=Approval(
                    approval_id=f"approval:{run_id}:write-1",
                    principal_id=row.id,
                    action="write",
                ),
            )
        ]
        assert events[-1]["termination_reason"] == "repeated_failed_action"
        assert len(capability.calls) == 2
        assert capability.sink == ["approved"]
    finally:
        await checkpoint.close()

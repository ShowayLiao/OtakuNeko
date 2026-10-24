"""Real Runtime-path acceptance for observation-aware ScriptedLLM decisions."""

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
    ExpectedMessage,
    ObservationExpectation,
    ScriptedLLM,
    ScriptedStep,
)
from app.harness.contracts import ExecutionContext, RunRequest
from app.harness.debug import DebugRunReport, run_debug
from app.harness.execution import build_runtime
from app.models import User
from app.schemas.user import UserRead

_ACTION = "scripted_fixture.inspect"
_TERMINAL_TYPES = {"run.succeeded", "run.failed", "run.cancelled"}

pytestmark = [pytest.mark.integration, pytest.mark.db]


class _ObservationCapability(BaseCapability):
    name = "scripted_fixture"
    description = "Synthetic read-only capability for ScriptedLLM acceptance"

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def actions(self) -> list[ActionDescriptor]:
        return [
            ActionDescriptor(
                name="inspect",
                public_name=_ACTION,
                description="Return the observed fixture value",
                input_schema={
                    "type": "object",
                    "properties": {"value": {"type": "string"}},
                    "required": ["value"],
                    "additionalProperties": False,
                },
                requires_auth=True,
            )
        ]

    async def execute(self, action: str, **kwargs: Any) -> dict[str, Any]:
        assert action == "inspect"
        self.calls.append(deepcopy(kwargs))
        return CapabilityResult.ok(value=f"observed:{kwargs['value']}").to_dict()


@pytest.fixture
async def principal(db_session: AsyncSession) -> tuple[AsyncSession, UserRead]:
    row = User(id=71, username=f"scripted-llm-{uuid4().hex}")
    db_session.add(row)
    await db_session.commit()
    await db_session.refresh(row)
    return db_session, UserRead.model_validate(row)


def _run_id(label: str) -> str:
    return f"scripted-llm-{label}-{uuid4().hex}"


def _invoke(decision_id: str, value: str) -> dict[str, Any]:
    return {
        "schema_version": "v1",
        "decision_id": decision_id,
        "action": "invoke",
        "capability": _ACTION,
        "capability_version": "v1",
        "arguments": {"value": value},
    }


async def _run(
    runtime: Any,
    *,
    run_id: str,
    principal_id: int,
) -> DebugRunReport:
    return await run_debug(
        RunRequest(
            run_id=run_id,
            goal="Use the fixture capability and report its observations",
            messages=[{"role": "user", "content": "Inspect the requested values"}],
            model="scripted-v1",
        ),
        ExecutionContext(
            principal_id=principal_id,
            run_id=run_id,
            trace_id=f"trace-{run_id}",
            thread_id=f"thread-{run_id}",
            capability_allowlist=frozenset({_ACTION}),
        ),
        runtime=runtime,
    )


def _runtime(
    session: AsyncSession,
    user: UserRead,
    capability: _ObservationCapability,
    gateway: ScriptedLLM,
) -> Any:
    registry = CapabilityRegistry()
    registry.register(capability)
    return build_runtime(
        session=session,
        user=user,
        registry=registry,
        model_gateway=gateway,
        trace_store=None,
        durable=True,
        allow_side_effects=False,
    )


def _terminal(report: DebugRunReport) -> Any:
    terminals = [
        event for event in report.events if event.event_type in _TERMINAL_TYPES
    ]
    assert len(terminals) == 1
    return terminals[0]


@pytest.mark.asyncio
async def test_scripted_llm_observes_feedback_then_derives_next_decision(
    principal: tuple[AsyncSession, UserRead],
) -> None:
    session, user = principal
    capability = _ObservationCapability()
    run_id = _run_id("derive")

    def derived_invoke(observation):
        observed = observation.last_tool_result
        assert observed is not None
        value = observed["safe_output"]["value"]
        return {
            **_invoke("inspect-derived", f"derived-from:{value}"),
            "run_id": observation.run_id,
        }

    def report(observation):
        observed = observation.last_tool_result
        assert observed is not None
        value = observed["safe_output"]["value"]
        return {
            "schema_version": "v1",
            "decision_id": "report-observations",
            "run_id": observation.run_id,
            "action": "respond",
            "content": f"Observed {value}",
        }

    gateway = ScriptedLLM(
        [
            ScriptedStep(
                decision={**_invoke("inspect-seed", "seed"), "run_id": run_id},
                expect=ObservationExpectation(
                    tool_results=0,
                    context={"schema_version": "v1", "run_state": "running"},
                    run_id=run_id,
                    trace_id=f"trace-{run_id}",
                ),
            ),
            ScriptedStep(
                decision=derived_invoke,
                expect=ObservationExpectation(
                    tool_results=1,
                    last_tool_result={
                        "safe_output": {"value": "observed:seed"},
                    },
                    history_contains=(ExpectedMessage("assistant", "inspect-seed"),),
                    context={"run_state": "running"},
                    run_id=run_id,
                    trace_id=f"trace-{run_id}",
                ),
            ),
            ScriptedStep(
                decision=report,
                expect=ObservationExpectation(
                    tool_results=2,
                    last_tool_result={
                        "safe_output": {"value": "observed:derived-from:observed:seed"},
                    },
                    message_count=5,
                    message_roles=(
                        "user",
                        "assistant",
                        "user",
                        "assistant",
                        "user",
                    ),
                ),
            ),
        ]
    )
    runtime = _runtime(session, user, capability, gateway)

    report_result = await _run(runtime, run_id=run_id, principal_id=user.id)

    assert report_result.status == "succeeded"
    assert _terminal(report_result).event_type == "run.succeeded"
    assert [item["value"] for item in capability.calls] == [
        "seed",
        "derived-from:observed:seed",
    ]
    assert all(item["user_id"] == user.id for item in capability.calls)
    assert gateway.observation_summary() == {
        "calls": 3,
        "history_messages": 1 + 3 + 5,
        "tool_results": 0 + 1 + 2,
        "context_snapshots": 3,
        "expectations_verified": 3,
        "observation_failures": 0,
    }
    assert len([e for e in report_result.events if e.event_type == "model_call"]) == 3
    assert (
        len([e for e in report_result.events if e.event_type == "tool_call_start"]) == 2
    )
    assert (
        len([e for e in report_result.events if e.event_type == "tool_call_end"]) == 2
    )


@pytest.mark.asyncio
async def test_missing_feedback_fails_on_real_runtime_path(
    principal: tuple[AsyncSession, UserRead],
) -> None:
    session, user = principal
    capability = _ObservationCapability()
    run_id = _run_id("missing-feedback")
    gateway = ScriptedLLM(
        [
            ScriptedStep(text="{not valid json"),
            ScriptedStep(
                decision={**_invoke("inspect-unexpected", "seed"), "run_id": run_id},
                expect=ObservationExpectation(tool_results=1),
            ),
        ]
    )
    runtime = _runtime(session, user, capability, gateway)

    report_result = await _run(runtime, run_id=run_id, principal_id=user.id)

    assert report_result.status == "failed"
    assert _terminal(report_result).event_type == "run.failed"
    assert capability.calls == []
    assert len(gateway.calls) == 2
    assert gateway.calls[1].tool_results == ()
    assert any(
        "expected 1 tool result" in failure for failure in gateway.observation_failures
    )


@pytest.mark.asyncio
async def test_wrong_feedback_fails_on_real_runtime_path(
    principal: tuple[AsyncSession, UserRead],
) -> None:
    session, user = principal
    capability = _ObservationCapability()
    run_id = _run_id("wrong-feedback")
    gateway = ScriptedLLM(
        [
            ScriptedStep(
                decision={**_invoke("inspect-seed", "seed"), "run_id": run_id}
            ),
            ScriptedStep(
                decision={**_invoke("inspect-unexpected", "other"), "run_id": run_id},
                expect=ObservationExpectation(
                    tool_results=1,
                    last_tool_result={
                        "safe_output": {"value": "observed:other"},
                    },
                ),
            ),
        ]
    )
    runtime = _runtime(session, user, capability, gateway)

    report_result = await _run(runtime, run_id=run_id, principal_id=user.id)

    assert report_result.status == "failed"
    assert [item["value"] for item in capability.calls] == ["seed"]
    assert len(gateway.calls) == 2
    assert any(
        "last tool result.safe_output.value" in failure
        for failure in gateway.observation_failures
    )


@pytest.mark.asyncio
async def test_wrong_context_fails_on_real_runtime_path(
    principal: tuple[AsyncSession, UserRead],
) -> None:
    session, user = principal
    capability = _ObservationCapability()
    run_id = _run_id("wrong-context")
    gateway = ScriptedLLM(
        [
            ScriptedStep(
                decision={**_invoke("inspect-seed", "seed"), "run_id": run_id},
                expect=ObservationExpectation(
                    context={"run_state": "completed"},
                ),
            )
        ]
    )
    runtime = _runtime(session, user, capability, gateway)

    report_result = await _run(runtime, run_id=run_id, principal_id=user.id)

    assert report_result.status == "failed"
    assert capability.calls == []
    assert any(
        "context.run_state" in failure for failure in gateway.observation_failures
    )


@pytest.mark.asyncio
async def test_missing_history_message_fails_on_real_runtime_path(
    principal: tuple[AsyncSession, UserRead],
) -> None:
    session, user = principal
    capability = _ObservationCapability()
    run_id = _run_id("wrong-history")
    gateway = ScriptedLLM(
        [
            ScriptedStep(
                decision={**_invoke("inspect-seed", "seed"), "run_id": run_id},
                expect=ObservationExpectation(
                    history_contains=(
                        ExpectedMessage("assistant", "missing-decision"),
                    ),
                ),
            )
        ]
    )
    runtime = _runtime(session, user, capability, gateway)

    report_result = await _run(runtime, run_id=run_id, principal_id=user.id)

    assert report_result.status == "failed"
    assert capability.calls == []
    assert any(
        "missing-decision" in failure for failure in gateway.observation_failures
    )

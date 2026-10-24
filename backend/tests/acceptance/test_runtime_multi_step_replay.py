"""A-L4-02: only the LLM is replaced; real Runtime path and replay."""

from __future__ import annotations

from copy import deepcopy
import json
from typing import Any, AsyncIterator
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
from app.harness.debug import run_debug
from app.harness.execution import build_runtime
from app.harness.model_gateway import ModelGateway
from app.harness.model_types import ModelCallResult
from app.harness.task import AgentTask
from app.models import User
from app.schemas.user import UserRead

_ACTION = "replay_fixture.inspect"
_GOAL = "Inspect two values and report the derived observation"
_MESSAGES = [{"role": "user", "content": "Inspect the fixture values"}]

pytestmark = [pytest.mark.integration, pytest.mark.db]


class _ReplayCapability(BaseCapability):
    name = "replay_fixture"
    description = "Synthetic read-only capability for the multi-step replay check"

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


class _ExplodingGateway(ModelGateway):
    """Fail loudly if replay reaches the model provider."""

    def __init__(self) -> None:
        self.calls = 0

    async def infer(self, **_kwargs: Any) -> ModelCallResult:
        self.calls += 1
        raise AssertionError("replay re-invoked the model")

    async def stream_infer(self, **_kwargs: Any) -> AsyncIterator[Any]:
        self.calls += 1
        raise AssertionError("replay re-invoked the model")
        yield  # pragma: no cover

    async def synthesize(self, **_kwargs: Any) -> str:
        raise AssertionError("replay must not synthesize")

    async def synthesize_result(self, **_kwargs: Any) -> ModelCallResult:
        raise AssertionError("replay must not synthesize")


def _invoke(decision_id: str, value: str, run_id: str) -> dict[str, Any]:
    return {
        "schema_version": "v1",
        "decision_id": decision_id,
        "run_id": run_id,
        "action": "invoke",
        "capability": _ACTION,
        "capability_version": "v1",
        "arguments": {"value": value},
    }


def _context(run_id: str, user_id: int) -> ExecutionContext:
    return ExecutionContext(
        principal_id=user_id,
        run_id=run_id,
        trace_id=f"trace-{run_id}",
        thread_id=f"thread-{run_id}",
        capability_allowlist=frozenset({_ACTION}),
    )


def _request(run_id: str) -> RunRequest:
    return RunRequest(
        run_id=run_id,
        goal=_GOAL,
        messages=_MESSAGES,
        model="scripted-v1",
    )


def _task(run_id: str, user_id: int) -> AgentTask:
    return AgentTask(
        user_id=user_id,
        goal=_GOAL,
        task_metadata={
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
    capability: _ReplayCapability,
    gateway: ModelGateway,
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
        allow_side_effects=False,
    )


def _script(run_id: str) -> ScriptedLLM:
    def derived(observation) -> dict[str, Any]:
        observed = observation.last_tool_result
        assert observed is not None
        return _invoke(
            "step-2-derive",
            f"derived-from:{observed['safe_output']['value']}",
            run_id,
        )

    def report(observation) -> dict[str, Any]:
        observed = observation.last_tool_result
        assert observed is not None
        return {
            "schema_version": "v1",
            "decision_id": "step-3-report",
            "run_id": observation.run_id,
            "action": "respond",
            "content": f"Observed {observed['safe_output']['value']}",
        }

    return ScriptedLLM(
        [
            ScriptedStep(
                decision=_invoke("step-1-seed", "seed", run_id),
                expect=ObservationExpectation(
                    tool_results=0,
                    context={"schema_version": "v1", "run_state": "running"},
                    run_id=run_id,
                    trace_id=f"trace-{run_id}",
                ),
            ),
            ScriptedStep(
                decision=derived,
                expect=ObservationExpectation(
                    tool_results=1,
                    last_tool_result={"safe_output": {"value": "observed:seed"}},
                    history_contains=(ExpectedMessage("assistant", "step-1-seed"),),
                ),
            ),
            ScriptedStep(
                decision=report,
                expect=ObservationExpectation(
                    tool_results=2,
                    last_tool_result={
                        "safe_output": {"value": "observed:derived-from:observed:seed"}
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


@pytest.mark.asyncio
async def test_multi_step_real_path_completes_and_replays(
    db_session: AsyncSession,
) -> None:
    run_id = f"multi-step-{uuid4().hex}"
    user_row = User(id=81, username=f"runtime-replay-{uuid4().hex}")
    db_session.add(user_row)
    await db_session.commit()
    await db_session.refresh(user_row)
    user = UserRead.model_validate(user_row)
    capability = _ReplayCapability()
    gateway = _script(run_id)
    runtime = _runtime(db_session, user, capability, gateway)
    context = _context(run_id, user.id)

    report = await run_debug(_request(run_id), context, runtime=runtime)

    assert report.status == "succeeded"
    assert [call["value"] for call in capability.calls] == [
        "seed",
        "derived-from:observed:seed",
    ]
    assert gateway.observation_summary() == {
        "calls": 3,
        "history_messages": 9,
        "tool_results": 3,
        "context_snapshots": 3,
        "expectations_verified": 3,
        "observation_failures": 0,
    }

    stored = await runtime.event_store.list_after(run_id)
    assert [event.sequence for event in stored] == list(range(1, len(stored) + 1))
    event_types = [event.event_type for event in stored]
    assert event_types.count("model_call") == 3
    assert event_types.count("tool_call_start") == 2
    assert event_types.count("tool_call_end") == 2
    assert event_types.count("run.succeeded") == 1
    saved = await runtime.run_store.get(run_id, user_id=user.id)
    assert saved is not None and saved.status == "succeeded"

    replay_capability = _ReplayCapability()
    replay_gateway = _ExplodingGateway()
    replay_runtime = _runtime(
        db_session,
        user,
        replay_capability,
        replay_gateway,
    )
    replay = [
        event
        async for event in replay_runtime.stream_decision(
            _task(run_id, user.id),
            context=context,
        )
    ]

    # The actual replay contract returns only the persisted terminal event;
    # the complete event history is read from EventStore.
    assert len(replay) == 1
    assert replay[0]["type"] == "run_completed"
    assert replay[0]["termination_reason"] == "respond"
    assert replay[0]["sequence"] == stored[-1].sequence
    terminal_payload = json.loads(stored[-1].payload_json or "{}")
    assert terminal_payload["content"] == "Observed observed:derived-from:observed:seed"
    assert replay_gateway.calls == 0
    assert replay_capability.calls == []
    stored_after = await replay_runtime.event_store.list_after(run_id)
    assert [event.sequence for event in stored_after] == [
        event.sequence for event in stored
    ]
    assert [event.event_type for event in stored_after] == event_types
    assert (await replay_runtime.run_store.get(run_id, user_id=user.id)) is not None

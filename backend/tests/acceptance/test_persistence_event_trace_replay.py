"""A-L4-04: assert Run/Event/Trace persistence and run_id/trace_id replay."""

from __future__ import annotations

from copy import deepcopy
from typing import Any, AsyncIterator
from uuid import uuid4

import pytest
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.capabilities.base import BaseCapability
from app.capabilities.registry import CapabilityRegistry
from app.capabilities.types import ActionDescriptor, CapabilityResult
from app.evaluation.scripted_llm import ExpectedMessage, ObservationExpectation
from app.evaluation.scripted_llm import ScriptedLLM, ScriptedStep
from app.harness.contracts import ExecutionContext, RunRequest
from app.harness.debug import run_debug
from app.harness.execution import build_runtime
from app.harness.model_gateway import ModelGateway
from app.harness.model_types import ModelCallResult
from app.harness.task import AgentTask
from app.models import User
from app.models.agent_run import AgentInvocation
from app.schemas.user import UserRead
from app.trace import TraceEventType
from app.trace.sql_store import SqlTraceStore

_ACTION = "trace_fixture.inspect"
_GOAL = "Inspect two values and report the second observation"
_MESSAGES = [{"role": "user", "content": "Inspect the fixture values"}]

pytestmark = [pytest.mark.integration, pytest.mark.db]


class _TraceCapability(BaseCapability):
    name = "trace_fixture"
    description = "Synthetic read-only capability for persistence/replay checks"

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


def _invoke(run_id: str, decision_id: str, value: str) -> dict[str, Any]:
    return {
        "schema_version": "v1",
        "decision_id": decision_id,
        "run_id": run_id,
        "action": "invoke",
        "capability": _ACTION,
        "capability_version": "v1",
        "arguments": {"value": value},
    }


def _respond(run_id: str, content: str) -> dict[str, Any]:
    return {
        "schema_version": "v1",
        "decision_id": "step-3-report",
        "run_id": run_id,
        "action": "respond",
        "content": content,
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
        run_id=run_id, goal=_GOAL, messages=_MESSAGES, model="scripted-v1"
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
    capability: _TraceCapability,
    gateway: ModelGateway,
):
    registry = CapabilityRegistry()
    registry.register(capability)
    return build_runtime(
        session=session,
        user=user,
        registry=registry,
        model_gateway=gateway,
        trace_store=SqlTraceStore(session),
        durable=True,
        allow_side_effects=False,
    )


def _script(run_id: str) -> ScriptedLLM:
    def derived(observation) -> dict[str, Any]:
        observed = observation.last_tool_result
        assert observed is not None
        return _invoke(
            run_id,
            "step-2-derive",
            f"derived-from:{observed['safe_output']['value']}",
        )

    return ScriptedLLM(
        [
            ScriptedStep(
                decision=_invoke(run_id, "step-1-seed", "seed"),
                expect=ObservationExpectation(tool_results=0),
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
                decision=_respond(
                    run_id,
                    "Observed observed:derived-from:observed:seed",
                ),
                expect=ObservationExpectation(
                    tool_results=2,
                    last_tool_result={
                        "safe_output": {"value": "observed:derived-from:observed:seed"}
                    },
                    message_count=5,
                ),
            ),
        ]
    )


@pytest.mark.asyncio
async def test_run_events_and_trace_persist_and_replay_by_ids(
    db_session: AsyncSession,
) -> None:
    run_id = f"persist-{uuid4().hex}"
    user_row = User(username=f"trace-replay-{uuid4().hex}")
    db_session.add(user_row)
    await db_session.commit()
    await db_session.refresh(user_row)
    user = UserRead.model_validate(user_row)
    capability = _TraceCapability()
    gateway = _script(run_id)
    runtime = _runtime(db_session, user, capability, gateway)
    context = _context(run_id, user.id)

    report = await run_debug(_request(run_id), context, runtime=runtime)

    assert report.status == "succeeded"
    assert [call["value"] for call in capability.calls] == [
        "seed",
        "derived-from:observed:seed",
    ]
    saved = await runtime.run_store.get(run_id, user_id=user.id)
    assert saved is not None and saved.status == "succeeded"

    events = await runtime.event_store.list_after(run_id)
    assert [event.sequence for event in events] == list(range(1, len(events) + 1))
    types = [event.event_type for event in events]
    assert types.count("model_call") == 3
    assert types.count("tool_call_start") == 2
    assert types.count("tool_call_end") == 2
    assert types.count("run.succeeded") == 1
    assert types[-1] == "run.succeeded"
    tool_ends = [event for event in events if event.event_type == "tool_call_end"]
    assert [event.payload["output"]["value"] for event in tool_ends] == [
        "observed:seed",
        "observed:derived-from:observed:seed",
    ]
    model_calls = [event for event in events if event.event_type == "model_call"]
    assert all(event.payload["provider"] == "scripted" for event in model_calls)
    assert all(event.payload["model"] == "scripted-v1" for event in model_calls)
    terminal_payload = events[-1].payload
    assert terminal_payload["content"] == (
        "Observed observed:derived-from:observed:seed"
    )

    invocations = (
        (
            await db_session.execute(
                select(AgentInvocation).where(AgentInvocation.run_id == run_id)
            )
        )
        .scalars()
        .all()
    )
    assert {row.invocation_id: row.status for row in invocations} == {
        "step-1-seed": "succeeded",
        "step-2-derive": "succeeded",
    }

    trace_store = SqlTraceStore(db_session)
    trace = await trace_store.query(context.trace_id, user_id=user.id)
    assert trace is not None
    assert trace.trace_id == context.trace_id
    assert trace.run_id == run_id
    assert trace.user_id == user.id
    assert trace.status == "completed"
    trace_events = [event for step in trace.steps for event in step.events]
    assert all(event.run_id == run_id for event in trace_events)
    trace_types = [event.event_type for event in trace_events]
    assert trace_types.count(TraceEventType.MODEL_CALL) == 3
    assert trace_types.count(TraceEventType.TOOL_CALL_START) == 2
    assert trace_types.count(TraceEventType.TOOL_CALL_END) == 2
    assert trace_types.count(TraceEventType.AGENT_RESULT) == 1
    trace_tool_ends = [
        event
        for event in trace_events
        if event.event_type == TraceEventType.TOOL_CALL_END
    ]
    assert [event.invocation_id for event in trace_tool_ends] == [
        "step-1-seed",
        "step-2-derive",
    ]
    assert [event.status for event in trace_tool_ends] == ["completed", "completed"]
    assert await trace_store.query(context.trace_id, user_id=user.id + 1) is None

    # Trace is a safe projection: the full tool result stays in EventStore.
    assert all(event.data == {} for event in trace_tool_ends)
    assert tool_ends[0].payload["output"]["value"] == "observed:seed"

    replay_gateway = _ExplodingGateway()
    replay_capability = _TraceCapability()
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

    assert len(replay) == 1
    assert replay[0]["type"] == "run_completed"
    assert replay_gateway.calls == 0
    assert replay_capability.calls == []
    events_after = await replay_runtime.event_store.list_after(run_id)
    assert [event.sequence for event in events_after] == [
        event.sequence for event in events
    ]
    trace_after = await trace_store.query(context.trace_id, user_id=user.id)
    assert trace_after is not None
    assert [event.event_id for event in trace_after.steps[0].events] == [
        event.event_id for event in trace.steps[0].events
    ]

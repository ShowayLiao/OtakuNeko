"""Certification for the Runtime-owned specialist/subagent boundary."""

from __future__ import annotations

import json
import logging
from typing import Any

import pytest

from app.agents.agent_registry import AgentRegistry
from app.agents.base import BaseAgent
from app.agents.router import AgentRouter
from app.capabilities.registry import CapabilityRegistry
from app.harness.contracts import ExecutionContext
from app.harness.dispatcher import Dispatcher
from app.harness.runtime import AgentRuntime
from app.harness.task import AgentTask
from tests.acceptance.exposure_support import (
    NoModelGateway,
    RecordingReadCapability,
    SyntheticSpecialist,
)
from tests.capabilities.contracts.system_support import capture_application_logs

_PRIVATE = "specialist-private-authority-sentinel"


class UnboundSpecialist(BaseAgent):
    async def execute(self, task: Any) -> dict[str, Any]:
        raise AssertionError("unbound specialist must never execute")

    async def plan(self, task: Any) -> dict[str, Any]:
        return {"goal": getattr(task, "goal", ""), "steps": []}

    async def reflect(self, task: Any, result: Any) -> dict[str, Any]:
        return {"goal_achieved": False, "observations": []}


class LoopingSpecialist(BaseAgent):
    """Repeatedly proposes the same rejected invocation to test budgeting."""

    def __init__(
        self,
        capability: str,
        arguments: dict[str, Any],
        *,
        iterations: int = 5,
        capability_invoker: Any = None,
    ) -> None:
        self._capability = capability
        self._arguments = dict(arguments)
        self._iterations = iterations
        self._capability_invoker = capability_invoker

    def bind_runtime(self, *, capability_invoker: Any) -> "LoopingSpecialist":
        return LoopingSpecialist(
            self._capability,
            self._arguments,
            iterations=self._iterations,
            capability_invoker=capability_invoker,
        )

    async def execute(self, task: Any) -> dict[str, Any]:
        assert self._capability_invoker is not None
        results = []
        for _ in range(self._iterations):
            results.append(
                await self._capability_invoker(self._capability, self._arguments)
            )
        return {
            "kind": "subagent",
            "name": "recommendation",
            "status": "failed",
            "content": "Synthetic looping specialist",
            "data": {"results": results},
        }

    async def plan(self, task: Any) -> dict[str, Any]:
        return {"goal": getattr(task, "goal", ""), "steps": []}

    async def reflect(self, task: Any, result: Any) -> dict[str, Any]:
        return {"goal_achieved": False, "observations": []}


def _runtime(capability, specialist) -> tuple[AgentRuntime, Dispatcher, NoModelGateway]:
    registry = CapabilityRegistry()
    registry.register(capability)
    dispatcher = Dispatcher(registry)
    agents = AgentRegistry()
    agents.register("recommendation", specialist)
    gateway = NoModelGateway()
    runtime = AgentRuntime(
        None,
        model_gateway=gateway,
        dispatcher=dispatcher,
        specialist_router=AgentRouter(agents),
    )
    return runtime, dispatcher, gateway


def _task(run_id: str) -> AgentTask:
    return AgentTask(
        user_id=7,
        goal="推荐动漫",
        task_metadata={
            "run_id": run_id,
            "messages": [{"role": "user", "content": "推荐动漫"}],
        },
    )


def _context(run_id: str, allowlist: set[str]) -> ExecutionContext:
    return ExecutionContext(
        principal_id=7,
        run_id=run_id,
        trace_id=f"trace-{run_id}",
        capability_allowlist=frozenset(allowlist),
    )


async def _run(runtime: AgentRuntime, task: AgentTask, context: ExecutionContext):
    return [chunk async for chunk in runtime.stream_decision(task, context=context)]


def _events(chunks: list[dict[str, Any]], event_type: str) -> list[dict[str, Any]]:
    return [chunk for chunk in chunks if chunk.get("type") == event_type]


@pytest.mark.asyncio
async def test_specialist_capability_calls_use_real_dispatcher_and_identity():
    capability = RecordingReadCapability(requires_auth=True)
    descriptor = capability.actions()[0]
    public_name = descriptor.public_name
    assert public_name is not None
    specialist = SyntheticSpecialist(public_name, {"value": "specialist"})
    runtime, dispatcher, gateway = _runtime(capability, specialist)
    context = _context("run-specialist-success", {public_name})

    chunks = await _run(runtime, _task(context.run_id), context)

    assert _events(chunks, "route_decision")[0]["agent"] == "recommendation"
    tool_starts = _events(chunks, "tool_call_start")
    tool_ends = _events(chunks, "tool_call_end")
    assert len(tool_starts) == 1
    assert len(tool_ends) == 1
    assert tool_ends[0]["status"] == "succeeded"
    assert tool_ends[0]["error_code"] is None
    assert len(_events(chunks, "agent_result")) == 1
    assert chunks[-1]["type"] == "run_completed"
    assert capability.calls == [{"value": "specialist", "user_id": 7}]
    assert [event.event_type for event in dispatcher.events] == [
        "invocation_start",
        "invocation_end",
    ]
    assert gateway.calls == []


@pytest.mark.asyncio
async def test_specialist_without_bind_runtime_fails_closed():
    capability = RecordingReadCapability(requires_auth=True)
    runtime, dispatcher, _ = _runtime(capability, UnboundSpecialist())
    context = _context("run-specialist-unbound", {"synthetic_echo"})

    chunks = await _run(runtime, _task(context.run_id), context)

    assert _events(chunks, "route_decision")
    assert not _events(chunks, "tool_call_start")
    assert not _events(chunks, "agent_result")
    terminal = _events(chunks, "run_failed")
    assert len(terminal) == 1
    assert terminal[0]["error_code"] == "dispatcher_required"
    assert capability.calls == []
    assert dispatcher.events == []


@pytest.mark.asyncio
async def test_specialist_forged_authority_arguments_are_rejected_and_paired(
    caplog,
):
    capability = RecordingReadCapability(requires_auth=True)
    descriptor = capability.actions()[0]
    public_name = descriptor.public_name
    assert public_name is not None
    specialist = SyntheticSpecialist(
        public_name,
        {"value": "x", "user_id": _PRIVATE},
    )
    runtime, dispatcher, _ = _runtime(capability, specialist)
    context = _context("run-specialist-spoofed", {public_name})

    with capture_application_logs(caplog):
        logging.getLogger("app.harness.runtime").warning("specialist-log-capture-probe")
        chunks = await _run(runtime, _task(context.run_id), context)
        assert "specialist-log-capture-probe" in caplog.text

    assert capability.calls == []
    assert dispatcher.events == []
    starts = _events(chunks, "tool_call_start")
    ends = _events(chunks, "tool_call_end")
    assert len(starts) == 1
    assert len(ends) == 1
    assert ends[0]["status"] == "denied"
    assert ends[0]["error_code"] == "identity_spoofing"
    assert ends[0]["invocation_id"] == starts[0]["invocation_id"]
    terminal = _events(chunks, "run_failed")
    assert len(terminal) == 1
    serialized = json.dumps(chunks, ensure_ascii=False)
    assert _PRIVATE not in serialized
    assert _PRIVATE not in caplog.text
    assert all(_PRIVATE not in repr(record.exc_info) for record in caplog.records)


@pytest.mark.asyncio
async def test_specialist_rejected_proposals_consume_tool_budget():
    capability = RecordingReadCapability(requires_auth=True)
    descriptor = capability.actions()[0]
    public_name = descriptor.public_name
    assert public_name is not None
    specialist = LoopingSpecialist(
        public_name,
        {"value": "x", "user_id": _PRIVATE},
    )
    runtime, dispatcher, _ = _runtime(capability, specialist)
    context = _context("run-specialist-budget", {public_name})

    from app.harness.budget import RunBudget

    chunks = [
        chunk
        async for chunk in runtime.stream_decision(
            _task(context.run_id),
            context=context,
            budget=RunBudget(max_tool_calls=2),
        )
    ]

    assert capability.calls == []
    assert dispatcher.events == []
    ends = _events(chunks, "tool_call_end")
    assert len(ends) == 2
    assert all(end["status"] == "denied" for end in ends)
    assert all(end["error_code"] == "identity_spoofing" for end in ends)
    terminal = _events(chunks, "run_failed")
    assert len(terminal) == 1
    assert terminal[0]["error_code"] == "budget_exceeded"


@pytest.mark.asyncio
async def test_specialist_capability_not_in_allowlist_never_executes():
    capability = RecordingReadCapability(requires_auth=True)
    descriptor = capability.actions()[0]
    public_name = descriptor.public_name
    assert public_name is not None
    specialist = SyntheticSpecialist(public_name, {"value": "x"})
    runtime, dispatcher, _ = _runtime(capability, specialist)
    context = _context("run-specialist-denied", {"some_other_action"})

    chunks = await _run(runtime, _task(context.run_id), context)

    assert capability.calls == []
    assert dispatcher.events == []
    ends = _events(chunks, "tool_call_end")
    assert len(ends) == 1
    assert ends[0]["status"] == "denied"
    assert ends[0]["error_code"] == "policy_denied"
    terminal = _events(chunks, "run_failed")
    assert len(terminal) == 1
    assert terminal[0]["error_code"] == "tool_error"

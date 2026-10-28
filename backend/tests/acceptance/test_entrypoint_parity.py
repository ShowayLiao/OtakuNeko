"""Exercise HTTP ingress, real Dispatcher dependencies and queryable traces."""

from __future__ import annotations

import json
from typing import Any, cast

import pytest

from app.capabilities.base import BaseCapability
from app.capabilities.registry import CapabilityRegistry
from app.capabilities.types import ActionDescriptor, CapabilityResult
from app.harness.contracts import ExecutionContext
from app.harness.budget import RunBudget
from app.harness.model_types import ModelCallResult
from app.harness.model_gateway import ModelGateway
from app.harness.task import AgentTask
from app.trace.sql_store import SqlTraceStore
from app.trace.store import InMemoryTraceStore
from tests.api.test_agent_http_contract import _auth, _create_user, _sse_frames, _token


class DependencyProbe(BaseCapability):
    name = "collections"
    description = "Synthetic read with trusted domain dependencies"

    def __init__(self):
        self.owners = []

    def actions(self):
        return [
            ActionDescriptor(
                name="probe",
                public_name="collections.probe",
                description="Read synthetic data",
                input_schema={"type": "object"},
            )
        ]

    async def execute(self, action, **kwargs):
        assert kwargs["db"] is not None
        self.owners.append(kwargs["user"].id)
        return CapabilityResult.ok(value="synthetic-result").to_dict()


class ScenarioGateway:
    def __init__(self, *, model="probe-model", **kwargs):
        self.model = model
        self.calls = 0

    async def infer(self, **kwargs: Any):
        self.calls += 1
        scenario = kwargs["goal"]
        if scenario == "failure":
            return ModelCallResult(
                provider="fixture",
                model=self.model,
                operation="infer",
                status="failed",
                error_code="permanent",
            )
        decision: dict[str, Any] = {
            "schema_version": "v1",
            "decision_id": f"{kwargs['run_id']}:d{self.calls}",
            "action": "respond",
            "content": "synthetic answer",
        }
        if self.calls == 1 and scenario != "respond":
            decision.update(
                action="invoke",
                capability="collections.probe",
                capability_version="v1",
                arguments={},
            )
            decision.pop("content")
            if scenario == "denied":
                decision["capability"] = "missing.action"
            if scenario == "spoof":
                decision["arguments"] = {"user_id": 9999}
        return ModelCallResult(
            provider="fixture",
            model=self.model,
            operation="infer",
            status="completed",
            decision=decision,
        )

    async def close(self):
        pass


@pytest.mark.parametrize(
    "scenario,terminal",
    [
        ("respond", "run_completed"),
        ("read", "run_completed"),
        ("failure", "run_failed"),
        ("denied", "run_failed"),
        ("spoof", "run_failed"),
    ],
)
async def test_http_headless_dispatch_and_trace_parity(
    api_client,
    db_session,
    monkeypatch,
    scenario,
    terminal,
):
    from app.api.v1 import agent as agent_api

    user = await _create_user(db_session, f"parity-{scenario}")
    other = await _create_user(db_session, f"other-{scenario}")
    probe = DependencyProbe()
    registry = CapabilityRegistry()
    registry.register(probe)
    monkeypatch.setattr(agent_api, "build_capability_registry", lambda: registry)
    monkeypatch.setattr(agent_api, "OpenAIModelGateway", ScenarioGateway)
    # Memory is outside this comparison; it would add a separate model call.
    monkeypatch.setattr(agent_api, "MemoryServiceImpl", lambda **kwargs: NoMemory())
    response = await api_client.post(
        "/api/v1/chat",
        headers={
            **_auth(_token(user.id)),
            "X-Api-Key": "synthetic-key",
        },
        json={
            "model": "probe-model",
            "messages": [{"role": "user", "content": scenario}],
        },
    )
    assert response.status_code == 200
    frames = _sse_frames(response.text)
    events = [frame["data"] for frame in frames]
    assert frames[-1]["event"] == terminal
    run_id = events[-1]["run_id"]
    trace_response = await api_client.get(
        f"/api/v1/trace/{run_id}", headers=_auth(_token(user.id))
    )
    assert trace_response.status_code == 200, "chat must create its own queryable trace"
    trace = trace_response.json()
    assert trace["run_id"] == run_id and trace["user_id"] == user.id
    assert trace["status"] == ("completed" if terminal == "run_completed" else "failed")
    trace_events = [event for step in trace["steps"] for event in step["events"]]
    assert trace_events
    assert all(
        event["run_id"] == run_id and event["sequence"] > 0 for event in trace_events
    )
    assert any(event["event_type"] == "model_call" for event in trace_events)
    if scenario == "read":
        assert {
            event["invocation_id"]
            for event in trace_events
            if event["event_type"] == "tool_call_end"
        } == {f"{run_id}:d1"}
    run_response = await api_client.get(
        f"/api/v1/runs/{run_id}", headers=_auth(_token(user.id))
    )
    assert run_response.json()["status"] == (
        "succeeded" if terminal == "run_completed" else "failed"
    )
    assert (
        await api_client.get(f"/api/v1/trace/{run_id}", headers=_auth(_token(other.id)))
    ).status_code == 404
    assert (await api_client.get(f"/api/v1/trace/{run_id}")).status_code == 401

    from app.harness.execution import build_runtime

    headless_id = f"headless-{run_id}"
    runtime = build_runtime(
        session=db_session,
        user=user,
        registry=registry,
        model_gateway=cast(ModelGateway, ScenarioGateway()),
        trace_store=SqlTraceStore(db_session),
    )
    headless = [
        event
        async for event in runtime.stream_decision(
            AgentTask(
                user_id=user.id,
                goal=scenario,
                task_metadata={
                    "run_id": headless_id,
                    "thread_id": headless_id,
                    "messages": [{"role": "user", "content": scenario}],
                },
            ),
            context=ExecutionContext(
                principal_id=user.id,
                run_id=headless_id,
                trace_id=headless_id,
                thread_id=headless_id,
                capability_allowlist=frozenset({"collections.probe"}),
            ),
            budget=RunBudget(),
        )
    ]
    assert headless[-1]["type"] == terminal
    headless_trace = await SqlTraceStore(db_session).query(headless_id, user_id=user.id)
    assert headless_trace is not None
    assert [e["type"] for e in headless] == [frame["event"] for frame in frames]
    assert trace_signature(trace) == trace_signature(
        headless_trace.model_dump(mode="json")
    )
    assert probe.owners == ([user.id, user.id] if scenario == "read" else [])
    assert "synthetic answer" not in json.dumps(trace)


class NoMemory:
    async def retrieve_context(self, *args, **kwargs):
        return None


def trace_signature(trace):
    return [
        (event["event_type"], event["status"], event["error_code"])
        for step in trace["steps"]
        for event in step["events"]
    ]


@pytest.mark.parametrize("fault", ["projection", "storage"])
async def test_trace_failure_preserves_canonical_success(
    db_session, monkeypatch, fault
):
    from app.harness.decision_trace import DecisionTraceProjection
    from app.harness.execution import build_runtime
    from app.harness.persistence.run_store import RunStore

    user = await _create_user(db_session, f"trace-fault-{fault}")
    run_id = f"trace-fault-{fault}"

    class BrokenStore(InMemoryTraceStore):
        async def record(self, trace):
            raise RuntimeError("synthetic trace storage fault")

    def broken_projection(self, event):
        raise RuntimeError("synthetic projection fault")

    if fault == "projection":
        monkeypatch.setattr(DecisionTraceProjection, "observe", broken_projection)
    runtime = build_runtime(
        session=db_session,
        user=user,
        registry=CapabilityRegistry(),
        model_gateway=cast(ModelGateway, ScenarioGateway()),
        trace_store=BrokenStore(),
    )
    events = [
        event
        async for event in runtime.stream_decision(
            AgentTask(
                user_id=user.id, goal="respond", task_metadata={"run_id": run_id}
            ),
            context=ExecutionContext(
                principal_id=user.id, run_id=run_id, trace_id=run_id
            ),
        )
    ]
    assert events[-1]["type"] == "run_completed"
    run = await RunStore(db_session).get(run_id, user_id=user.id)
    assert run is not None
    assert run.status == "succeeded"


async def test_terminal_delivery_then_close_preserves_success(db_session):
    from app.harness.execution import build_runtime
    from app.harness.checkpoint import InMemoryCheckpointStore

    user = await _create_user(db_session, "terminal-close")
    run_id = "terminal-close"
    store = SqlTraceStore(db_session)
    checkpoint = InMemoryCheckpointStore()
    runtime = build_runtime(
        session=db_session,
        user=user,
        registry=CapabilityRegistry(),
        model_gateway=cast(ModelGateway, ScenarioGateway()),
        trace_store=store,
        checkpoint_store=checkpoint,
    )
    stream = runtime.stream_decision(
        AgentTask(
            user_id=user.id,
            goal="respond",
            task_metadata={"run_id": run_id, "thread_id": run_id},
        ),
        context=ExecutionContext(
            principal_id=user.id, run_id=run_id, trace_id=run_id, thread_id=run_id
        ),
    )
    async for event in stream:
        if event["type"] == "run_completed":
            break
    await getattr(stream, "aclose")()
    trace = await store.query(run_id, user_id=user.id)
    assert trace is not None and trace.status == "completed"
    saved = await checkpoint.load(run_id, run_id)
    assert saved is not None and saved.status == "completed"
    assert (
        saved.terminal_result is not None
        and saved.terminal_result.status == "completed"
    )


async def test_rejected_recovery_cannot_freeze_trace_failed(
    db_session, tmp_path, monkeypatch
):
    from app.harness.runtime import AgentRuntime
    from app.harness.dispatcher import Dispatcher
    from app.harness.persistence.run_store import RunStore
    from app.harness.persistence.event_store import EventStore
    from app.trace import AgentTrace
    from tests.acceptance.test_checkpoint_resume_admission import _setup, _RUN, _THREAD

    _, checkpoint, state = await _setup(db_session, tmp_path, monkeypatch)
    state.task.metadata["model"] = "fixture"
    store = SqlTraceStore(db_session)
    await store.record_projection(AgentTrace(trace_id=_RUN, run_id=_RUN, user_id=7))
    lease = await checkpoint.claim_lease(_RUN, _THREAD, "original", 60)
    assert lease is not None

    class RespondGateway(ScenarioGateway):
        async def infer(self, **kwargs):
            return await super().infer(**{**kwargs, "goal": "respond"})

    def runtime():
        return AgentRuntime(
            model_gateway=cast(ModelGateway, RespondGateway()),
            dispatcher=Dispatcher(CapabilityRegistry()),
            checkpoint_store=checkpoint,
            trace_store=store,
            run_store=RunStore(db_session),
            event_store=EventStore(db_session),
        )

    context = ExecutionContext(
        principal_id=7, run_id=_RUN, trace_id=_RUN, thread_id=_THREAD
    )
    rejected = [
        event async for event in runtime().stream_decision(state.task, context=context)
    ]
    assert rejected[-1]["termination_reason"] == "checkpoint_lease_lost"
    trace = await store.query(_RUN, user_id=7)
    assert trace is not None and trace.status == "running"
    await checkpoint.release_lease(lease)
    resumed = [
        event async for event in runtime().stream_decision(state.task, context=context)
    ]
    assert resumed[-1]["type"] == "run_completed", resumed[-1]
    trace = await store.query(_RUN, user_id=7)
    assert trace is not None and trace.status == "completed"
    await checkpoint.close()


@pytest.mark.parametrize("case_index", range(5))
async def test_terminal_http_recovery_rebuilds_trace_metadata(
    db_session,
    tmp_path,
    monkeypatch,
    case_index,
):
    from app.api.v1 import trace as trace_api
    from tests.acceptance.test_terminal_checkpoint_reconciliation import (
        _setup,
        _CASES,
        _client,
        _RUN,
    )

    case = _CASES[case_index]
    app, checkpoint, _, _, canonical_status, _ = await _setup(
        db_session,
        tmp_path,
        monkeypatch,
        case=case,
    )
    app.include_router(trace_api.router, prefix="/v1")
    async with _client(app) as client:
        recovered = await client.get(f"/v1/runs/{_RUN}")
        assert (
            recovered.status_code == 200
            and recovered.json()["status"] == canonical_status
        )
        response = await client.get(f"/v1/trace/{_RUN}")
        assert response.status_code == 200
        trace = response.json()
        assert trace["status"] == ("failed" if case[0] == "timeout" else case[0])
        assert trace["error"] == case[1]
        events = [event for step in trace["steps"] for event in step["events"]]
        assert events[-1]["status"] == case[0]
        assert events[-1]["error_code"] == case[1]
    await checkpoint.close()


async def test_interrupted_run_reconciliation_updates_trace(
    db_session, tmp_path, monkeypatch
):
    from app.api.v1 import agent as agent_api
    from app.harness.runtime import AgentRuntime
    from app.harness.dispatcher import Dispatcher
    from app.harness.persistence.run_store import RunStore
    from app.harness.persistence.event_store import EventStore
    from tests.acceptance.test_checkpoint_resume_admission import _setup, _RUN, _THREAD

    _, checkpoint, state = await _setup(db_session, tmp_path, monkeypatch)
    state.task.metadata["model"] = "fixture"
    monkeypatch.setattr(agent_api, "SqlTraceStore", SqlTraceStore)
    store = SqlTraceStore(db_session)
    runtime = AgentRuntime(
        model_gateway=cast(ModelGateway, ScenarioGateway()),
        dispatcher=Dispatcher(CapabilityRegistry()),
        checkpoint_store=checkpoint,
        trace_store=store,
        run_store=RunStore(db_session),
        event_store=EventStore(db_session),
    )
    stream = runtime.stream_decision(
        state.task,
        context=ExecutionContext(
            principal_id=7, run_id=_RUN, trace_id=_RUN, thread_id=_THREAD
        ),
    )
    async for event in stream:
        if event["type"] == "model_call":
            break
    await getattr(stream, "aclose")()
    run = await RunStore(db_session).get(_RUN, user_id=7)
    assert run is not None
    recovered = await agent_api._recover_stale_run(run, db_session)
    assert recovered.status == "cancelled"
    trace = await store.query(_RUN, user_id=7)
    assert trace is not None and trace.status == "cancelled"
    assert any(
        event.event_type == "model_call"
        for step in trace.steps
        for event in step.events
    )
    await checkpoint.close()

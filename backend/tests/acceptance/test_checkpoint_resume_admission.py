"""Admission and finite-budget regressions for the primary recovery ingress."""

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from collections.abc import AsyncGenerator
from typing import Any
import hashlib

import httpx
import pytest
from fastapi import FastAPI

from app.api.deps import get_current_user, get_session
from app.api.v1 import agent as agent_api
from app.capabilities.registry import CapabilityRegistry
from app.harness.budget import RunBudget, CancellationToken
from app.harness.cancellation_store import cancellation_store
from app.harness.checkpoint import SqliteCheckpointStore
from app.harness.model_types import ModelCallResult, ModelStreamEvent
from app.harness.model_types import ModelUsage
from app.harness.contracts import ExecutionContext
from app.harness.dispatcher import Dispatcher
from app.harness.persistence.event_store import EventStore
from app.harness.runtime import AgentRuntime
from app.harness.persistence.run_store import RunStore
from app.harness.state import AgentState
from app.harness.task import AgentTask
from app.schemas.user import UserRead


pytestmark = [pytest.mark.integration, pytest.mark.api, pytest.mark.db]
_RUN = "run-checkpoint-admission"
_THREAD = "user:7:thread:recovery"


async def _setup(db_session, tmp_path, monkeypatch, *, status="running", marker=True):
    path = str(tmp_path / "checkpoints.db")
    monkeypatch.setattr(agent_api.settings, "CHECKPOINT_DB_PATH", path)
    monkeypatch.setattr(agent_api.settings, "HARNESS_CHECKPOINT_ADAPTER", "sqlite")
    monkeypatch.setattr(agent_api, "SqlTraceStore", lambda db: None)
    monkeypatch.setattr(
        agent_api,
        "_resolve_provider_base_url",
        lambda value: "http://localhost:9999/v1",
    )
    monkeypatch.setattr(agent_api, "build_capability_registry", CapabilityRegistry)
    await RunStore(db_session).create(
        run_id=_RUN,
        user_id=7,
        thread_id=_THREAD,
        status=status,
        goal_hash=hashlib.sha256(b"resume").hexdigest(),
        model="fixture",
    )
    budget = RunBudget().snapshot()
    budget.update(
        remaining_seconds=120.0, saved_at=datetime.now(timezone.utc).isoformat()
    )
    state = AgentState(
        task=AgentTask(
            user_id=7,
            goal="resume",
            task_metadata={"run_id": _RUN, "thread_id": _THREAD},
        ),
        status=status,
        current_step="model",
        context={
            "decision_messages": [],
            "recovery_budget": budget,
            **({"recovery_version": 1} if marker else {}),
        },
    )
    store = SqliteCheckpointStore(path)
    await store.save(_RUN, _THREAD, state)
    app = FastAPI()
    app.include_router(agent_api.router, prefix="/v1")

    async def user():
        return UserRead(id=7, username="fixture", created_at=datetime.now(timezone.utc))

    async def session():
        yield db_session

    app.dependency_overrides[get_current_user] = user
    app.dependency_overrides[get_session] = session
    return app, store, state


async def _resume(app, **params):
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        return await client.post(
            "/v1/chat/resume",
            params={
                "run_id": _RUN,
                "thread_id": "recovery",
                "decision": "continue",
                **params,
            },
            headers={"X-Api-Key": "fixture"},
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "case",
    [
        "live_lease",
        "legacy",
        "terminal",
        "wrong_checkpoint_owner",
        "missing",
        "approval_pause",
        "specialist",
    ],
)
async def test_continue_refuses_unsafe_checkpoint(
    db_session, tmp_path, monkeypatch, case
):
    app, store, state = await _setup(
        db_session,
        tmp_path,
        monkeypatch,
        marker=case != "legacy",
        status="succeeded" if case == "terminal" else "running",
    )
    if case == "live_lease":
        await store.claim_lease(_RUN, _THREAD, "original-worker", 60)
    if case == "wrong_checkpoint_owner":
        state.task.user_id = 8
        await store.save(_RUN, _THREAD, state)
    if case == "specialist":
        state.context["recovery_kind"] = "specialist"
        await store.save(_RUN, _THREAD, state)
    if case == "missing":
        monkeypatch.setattr(
            agent_api.settings, "CHECKPOINT_DB_PATH", str(tmp_path / "missing.db")
        )
    if case == "approval_pause":
        state.status = "paused"
        await store.save(_RUN, _THREAD, state)
        await RunStore(db_session).transition(_RUN, "paused")
    response = await _resume(app)
    assert response.status_code == 409, response.text
    if case == "live_lease":
        # A refused request must not fence or release the running owner.
        assert await store.claim_lease(_RUN, _THREAD, "intruder", 60) is None
    await store.close()


@pytest.mark.asyncio
async def test_known_model_usage_is_checkpointed_before_exposing_event(
    db_session, tmp_path, monkeypatch
):
    _, store, state = await _setup(db_session, tmp_path, monkeypatch)
    state.task.metadata["model"] = "fixture"

    class UsageGateway(_Gateway):
        async def infer(self, **kwargs):
            result = await super().infer(**kwargs)
            return result.model_copy(
                update={
                    "usage": ModelUsage(
                        prompt_tokens=3,
                        completion_tokens=4,
                        total_tokens=7,
                        estimated_cost_usd=Decimal("0.25"),
                    )
                }
            )

    runtime = AgentRuntime(
        checkpoint_store=store,
        model_gateway=UsageGateway(),
        dispatcher=Dispatcher(CapabilityRegistry()),
        run_store=RunStore(db_session),
        event_store=EventStore(db_session),
    )
    stream = runtime.stream_decision(
        state.task,
        context=ExecutionContext(
            principal_id=7, run_id=_RUN, trace_id=_RUN, thread_id=_THREAD
        ),
    )
    assert isinstance(stream, AsyncGenerator)
    try:
        async for event in stream:
            if event["type"] == "model_call":
                checkpoint = await store.load(_RUN, _THREAD)
                assert checkpoint is not None
                budget = checkpoint.context["recovery_budget"]
                assert budget["total_tokens_used"] == 7
                assert float(budget["total_cost_usd"]) == 0.25
                assert budget["model_calls_used"] == 1
                break
        else:
            pytest.fail("model_call event missing")
    finally:
        await stream.aclose()
        await store.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("case", ["expired_deadline", "steps", "cancelled"])
async def test_continue_cannot_reset_other_run_controls(
    db_session, tmp_path, monkeypatch, case
):
    app, store, state = await _setup(db_session, tmp_path, monkeypatch)
    if case == "expired_deadline":
        state.context["recovery_budget"]["saved_at"] = (
            datetime.now(timezone.utc) - timedelta(minutes=3)
        ).isoformat()
    elif case == "steps":
        state.context["recovery_budget"].update(max_steps=1, steps_used=1)
    else:
        await store.request_cancellation(
            _RUN, requester="fixture", reason="cancel before restart"
        )
    await store.save(_RUN, _THREAD, state)
    _Gateway.calls.clear()
    monkeypatch.setattr(agent_api, "OpenAIModelGateway", _Gateway)
    response = await _resume(app)
    assert response.status_code == 200, response.text
    expected = {
        "expired_deadline": "run_timeout",
        "steps": "run_failed",
        "cancelled": "run_cancelled",
    }[case]
    assert f"event: {expected}" in response.text
    assert _Gateway.calls == []
    await store.close()


@pytest.mark.asyncio
async def test_continue_preserves_thread_scope(db_session, tmp_path, monkeypatch):
    app, store, _ = await _setup(db_session, tmp_path, monkeypatch)
    response = await _resume(app, thread_id="another-thread")
    assert response.status_code == 404
    assert await store.claim_lease(_RUN, _THREAD, "after-refusal", 60) is not None
    await store.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("admission_race", [False, True])
async def test_resume_cannot_take_over_an_active_local_run_with_expired_lease(
    db_session, tmp_path, monkeypatch, admission_race
):
    app, store, _ = await _setup(db_session, tmp_path, monkeypatch)
    old_store = SqliteCheckpointStore(
        store.path, clock=lambda: datetime.now(timezone.utc) - timedelta(minutes=1)
    )
    await old_store.claim_lease(_RUN, _THREAD, "still-running-local-worker", 1)
    token = CancellationToken()
    cancellation_store.register(_RUN, token)
    if admission_race:
        # A local owner may register between the advisory check and admission.
        monkeypatch.setattr(cancellation_store, "is_active", lambda run_id: False)
    monkeypatch.setattr(agent_api, "OpenAIModelGateway", _Gateway)
    try:
        response = await _resume(app)
        assert response.status_code == 409, response.text
        assert not token.is_cancelled()
        assert cancellation_store.cancel(_RUN)
        assert token.is_cancelled()
    finally:
        cancellation_store.unregister(_RUN, token)
        await old_store.close()
        await store.close()
    response = await _resume(app)
    assert response.status_code == 200, response.text
    assert "event: run_completed" in response.text


class _Gateway:
    calls: list[dict[str, Any]] = []

    def __init__(self, **kwargs):
        pass

    async def infer(self, **kwargs):
        self.calls.append(kwargs)
        return ModelCallResult(
            provider="fixture",
            model="fixture",
            operation="infer",
            status="completed",
            decision={
                "schema_version": "v1",
                "decision_id": "resumed-answer",
                "run_id": kwargs["run_id"],
                "action": "respond",
                "content": "continued",
            },
        )

    async def close(self):
        pass

    async def stream_infer(self, **kwargs):
        yield ModelStreamEvent(result=await self.infer(**kwargs))

    async def synthesize(self, **kwargs):
        raise AssertionError("Recovery must use Decisions")

    async def synthesize_result(self, **kwargs):
        raise AssertionError("Recovery must use Decisions")


@pytest.mark.asyncio
@pytest.mark.parametrize("exhausted", [False, True])
async def test_continue_restores_model_budget(
    db_session, tmp_path, monkeypatch, exhausted
):
    app, store, state = await _setup(db_session, tmp_path, monkeypatch)
    state.context["recovery_budget"].update(
        max_model_calls=1, model_calls_used=int(exhausted)
    )
    await store.save(_RUN, _THREAD, state)
    _Gateway.calls.clear()
    monkeypatch.setattr(agent_api, "OpenAIModelGateway", _Gateway)
    response = await _resume(app)
    assert response.status_code == 200, response.text
    if exhausted:
        assert '"termination_reason": "max_model_calls"' in response.text
        assert _Gateway.calls == []
    else:
        assert "event: run_completed" in response.text
        assert len(_Gateway.calls) == 1
    stored = await RunStore(db_session).get(_RUN, user_id=7)
    assert stored is not None
    assert stored.status == ("failed" if exhausted else "succeeded")
    assert (await _resume(app)).status_code == 409
    assert len(_Gateway.calls) == (0 if exhausted else 1)
    assert await store.claim_lease(_RUN, _THREAD, "after-completion", 60) is not None
    await store.close()

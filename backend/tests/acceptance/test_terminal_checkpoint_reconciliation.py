"""Terminal checkpoint / canonical fact reconciliation via the real API."""

from datetime import datetime, timedelta, timezone
import hashlib
import sqlite3

import httpx
import pytest
from fastapi import FastAPI

from app.api.deps import get_current_user, get_session
from app.api.v1 import agent as agent_api
from app.harness.budget import CancellationToken
from app.harness.cancellation_store import cancellation_store
from app.harness.checkpoint import SqliteCheckpointStore, CheckpointLeaseLost
from app.harness.contracts import RunEvent, RunResult, ExecutionContext
from app.harness.persistence.event_store import EventStore
from app.harness.persistence.run_store import RunStore
from app.harness.state import AgentState
from app.harness.task import AgentTask
from app.harness.runtime import AgentRuntime
from app.schemas.user import UserRead


pytestmark = [pytest.mark.integration, pytest.mark.api, pytest.mark.db]
_RUN = "terminal-reconcile"
_THREAD = "user:7:thread:terminal"
_CASES = [
    ("completed", None, "respond", "succeeded", "run.succeeded"),
    ("failed", "provider_error", "provider_error", "failed", "run.failed"),
    ("failed", "tool_error", "attention_required", "failed", "run.failed"),
    ("cancelled", "cancelled", "cancelled", "cancelled", "run.cancelled"),
    ("timeout", "timeout", "timeout", "failed", "run.failed"),
]


async def _setup(db_session, tmp_path, monkeypatch, case=_CASES[0], *, existing=False):
    status, error, reason, canonical_status, canonical_type = case
    path = str(tmp_path / "terminal-checkpoints.db")
    monkeypatch.setattr(agent_api.settings, "CHECKPOINT_DB_PATH", path)
    monkeypatch.setattr(agent_api.settings, "HARNESS_CHECKPOINT_ADAPTER", "sqlite")
    monkeypatch.setattr(agent_api.settings, "CHECKPOINT_LEASE_SECONDS", 1)

    def forbidden(*args, **kwargs):
        raise AssertionError(
            "Terminal reconciliation must not instantiate execution dependencies"
        )

    monkeypatch.setattr(agent_api, "OpenAIModelGateway", forbidden)
    monkeypatch.setattr(agent_api, "build_capability_registry", forbidden)
    await RunStore(db_session).create(
        run_id=_RUN,
        user_id=7,
        thread_id=_THREAD,
        status="running",
        goal_hash=hashlib.sha256(b"terminal fixture").hexdigest(),
        model="fixture",
    )
    await EventStore(db_session).append(
        RunEvent(run_id=_RUN, sequence=1, event_type="run.started")
    )
    result = RunResult(
        run_id=_RUN,
        status=status,
        error_code=error,
        termination_reason=reason,
        content="saved answer" if status == "completed" else None,
    )
    payload = {"termination_reason": reason}
    if status == "completed":
        payload["content"] = "saved answer"
    else:
        payload["error_code"] = error
        if status == "timeout":
            payload["status"] = "timeout"
    state = AgentState(
        task=AgentTask(
            user_id=7,
            goal="terminal fixture",
            task_metadata={"run_id": _RUN, "thread_id": _THREAD, "model": "fixture"},
        ),
        status=status,
        result=result.content,
        context={
            "recovery_version": 1,
            "recovery_kind": "decision",
            "recovery_terminal_result": result.model_dump(mode="json"),
        },
    )
    store = SqliteCheckpointStore(path)
    await store.save(_RUN, _THREAD, state)
    old = SqliteCheckpointStore(
        path, clock=lambda: datetime.now(timezone.utc) - timedelta(seconds=10)
    )
    await old.claim_lease(_RUN, _THREAD, "killed-worker", 1)
    if existing:
        await EventStore(db_session).append(
            RunEvent(
                run_id=_RUN, sequence=2, event_type=canonical_type, payload=payload
            )
        )
    app = FastAPI()
    app.include_router(agent_api.router, prefix="/v1")

    async def user():
        return UserRead(id=7, username="fixture", created_at=datetime.now(timezone.utc))

    async def session():
        yield db_session

    app.dependency_overrides[get_current_user] = user
    app.dependency_overrides[get_session] = session
    return app, store, state, payload, canonical_status, canonical_type


def _client(app):
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    )


@pytest.mark.parametrize("case", _CASES)
@pytest.mark.parametrize(
    "existing", [False, True], ids=["checkpoint-only", "event-committed"]
)
async def test_get_recovers_terminal_fact_once_without_execution(
    db_session, tmp_path, monkeypatch, case, existing
):
    app, store, _, payload, status, event_type = await _setup(
        db_session, tmp_path, monkeypatch, case, existing=existing
    )
    async with _client(app) as client:
        first = await client.get(f"/v1/runs/{_RUN}", params={"thread_id": "terminal"})
        assert first.status_code == 200, first.text
        assert first.json()["status"] == status, first.text
        assert first.json()["error_code"] == case[1]
        assert first.json()["finished_at"] is not None
        events = await client.get(f"/v1/runs/{_RUN}/events")
        terminal = [
            e for e in events.json()["events"] if e["event_type"] != "run.started"
        ]
        assert len(terminal) == 1
        assert terminal[0]["event_type"] == event_type
        assert terminal[0]["payload"] == payload
        again = await client.get(f"/v1/runs/{_RUN}")
        assert again.json() == first.json()
        replay = await client.get(f"/v1/runs/{_RUN}/events")
        assert replay.json() == events.json()
        resume = await client.post(
            "/v1/chat/resume",
            params={"thread_id": "terminal", "run_id": _RUN, "decision": "continue"},
        )
        assert resume.status_code == 409
    assert (
        await store.claim_lease(_RUN, _THREAD, "after-reconciliation", 30) is not None
    )
    await store.close()


async def test_resume_reconciles_terminal_before_returning_conflict(
    db_session, tmp_path, monkeypatch
):
    app, store, _, _, _, _ = await _setup(db_session, tmp_path, monkeypatch)
    async with _client(app) as client:
        resume = await client.post(
            "/v1/chat/resume",
            params={"thread_id": "terminal", "run_id": _RUN, "decision": "continue"},
        )
        assert resume.status_code == 409
    run = await RunStore(db_session).get(_RUN)
    assert run is not None and run.status == "succeeded"
    assert len(await EventStore(db_session).list_after(_RUN, after_sequence=1)) == 1
    await store.close()


@pytest.mark.parametrize("case", _CASES)
@pytest.mark.parametrize("explicit_context", [True, False])
async def test_runtime_replays_terminal_without_model_or_dispatcher(
    db_session, tmp_path, monkeypatch, case, explicit_context
):
    _, store, state, payload, status, _ = await _setup(
        db_session, tmp_path, monkeypatch, case
    )
    runtime = AgentRuntime(
        checkpoint_store=store,
        run_store=RunStore(db_session),
        event_store=EventStore(db_session),
    )
    context = (
        ExecutionContext(principal_id=7, run_id=_RUN, trace_id=_RUN, thread_id=_THREAD)
        if explicit_context
        else None
    )
    events = [
        event async for event in runtime.stream_decision(state.task, context=context)
    ]
    assert len(events) == 1
    expected_type = {
        "completed": "run_completed",
        "failed": "run_failed",
        "timeout": "run_timeout",
        "cancelled": "run_cancelled",
    }[case[0]]
    assert events[0]["type"] == expected_type
    for key, value in payload.items():
        if key != "status":
            assert events[0][key] == value
    replay = [
        event
        async for event in runtime.stream_decision(
            state.task,
            context=ExecutionContext(
                principal_id=7, run_id=_RUN, trace_id=_RUN, thread_id=_THREAD
            ),
        )
    ]
    assert replay == events
    run = await RunStore(db_session).get(_RUN)
    assert run is not None and run.status == status
    stored = await store.load(_RUN, _THREAD)
    assert stored is not None and stored.status == state.status
    await store.close()


@pytest.mark.parametrize("corruption", ["missing", "version", "run", "status", "owner"])
async def test_invalid_terminal_evidence_never_creates_a_success_fact(
    db_session, tmp_path, monkeypatch, corruption
):
    app, store, state, _, _, _ = await _setup(db_session, tmp_path, monkeypatch)
    raw = state.context["recovery_terminal_result"]
    if corruption == "missing":
        state.context.pop("recovery_terminal_result")
    elif corruption == "version":
        raw["schema_version"] = "v999"
    elif corruption == "run":
        raw["run_id"] = "some-other-run"
    elif corruption == "status":
        raw["status"] = "failed"
    else:
        state.task.user_id = 8
    lease = await store.claim_lease(_RUN, _THREAD, "fixture-writer", 30)
    assert lease is not None
    await store.save(
        _RUN,
        _THREAD,
        state,
        worker_id=lease.worker_id,
        fencing_token=lease.fencing_token,
    )
    await store.release_lease(lease)
    async with _client(app) as client:
        response = await client.get(f"/v1/runs/{_RUN}")
        assert response.status_code == 200
        assert response.json()["status"] != "succeeded"
    assert await EventStore(db_session).list_after(_RUN, after_sequence=1) == []
    await store.close()


async def test_conflicting_terminal_event_is_preserved_for_investigation(
    db_session, tmp_path, monkeypatch
):
    app, store, _, _, _, _ = await _setup(db_session, tmp_path, monkeypatch)
    await EventStore(db_session).append(
        RunEvent(
            run_id=_RUN,
            sequence=2,
            event_type="run.failed",
            payload={
                "error_code": "tool_error",
                "termination_reason": "attention_required",
            },
        )
    )
    before = await EventStore(db_session).list_after(_RUN, after_sequence=0)
    async with _client(app) as client:
        response = await client.get(f"/v1/runs/{_RUN}")
        assert response.status_code == 409, response.text
    after = await EventStore(db_session).list_after(_RUN, after_sequence=0)
    assert [event.event_id for event in after] == [event.event_id for event in before]
    run = await RunStore(db_session).get(_RUN)
    assert run is not None and run.status == "running"
    checkpoint = await store.load(_RUN, _THREAD)
    assert checkpoint is not None and checkpoint.status == "completed"
    await store.close()


@pytest.mark.parametrize("active", ["local", "lease"])
async def test_terminal_reconciliation_cannot_fence_an_active_owner(
    db_session, tmp_path, monkeypatch, active
):
    app, store, _, _, _, _ = await _setup(db_session, tmp_path, monkeypatch)
    token = CancellationToken()
    if active == "local":
        cancellation_store.register(_RUN, token)
    else:
        await store.claim_lease(_RUN, _THREAD, "active-owner", 30)
    try:
        async with _client(app) as client:
            response = await client.get(f"/v1/runs/{_RUN}")
            assert response.status_code == 200
            assert response.json()["status"] == "running"
        assert not token.is_cancelled()
        events = await EventStore(db_session).list_after(_RUN, after_sequence=1)
        assert events == []
    finally:
        cancellation_store.unregister(_RUN, token)
        await store.close()


async def test_reconciliation_retry_after_event_commit_is_idempotent(
    db_session, tmp_path, monkeypatch
):
    app, store, _, _, _, _ = await _setup(db_session, tmp_path, monkeypatch)
    original = RunStore.transition
    fail_once = True

    async def interrupted(self, run_id, status, **kwargs):
        nonlocal fail_once
        if run_id == _RUN and status == "succeeded" and fail_once:
            fail_once = False
            raise RuntimeError("synthetic transition interruption")
        return await original(self, run_id, status, **kwargs)

    monkeypatch.setattr(RunStore, "transition", interrupted)
    async with _client(app) as client:
        first = await client.get(f"/v1/runs/{_RUN}")
        assert first.status_code == 409
        committed = await EventStore(db_session).list_after(_RUN, after_sequence=1)
        assert len(committed) == 1
        second = await client.get(f"/v1/runs/{_RUN}")
        assert second.status_code == 200 and second.json()["status"] == "succeeded"
        after = await EventStore(db_session).list_after(_RUN, after_sequence=1)
        assert [event.event_id for event in after] == [
            event.event_id for event in committed
        ]
    await store.close()


async def test_direct_terminal_recovery_never_fences_registered_local_owner(
    db_session, tmp_path, monkeypatch
):
    _, store, state, _, _, _ = await _setup(db_session, tmp_path, monkeypatch)
    runtime = AgentRuntime(
        checkpoint_store=store,
        run_store=RunStore(db_session),
        event_store=EventStore(db_session),
    )
    token = CancellationToken()
    cancellation_store.register(_RUN, token)
    with sqlite3.connect(store.path) as connection:
        before = connection.execute(
            "SELECT worker_id, fencing_token, lease_expires_at FROM harness_checkpoint_leases WHERE run_id = ?",
            (_RUN,),
        ).fetchone()
    try:
        with pytest.raises(CheckpointLeaseLost):
            await runtime.reconcile_terminal_checkpoint(
                state.task,
                context=ExecutionContext(
                    principal_id=7, run_id=_RUN, trace_id=_RUN, thread_id=_THREAD
                ),
            )
        with sqlite3.connect(store.path) as connection:
            after = connection.execute(
                "SELECT worker_id, fencing_token, lease_expires_at FROM harness_checkpoint_leases WHERE run_id = ?",
                (_RUN,),
            ).fetchone()
        assert after == before
        assert cancellation_store.cancel(_RUN)
        assert token.is_cancelled()
        assert await EventStore(db_session).list_after(_RUN, after_sequence=1) == []
    finally:
        cancellation_store.unregister(_RUN, token)
        await store.close()


@pytest.mark.parametrize("boundary", ["after-header-read", "before-event-insert"])
async def test_terminal_repair_never_resurrects_deleted_history(
    db_session, tmp_path, monkeypatch, boundary
):
    app, store, _, _, _, _ = await _setup(db_session, tmp_path, monkeypatch)
    deleted = False
    calls = 0
    original_get = RunStore.get
    original_event_lookup = EventStore._get_by_sequence

    async def delete_after_read(self, run_id, **kwargs):
        nonlocal calls, deleted
        run = await original_get(self, run_id, **kwargs)
        if run_id == _RUN:
            calls += 1
        if boundary == "after-header-read" and calls == 2 and not deleted:
            deleted = True
            await RunStore(db_session).delete_thread(_THREAD, user_id=7)
        return run

    async def delete_before_insert(self, run_id, sequence):
        nonlocal deleted
        event = await original_event_lookup(self, run_id, sequence)
        if (
            boundary == "before-event-insert"
            and run_id == _RUN
            and sequence == 2
            and not deleted
        ):
            deleted = True
            await RunStore(db_session).delete_thread(_THREAD, user_id=7)
        return event

    monkeypatch.setattr(RunStore, "get", delete_after_read)
    monkeypatch.setattr(EventStore, "_get_by_sequence", delete_before_insert)
    async with _client(app) as client:
        response = await client.get(f"/v1/runs/{_RUN}")
        assert deleted
        assert await original_get(RunStore(db_session), _RUN) is None, response.text
        assert await EventStore(db_session).list_after(_RUN, after_sequence=0) == []
        assert response.status_code in {404, 409}
    await store.close()

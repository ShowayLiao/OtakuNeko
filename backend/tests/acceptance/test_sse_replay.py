from __future__ import annotations

from datetime import datetime, timezone

import httpx
import pytest
from fastapi import FastAPI

from app.api.deps import get_current_user, get_session
from app.api.v1.agent import (
    _chat_sse_projection,
    _interactive_run_store_enabled,
    format_sse,
    router,
)
from app.harness.contracts import RunEvent
from app.harness.persistence.event_store import EventStore
from app.harness.persistence.run_store import RunStore
from app.schemas.user import UserRead


def _user(user_id: int) -> UserRead:
    return UserRead(
        id=user_id,
        username=f"user-{user_id}",
        created_at=datetime.now(timezone.utc),
    )


def test_format_sse_adds_replayable_id_without_changing_event_data() -> None:
    frame = format_sse(
        "message_chunk",
        {"type": "message_chunk", "content": "hello"},
        event_id=4,
    )

    assert frame.startswith("id: 4\nevent: message_chunk\n")
    assert '"content": "hello"' in frame


def test_chat_sse_projection_declares_durability_without_mutating_runtime_data() -> None:
    runtime_event = {"type": "run_completed", "run_id": "run-1", "sequence": 4}

    durable_projection = _chat_sse_projection(runtime_event, durable=True)
    ephemeral_projection = _chat_sse_projection(runtime_event, durable=False)

    assert durable_projection["durable"] is True
    assert ephemeral_projection["durable"] is False
    assert runtime_event == {"type": "run_completed", "run_id": "run-1", "sequence": 4}


def test_replay_wiring_respects_disabled_interactive_store(monkeypatch) -> None:
    monkeypatch.setenv("INTERACTIVE_RUN_STORE_ENABLED", "false")

    assert _interactive_run_store_enabled() is False


@pytest.mark.asyncio
async def test_run_and_event_projection_is_scoped_and_replayable(db_session) -> None:
    run_store = RunStore(db_session)
    event_store = EventStore(db_session)
    await run_store.create(
        run_id="run-replay",
        user_id=7,
        thread_id="user:7:thread:thread-1",
        status="queued",
        goal_hash="goal-hash",
        model="test-model",
    )
    await run_store.transition("run-replay", "running")
    await event_store.append(
        RunEvent(
            run_id="run-replay",
            sequence=1,
            event_type="run.started",
            payload={},
        )
    )
    await event_store.append(
        RunEvent(
            run_id="run-replay",
            sequence=2,
            event_type="message_chunk",
            payload={"content": "safe", "token": "secret"},
        )
    )
    await event_store.append(
        RunEvent(
            run_id="run-replay",
            sequence=3,
            event_type="run.succeeded",
            payload={},
        )
    )
    await run_store.transition("run-replay", "succeeded")

    current_user = _user(7)
    app = FastAPI()
    app.include_router(router, prefix="/v1")

    async def override_user() -> UserRead:
        return current_user

    async def override_session():
        yield db_session

    app.dependency_overrides[get_current_user] = override_user
    app.dependency_overrides[get_session] = override_session

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        run_response = await client.get(
            "/v1/runs/run-replay?thread_id=thread-1"
        )
        assert run_response.status_code == 200
        assert run_response.json()["status"] == "succeeded"
        assert run_response.json()["last_sequence"] == 3

        replay_response = await client.get(
            "/v1/runs/run-replay/events?after=1&thread_id=thread-1"
        )
        assert replay_response.status_code == 200
        payload = replay_response.json()
        assert [event["sequence"] for event in payload["events"]] == [2, 3]
        assert payload["events"][0]["payload"]["token"] == "[REDACTED]"

        header_replay = await client.get(
            "/v1/runs/run-replay/events?thread_id=thread-1",
            headers={"Last-Event-ID": "2"},
        )
        assert [event["sequence"] for event in header_replay.json()["events"]] == [3]

        negative = await client.get("/v1/runs/run-replay/events?after=-1")
        too_large = await client.get("/v1/runs/run-replay/events?after=1000000001")
        assert negative.status_code == 400
        assert too_large.status_code == 400

        missing = await client.get("/v1/runs/missing")
        assert missing.status_code == 404

    current_user = _user(8)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        cross_user = await client.get("/v1/runs/run-replay")
        assert cross_user.status_code == 404

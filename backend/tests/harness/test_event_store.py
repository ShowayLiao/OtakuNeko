from __future__ import annotations

import json

import pytest

from app.harness.contracts import RunEvent
from app.harness.persistence.event_store import (
    EventConflict,
    EventPayloadError,
    EventStore,
)
from app.harness.persistence.run_store import RunStore


async def _create_run(session) -> None:
    await RunStore(session).create(
        run_id="run-events",
        user_id=7,
        thread_id="thread",
        status="queued",
        goal_hash="hash",
        model="model",
    )


@pytest.mark.asyncio
async def test_event_store_append_is_idempotent_and_ordered(db_session) -> None:
    await _create_run(db_session)
    store = EventStore(db_session)
    event = RunEvent(
        run_id="run-events",
        sequence=1,
        event_type="run.started",
        payload={"api_key": "secret", "safe": "value"},
    )

    first = await store.append(event)
    duplicate = await store.append(event)
    later = await store.append(
        RunEvent(
            run_id="run-events",
            sequence=2,
            event_type="message.chunk",
            payload={"content": "hello"},
        )
    )

    assert first.event_id == duplicate.event_id
    assert later.sequence == 2
    listed = await store.list_after("run-events", after_sequence=0)
    assert [item.sequence for item in listed] == [1, 2]
    assert json.loads(first.payload_json)["api_key"] == "[REDACTED]"
    assert "secret" not in first.payload_json


@pytest.mark.asyncio
async def test_event_store_rejects_payload_conflict_for_same_sequence(db_session) -> None:
    await _create_run(db_session)
    store = EventStore(db_session)
    await store.append(
        RunEvent(
            run_id="run-events",
            sequence=1,
            event_type="decision.created",
            payload={"choice": "a"},
        )
    )

    with pytest.raises(EventConflict):
        await store.append(
            RunEvent(
                run_id="run-events",
                sequence=1,
                event_type="decision.created",
                payload={"choice": "b"},
            )
        )


@pytest.mark.asyncio
async def test_event_store_rejects_unsafe_or_oversized_payload(db_session) -> None:
    await _create_run(db_session)
    store = EventStore(db_session, max_payload_bytes=64)

    with pytest.raises(EventPayloadError):
        await store.append(
            RunEvent(
                run_id="run-events",
                sequence=1,
                event_type="unsafe",
                payload={"nested": object()},
            )
        )
    with pytest.raises(EventPayloadError):
        await store.append(
            RunEvent(
                run_id="run-events",
                sequence=2,
                event_type="large",
                payload={"content": "x" * 1000},
            )
        )

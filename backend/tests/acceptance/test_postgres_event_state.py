"""PostgreSQL canonical event identity, conflict recovery and JSON state."""

import asyncio
from collections.abc import Callable
from typing import Any

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.harness.contracts import InvocationResult, RunEvent
from app.harness.persistence.event_store import (
    EventConflict,
    EventPayloadError,
    EventStore,
)
from app.harness.persistence.run_store import RunStore
from app.models.user import User

pytestmark = [pytest.mark.postgres, pytest.mark.integration, pytest.mark.db]


@pytest.fixture
async def event_factory(
    postgres_engine: AsyncEngine,
) -> async_sessionmaker[AsyncSession]:
    factory = async_sessionmaker(postgres_engine, expire_on_commit=False)
    async with factory() as session:
        session.add(User(id=505, username="event-state-owner"))
        await session.commit()
        await RunStore(session).create(
            run_id="event-state-run", user_id=505, thread_id="user:505:thread:state"
        )
    return factory


def _event(payload: dict[str, Any], *, sequence: int = 1) -> RunEvent:
    return RunEvent(
        run_id="event-state-run",
        sequence=sequence,
        event_type="invocation.succeeded",
        invocation_id="state-invocation",
        payload=payload,
    )


async def _race(
    factory: async_sessionmaker[AsyncSession],
    payloads: list[dict[str, Any]],
) -> tuple[list[tuple[str, str]], set[int]]:
    ready: asyncio.Queue[int] = asyncio.Queue()
    start = asyncio.Event()

    async def write(payload: dict[str, Any]) -> tuple[str, str]:
        async with factory() as session:
            pid = int(
                (await session.execute(text("SELECT pg_backend_pid()"))).scalar_one()
            )
            ready.put_nowait(pid)
            await start.wait()
            try:
                stored = await EventStore(session).append(_event(payload))
                return "accepted", stored.event_id
            except EventConflict:
                await session.rollback()
                recovered = await EventStore(session).append(
                    _event({"recovered": True}, sequence=2)
                )
                return "conflict", recovered.event_id

    tasks = [asyncio.create_task(write(payload)) for payload in payloads]
    try:
        pids = set(
            await asyncio.wait_for(asyncio.gather(*(ready.get() for _ in tasks)), 15)
        )
        start.set()
        outcomes = await asyncio.wait_for(asyncio.gather(*tasks), 20)
        return outcomes, pids
    finally:
        start.set()
        for task in tasks:
            if not task.done():
                task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)


async def test_concurrent_identical_events_commit_once_and_preserve_tool_artifact_json(
    event_factory: async_sessionmaker[AsyncSession],
    record_property: Callable[[str, object], None],
) -> None:
    artifact = {
        "ref": "artifact:test/recommendations.json",
        "media_type": "application/json",
        "sha256": "a" * 64,
    }
    result = InvocationResult(
        invocation_id="state-invocation",
        run_id="event-state-run",
        status="succeeded",
        output={"items": ["番剧", None, True, 3, 0.5], "nested": {"complete": False}},
        artifacts=[artifact],
        provenance={"source": "test-fixture"},
    )
    payload = {
        "result": result.model_dump(mode="json"),
        "tool_state": {"cursor": 2, "pending": []},
    }
    outcomes, pids = await _race(event_factory, [payload] * 6)
    assert len(pids) == 6
    assert all(status == "accepted" for status, _ in outcomes)
    assert len({event_id for _, event_id in outcomes}) == 1
    async with event_factory() as session:
        stored = await EventStore(session).list_after("event-state-run")
        assert len(stored) == 1
        assert stored[0].sequence == 1
        assert stored[0].payload == payload
        restored = InvocationResult.model_validate(stored[0].payload["result"])
        assert restored.artifacts == [artifact]
        assert restored.output == result.output
        assert type(restored.output["items"][2]) is bool
    record_property("concurrent_event_writers", 6)
    record_property("independent_postgres_connections", len(pids))
    record_property("durable_event_count", 1)
    record_property("tool_state_and_artifact_reference_roundtrip", "verified")


async def test_conflicting_concurrent_events_reject_one_and_allow_next_commit(
    event_factory: async_sessionmaker[AsyncSession],
    record_property: Callable[[str, object], None],
) -> None:
    outcomes, pids = await _race(event_factory, [{"winner": "a"}, {"winner": "b"}])
    assert len(pids) == 2
    assert sorted(status for status, _ in outcomes) == ["accepted", "conflict"]
    async with event_factory() as session:
        events = await EventStore(session).list_after("event-state-run")
        assert [event.sequence for event in events] == [1, 2]
        assert events[0].payload in ({"winner": "a"}, {"winner": "b"})
        assert events[1].payload == {"recovered": True}
    record_property("expected_failure_category", "EventConflict")
    record_property("concurrent_accepted_writes", 1)
    record_property("concurrent_conflicting_writes", 1)
    record_property("next_event_commit_after_conflict", "verified")


@pytest.mark.parametrize("invalid_kind", ["non-finite", "unsupported-object"])
async def test_invalid_event_state_is_rejected_without_polluting_next_write(
    event_factory: async_sessionmaker[AsyncSession],
    invalid_kind: str,
    record_property: Callable[[str, object], None],
) -> None:
    invalid = float("nan") if invalid_kind == "non-finite" else object()
    async with event_factory() as session:
        store = EventStore(session)
        with pytest.raises(EventPayloadError):
            await store.append(_event({"tool_state": {"value": invalid}}))
        assert await store.list_after("event-state-run") == []
        await store.append(_event({"tool_state": {"value": "valid"}}))
    async with event_factory() as session:
        events = await EventStore(session).list_after("event-state-run")
        assert len(events) == 1 and events[0].payload == {
            "tool_state": {"value": "valid"}
        }
    record_property("expected_failure_category", "EventPayloadError")
    record_property("invalid_serialization_kind", invalid_kind)
    record_property("rejected_payload_then_valid_commit", "verified")

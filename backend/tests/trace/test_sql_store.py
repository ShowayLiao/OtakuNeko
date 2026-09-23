from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy.ext.asyncio import (
    AsyncSession as SQLAlchemyAsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlmodel import SQLModel, select

from app.models.agent_trace import AgentTraceModel, TraceEventModel
from app.trace import AgentTrace, TraceEvent, TraceStep
from app.trace.sql_store import SqlTraceStore


def _trace(*, user_id: int, task_id: int, goal: str = "private") -> AgentTrace:
    trace = AgentTrace(user_id=user_id, task_id=task_id, goal=goal)
    step = TraceStep(step_index=0, step_label="capability", agent_name="agent")
    step.events.append(
        TraceEvent(
            event_type="capability_call",
            data={"operation": "anime.search", "api_key": "sk-secret"},
        )
    )
    step.complete()
    trace.add_step(step)
    trace.mark_completed()
    return trace


def test_trace_timestamp_columns_are_timezone_aware():
    assert AgentTraceModel.__table__.c.started_at.type.timezone is True
    assert AgentTraceModel.__table__.c.created_at.type.timezone is True
    assert TraceEventModel.__table__.c.created_at.type.timezone is True


@pytest.mark.asyncio
async def test_sql_store_round_trip_is_scoped_and_redacted(db_session):
    store = SqlTraceStore(db_session)
    trace = _trace(user_id=7, task_id=11)

    await store.record(trace)

    restored = await store.query(trace.trace_id, user_id=7)
    assert restored is not None
    assert restored.goal == "[REDACTED]"
    assert restored.task_id == 11
    assert restored.steps[0].events[0].data["api_key"] == "[REDACTED]"
    assert await store.query(trace.trace_id, user_id=8) is None
    header = (
        await db_session.exec(
            select(AgentTraceModel).where(AgentTraceModel.trace_id == trace.trace_id)
        )
    ).one()
    event = (
        await db_session.exec(
            select(TraceEventModel).where(TraceEventModel.trace_id == trace.trace_id)
        )
    ).one()
    raw_database_payload = f"{header.goal}{header.headers_json}{event.step_json}"
    assert "private" not in raw_database_payload
    assert "sk-secret" not in raw_database_payload


@pytest.mark.asyncio
async def test_sql_store_drops_unsafe_payload_but_keeps_event_error_code(db_session):
    trace = AgentTrace(user_id=7, task_id=12)
    step = TraceStep(step_index=0, step_label="policy", agent_name="agent")
    step.events.append(
        TraceEvent(
            event_type="failure",
            data={
                "chain_of_thought": "must not persist",
                "error_code": "policy_denied",
            },
            error_code="policy_denied",
            status="failed",
        )
    )
    step.complete()
    trace.add_step(step)
    trace.mark_failed("policy_denied")

    await SqlTraceStore(db_session).record(trace)

    restored = await SqlTraceStore(db_session).query(trace.trace_id, user_id=7)
    assert restored is not None
    event = restored.steps[0].events[0]
    assert event.event_type == "failure"
    assert event.error_code == "policy_denied"
    assert event.data == {
        "redaction": "unsafe_payload_dropped",
        "error_code": "policy_denied",
    }
    assert "must not persist" not in restored.model_dump_json()


@pytest.mark.asyncio
async def test_sql_store_maps_records_without_schema_version_to_legacy(db_session):
    trace_id = "legacy-trace"
    started_at = datetime.now(timezone.utc)
    legacy_event = {
        "event_id": "legacy-event",
        "event_type": "capability_call",
        "data": {"operation": "legacy"},
        "status": "completed",
        "correlation_id": trace_id,
    }
    legacy_step = {
        "step_index": 0,
        "step_label": "legacy",
        "agent_name": "agent",
        "status": "completed",
        "events": [legacy_event],
    }
    db_session.add(
        AgentTraceModel(
            trace_id=trace_id,
            user_id=9,
            agent_name="agent",
            status="completed",
            headers_json=json.dumps({"agent_name": "agent"}),
            started_at=started_at,
        )
    )
    db_session.add(
        TraceEventModel(
            trace_id=trace_id,
            step_index=0,
            step_label="legacy",
            agent_name="agent",
            status="completed",
            step_json=json.dumps(legacy_step),
        )
    )
    await db_session.commit()

    restored = await SqlTraceStore(db_session).query(trace_id, user_id=9)

    assert restored is not None
    assert restored.schema_version == 1
    assert restored.steps[0].events[0].schema_version == 1


@pytest.mark.asyncio
async def test_sql_store_count_retention_removes_events(db_session):
    store = SqlTraceStore(db_session, max_traces=1)
    first = _trace(user_id=7, task_id=1)
    second = _trace(user_id=7, task_id=2)
    first.started_at = second.started_at - timedelta(seconds=1)

    await store.record(first)
    await store.record(second)

    assert await store.query(first.trace_id, user_id=7) is None
    events = (
        await db_session.exec(
            select(TraceEventModel).where(TraceEventModel.trace_id == first.trace_id)
        )
    ).all()
    assert events == []


@pytest.mark.asyncio
async def test_sql_store_age_retention(db_session):
    store = SqlTraceStore(db_session, max_age=timedelta(days=1))
    old = _trace(user_id=7, task_id=1)
    await store.record(old)
    model = (
        await db_session.exec(
            select(AgentTraceModel).where(AgentTraceModel.trace_id == old.trace_id)
        )
    ).one()
    model.started_at = datetime.now(timezone.utc) - timedelta(days=2)
    db_session.add(model)
    await db_session.commit()

    await store.record(_trace(user_id=7, task_id=2))

    assert await store.query(old.trace_id, user_id=7) is None


@pytest.mark.asyncio
async def test_sql_store_stable_cursor_pagination(db_session):
    store = SqlTraceStore(db_session)
    traces = [_trace(user_id=7, task_id=index) for index in range(3)]
    for trace in traces:
        await store.record(trace)

    first_page, cursor = await store.list_page(limit=2, user_id=7)
    second_page, next_cursor = await store.list_page(limit=2, user_id=7, cursor=cursor)

    assert len(first_page) == 2
    assert len(second_page) == 1
    assert {trace.trace_id for trace in first_page}.isdisjoint(
        trace.trace_id for trace in second_page
    )
    assert next_cursor is None


@pytest.mark.asyncio
async def test_sql_store_filters_remain_user_scoped(db_session):
    store = SqlTraceStore(db_session)
    own = _trace(user_id=7, task_id=42)
    other = _trace(user_id=8, task_id=42)
    failed = _trace(user_id=7, task_id=43)
    failed.mark_failed("safe category")
    for trace in (own, other, failed):
        await store.record(trace)

    by_task, _ = await store.list_page(limit=10, user_id=7, task_id=42)
    by_status, _ = await store.list_page(limit=10, user_id=7, status="failed")

    assert [trace.trace_id for trace in by_task] == [own.trace_id]
    assert [trace.trace_id for trace in by_status] == [failed.trace_id]


@pytest.mark.asyncio
async def test_sql_store_survives_engine_restart(tmp_path):
    database_url = f"sqlite+aiosqlite:///{(tmp_path / 'traces.db').as_posix()}"
    first_engine = create_async_engine(database_url)
    async with first_engine.begin() as connection:
        await connection.run_sync(SQLModel.metadata.create_all)
    first_factory = async_sessionmaker(
        first_engine,
        class_=SQLAlchemyAsyncSession,
        expire_on_commit=False,
    )
    trace = _trace(user_id=7, task_id=9)
    async with first_factory() as session:
        await SqlTraceStore(session).record(trace)
    await first_engine.dispose()

    second_engine = create_async_engine(database_url)
    second_factory = async_sessionmaker(
        second_engine,
        class_=SQLAlchemyAsyncSession,
        expire_on_commit=False,
    )
    async with second_factory() as session:
        restored = await SqlTraceStore(session).query(trace.trace_id, user_id=7)
    await second_engine.dispose()

    assert restored is not None
    assert restored.task_id == 9
    assert len(restored.steps) == 1

"""Primary Trace updates preserve earlier execution segments and ownership."""

from datetime import datetime, timedelta, timezone

import pytest

from app.trace import AgentTrace, TraceEvent, TraceEventType, TraceStep
from app.trace.sql_store import SqlTraceStore


def projection(owner, status, sequence):
    trace = AgentTrace(
        trace_id="primary-projection",
        run_id="primary-run",
        user_id=owner,
        status=status,
        steps=[
            TraceStep(
                step_index=0,
                step_label="decision",
                agent_name="primary-runtime",
                events=[
                    TraceEvent(
                        run_id="primary-run",
                        sequence=sequence,
                        event_type=TraceEventType.MODEL_CALL,
                    )
                ],
            )
        ],
    )
    if status == "completed":
        trace.mark_completed()
    return trace


async def test_projection_update_merges_resume_without_duplicate_events(db_session):
    store = SqlTraceStore(db_session)
    assert callable(getattr(store, "record_projection", None))
    await store.record_projection(projection(7, "running", 1))
    await store.record_projection(projection(7, "completed", 2))
    await store.record_projection(projection(7, "completed", 2))
    result = await store.query("primary-projection", user_id=7)
    assert result is not None
    assert result.status == "completed"
    assert result.total_duration_ms is not None
    assert [event.sequence for step in result.steps for event in step.events] == [1, 2]
    with pytest.raises(ValueError, match="identity"):
        await store.record_projection(projection(8, "completed", 3))
    result = await store.query("primary-projection", user_id=7)
    assert result is not None
    assert [event.sequence for step in result.steps for event in step.events] == [1, 2]


async def test_projection_cannot_downgrade_terminal_state(db_session):
    store = SqlTraceStore(db_session)
    assert callable(getattr(store, "record_projection", None))
    await store.record_projection(projection(7, "completed", 1))
    await store.record_projection(projection(7, "running", 2))
    result = await store.query("primary-projection", user_id=7)
    assert result is not None
    assert result.status == "completed"
    assert [event.sequence for step in result.steps for event in step.events] == [1]


async def test_projection_cannot_downgrade_timeout_state(db_session):
    store = SqlTraceStore(db_session)
    timed_out = projection(7, "running", 1)
    timed_out.status = "timeout"
    timed_out.completed_at = datetime.now(timezone.utc)
    timed_out._set_duration()
    await store.record_projection(timed_out)
    await store.record_projection(projection(7, "running", 2))
    result = await store.query("primary-projection", user_id=7)
    assert result is not None
    assert result.status == "timeout"
    assert [event.sequence for step in result.steps for event in step.events] == [1]


async def test_projection_update_normalizes_naive_sql_timestamps(db_session):
    store = SqlTraceStore(db_session)
    base = datetime.now(timezone.utc).replace(tzinfo=None, microsecond=0)
    started = projection(7, "running", 1)
    started.started_at = base
    await store.record_projection(started)
    completed = projection(7, "running", 2)
    completed.status = "completed"
    completed.completed_at = base + timedelta(seconds=5)
    await store.record_projection(completed)
    result = await store.query("primary-projection", user_id=7)
    assert result is not None
    assert result.status == "completed"
    assert result.total_duration_ms == 5000.0

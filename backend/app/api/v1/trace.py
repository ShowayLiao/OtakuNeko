"""Trace query API.

Provides endpoints to retrieve agent execution traces for debugging
and observability.
"""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.user import UserRead
from app.api.deps import get_current_user
from app.db.database import get_session
from app.trace.sql_store import SqlTraceStore

router = APIRouter(prefix="/trace", tags=["trace"])

_trace_store: object = None


def init_trace_store(store) -> None:
    """Set the trace store instance shared with the agent runtime."""
    global _trace_store
    _trace_store = store


def _get_store(session: AsyncSession):
    return _trace_store or SqlTraceStore(session)


@router.get("/{trace_id}")
async def get_trace(
    trace_id: str,
    user: UserRead = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
):
    """Retrieve a single execution trace by ID."""
    store = _get_store(db)
    trace = await store.query(trace_id, user_id=user.id)
    if trace is None:
        raise HTTPException(status_code=404, detail="Trace not found")
    return trace.model_dump(mode="json")


@router.get("/")
async def list_traces(
    limit: int = Query(default=20, ge=1, le=100),
    cursor: str | None = None,
    user_id: int | None = None,
    task_id: int | None = None,
    status: str | None = Query(
        default=None,
        pattern="^(running|completed|failed|cancelled)$",
    ),
    started_after: datetime | None = None,
    started_before: datetime | None = None,
    user: UserRead = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
):
    """List recent traces, optionally filtered by user ID."""
    store = _get_store(db)
    # Trace data is private to the authenticated user.  The query parameter
    # is retained for backwards-compatible clients but cannot widen access.
    if hasattr(store, "list_page"):
        try:
            traces, next_cursor = await store.list_page(
                limit=limit,
                user_id=user.id,
                cursor=cursor,
                task_id=task_id,
                status=status,
                started_after=started_after,
                started_before=started_before,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
    else:
        traces = await store.list_recent(limit=limit, user_id=user.id)
        next_cursor = None
    return {
        "traces": [t.model_dump(mode="json") for t in traces],
        "total": len(traces),
        "next_cursor": next_cursor,
    }

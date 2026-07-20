"""Trace query API.

Provides endpoints to retrieve agent execution traces for debugging
and observability.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from app.schemas.user import UserRead
from app.api.deps import get_current_user

router = APIRouter(prefix="/trace", tags=["trace"])

_trace_store: object = None


def init_trace_store(store) -> None:
    """Set the trace store instance shared with the agent runtime."""
    global _trace_store
    _trace_store = store


def _get_store():
    if _trace_store is None:
        raise HTTPException(status_code=503, detail="Trace store not initialized")
    return _trace_store


@router.get("/{trace_id}")
async def get_trace(
    trace_id: str,
    user: UserRead = Depends(get_current_user),
):
    """Retrieve a single execution trace by ID."""
    store = _get_store()
    trace = await store.query(trace_id)
    if trace is None:
        raise HTTPException(status_code=404, detail="Trace not found")
    if trace.user_id is not None and trace.user_id != user.id:
        raise HTTPException(status_code=403, detail="Access denied")
    return trace.model_dump(mode="json")


@router.get("/")
async def list_traces(
    limit: int = Query(default=20, ge=1, le=100),
    user_id: int | None = None,
    user: UserRead = Depends(get_current_user),
):
    """List recent traces, optionally filtered by user ID."""
    store = _get_store()
    # Trace data is private to the authenticated user.  The query parameter
    # is retained for backwards-compatible clients but cannot widen access.
    traces = await store.list_recent(limit=limit, user_id=user.id)
    return {
        "traces": [t.model_dump(mode="json") for t in traces],
        "total": len(traces),
    }

"""Trace storage abstraction.

Provides a pluggable store for agent execution traces. Default
InMemoryTraceStore works for local dev; swap for a DB-backed
implementation in production.
"""

from __future__ import annotations

from typing import Protocol

from app.trace import AgentTrace


class TraceStore(Protocol):
    """Storage contract for agent execution traces."""

    async def record(self, trace: AgentTrace) -> None:
        """Persist a completed or failed trace."""
        ...

    async def query(self, trace_id: str) -> AgentTrace | None:
        """Retrieve a single trace by ID."""
        ...

    async def list_recent(
        self, limit: int = 20, user_id: int | None = None
    ) -> list[AgentTrace]:
        """Return recent traces, optionally filtered by user."""
        ...


class InMemoryTraceStore:
    """Non-persistent trace store backed by a dict."""

    def __init__(self, max_traces: int = 1000) -> None:
        self._traces: dict[str, AgentTrace] = {}
        self._max_traces = max_traces

    async def record(self, trace: AgentTrace) -> None:
        if len(self._traces) >= self._max_traces:
            oldest = min(
                self._traces.keys(),
                key=lambda k: self._traces[k].started_at,
            )
            del self._traces[oldest]
        self._traces[trace.trace_id] = trace

    async def query(self, trace_id: str) -> AgentTrace | None:
        return self._traces.get(trace_id)

    async def list_recent(
        self, limit: int = 20, user_id: int | None = None
    ) -> list[AgentTrace]:
        traces = list(self._traces.values())
        if user_id is not None:
            traces = [t for t in traces if t.user_id == user_id]
        traces.sort(key=lambda t: t.started_at, reverse=True)
        return traces[:limit]

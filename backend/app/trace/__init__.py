"""Agent execution trace models.

Captures the full lifecycle of an agent task — what ran, what
steps it took, how long each step took, and whether it succeeded.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class TraceEvent(BaseModel):
    """A single event within a trace step (tool call, node entry, etc.)."""

    event_type: str
    timestamp: datetime = Field(default_factory=_utc_now)
    data: dict[str, Any] = Field(default_factory=dict)
    duration_ms: float | None = None


class TraceStep(BaseModel):
    """One step in an agent execution trace."""

    step_index: int
    step_label: str
    agent_name: str
    started_at: datetime = Field(default_factory=_utc_now)
    completed_at: datetime | None = None
    status: str = "running"
    events: list[TraceEvent] = Field(default_factory=list)
    input_summary: str | None = None
    output_summary: str | None = None

    def complete(self) -> None:
        self.status = "completed"
        self.completed_at = _utc_now()

    def fail(self, error: str) -> None:
        self.status = "failed"
        self.completed_at = _utc_now()


class AgentTrace(BaseModel):
    """Full execution trace for one agent task."""

    trace_id: str = Field(default_factory=lambda: uuid4().hex)
    task_id: int | None = None
    user_id: int | None = None
    agent_name: str = ""
    goal: str = ""
    started_at: datetime = Field(default_factory=_utc_now)
    completed_at: datetime | None = None
    status: str = "running"
    steps: list[TraceStep] = Field(default_factory=list)
    total_duration_ms: float | None = None
    error: str | None = None

    def add_step(self, step: TraceStep) -> None:
        self.steps.append(step)

    def mark_completed(self) -> None:
        self.completed_at = _utc_now()
        self.status = "completed"
        if self.started_at:
            self.total_duration_ms = (
                self.completed_at - self.started_at
            ).total_seconds() * 1000

    def mark_failed(self, error: str) -> None:
        self.completed_at = _utc_now()
        self.status = "failed"
        self.error = error

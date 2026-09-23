"""Agent trace models — TRACE-002 Step 04.

Persists trace headers and structured events for durable observability.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import DateTime
from sqlmodel import Field, SQLModel


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class AgentTraceModel(SQLModel, table=True):
    __tablename__ = "agent_trace"

    id: Optional[int] = Field(default=None, primary_key=True)
    trace_id: str = Field(index=True, unique=True, nullable=False)
    user_id: Optional[int] = Field(index=True, default=None)
    task_id: Optional[int] = Field(index=True, default=None)
    agent_name: str = Field(default="")
    goal: str = Field(default="")
    status: str = Field(default="completed", index=True)
    headers_json: Optional[str] = Field(default=None)
    started_at: datetime = Field(  # type: ignore[call-overload]  # SQLModel Field stub lacks sa_type overload
        default_factory=_utc_now,
        index=True,
        sa_type=DateTime(timezone=True),
    )
    created_at: datetime = Field(  # type: ignore[call-overload]  # SQLModel Field stub lacks sa_type overload
        default_factory=_utc_now,
        index=True,
        sa_type=DateTime(timezone=True),
    )


class TraceEventModel(SQLModel, table=True):
    __tablename__ = "trace_event"

    id: Optional[int] = Field(default=None, primary_key=True)
    trace_id: str = Field(
        foreign_key="agent_trace.trace_id",
        ondelete="CASCADE",
        index=True,
        nullable=False,
    )
    step_index: int = Field(default=0)
    step_label: str = Field(default="")
    agent_name: str = Field(default="")
    status: str = Field(default="completed")
    step_json: Optional[str] = Field(default=None)
    created_at: datetime = Field(  # type: ignore[call-overload]  # SQLModel Field stub lacks sa_type overload
        default_factory=_utc_now,
        sa_type=DateTime(timezone=True),
    )

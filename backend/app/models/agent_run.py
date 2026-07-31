"""Durable interactive Run, Invocation and Event records."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Optional

from pydantic import field_validator
from sqlalchemy import DateTime, Index, UniqueConstraint
from sqlmodel import Field, SQLModel


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


RUN_STATUSES = {
    "queued",
    "running",
    "succeeded",
    "failed",
    "cancelled",
    "paused",
    "abandoned",
}

INVOCATION_STATUSES = {
    "pending",
    "running",
    "succeeded",
    "failed",
    "denied",
    "cancelled",
    "timed_out",
}


class AgentRun(SQLModel, table=True):
    """Durable lifecycle header for one interactive Agent Run."""

    __tablename__ = "agent_run"
    __table_args__ = (
        Index("ix_agent_run_status_created_at", "status", "created_at"),
    )

    run_id: str = Field(primary_key=True, nullable=False)
    user_id: Optional[int] = Field(
        default=None,
        foreign_key="users.id",
        index=True,
    )
    thread_id: Optional[str] = Field(default=None, index=True)
    status: str = Field(default="queued", index=True, nullable=False)
    goal_hash: str = Field(default="", nullable=False)
    model: str = Field(default="", nullable=False)
    started_at: Optional[datetime] = Field(
        default=None,
        sa_type=DateTime(timezone=True),
    )
    finished_at: Optional[datetime] = Field(
        default=None,
        sa_type=DateTime(timezone=True),
    )
    error_code: Optional[str] = Field(default=None, index=True)
    created_at: datetime = Field(
        default_factory=_utc_now,
        index=True,
        sa_type=DateTime(timezone=True),
    )

    @field_validator("status")
    @classmethod
    def validate_status(cls, value: str) -> str:
        if value not in RUN_STATUSES:
            raise ValueError(f"invalid AgentRun status: {value}")
        return value


class AgentInvocation(SQLModel, table=True):
    """Durable record for one controlled capability/tool invocation."""

    __tablename__ = "agent_invocation"
    __table_args__ = (
        UniqueConstraint(
            "run_id",
            "sequence",
            name="uq_agent_invocation_run_sequence",
        ),
        UniqueConstraint(
            "run_id",
            "idempotency_key",
            name="uq_agent_invocation_run_idempotency_key",
        ),
        Index("ix_agent_invocation_run_sequence", "run_id", "sequence"),
    )

    invocation_id: str = Field(primary_key=True, nullable=False)
    run_id: str = Field(
        foreign_key="agent_run.run_id",
        index=True,
        nullable=False,
    )
    sequence: int = Field(nullable=False)
    capability: str = Field(default="", nullable=False)
    capability_version: str = Field(default="v1", nullable=False)
    status: str = Field(default="pending", index=True, nullable=False)
    input_hash: str = Field(default="", nullable=False)
    idempotency_key: Optional[str] = Field(default=None, index=True)
    started_at: Optional[datetime] = Field(
        default=None,
        sa_type=DateTime(timezone=True),
    )
    finished_at: Optional[datetime] = Field(
        default=None,
        sa_type=DateTime(timezone=True),
    )
    error_code: Optional[str] = Field(default=None)

    @field_validator("status")
    @classmethod
    def validate_status(cls, value: str) -> str:
        if value not in INVOCATION_STATUSES:
            raise ValueError(f"invalid AgentInvocation status: {value}")
        return value


class AgentRunEvent(SQLModel, table=True):
    """Append-only, replayable Run event with a bounded safe JSON payload."""

    __tablename__ = "agent_run_event"
    __table_args__ = (
        UniqueConstraint(
            "run_id",
            "sequence",
            name="uq_agent_run_event_run_sequence",
        ),
        Index("ix_agent_run_event_run_sequence", "run_id", "sequence"),
    )

    event_id: str = Field(primary_key=True, nullable=False)
    run_id: str = Field(
        foreign_key="agent_run.run_id",
        index=True,
        nullable=False,
    )
    sequence: int = Field(nullable=False)
    event_type: str = Field(default="", nullable=False)
    invocation_id: Optional[str] = Field(default=None, index=True)
    payload_json: str = Field(default="{}", nullable=False)
    occurred_at: datetime = Field(
        default_factory=_utc_now,
        index=True,
        sa_type=DateTime(timezone=True),
    )

    @property
    def payload(self) -> dict[str, Any]:
        try:
            value = json.loads(self.payload_json or "{}")
        except json.JSONDecodeError:
            return {}
        return value if isinstance(value, dict) else {}

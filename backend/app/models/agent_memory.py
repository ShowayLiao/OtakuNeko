"""AgentMemory SQLModel — durable typed memory records.

Each row stores a single memory fact tied to a user and optionally a
thread, with a ``kind`` discriminator (episodic / semantic / profile).
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import CheckConstraint, DateTime, UniqueConstraint
from sqlmodel import Field, SQLModel


class AgentMemory(SQLModel, table=True):
    __tablename__ = "agent_memory"
    __table_args__ = (
        CheckConstraint(
            "kind IN ('episodic', 'semantic', 'profile')",
            name="ck_agent_memory_kind",
        ),
        CheckConstraint(
            "importance >= 0 AND importance <= 1",
            name="ck_agent_memory_importance",
        ),
        UniqueConstraint(
            "user_id",
            "thread_id",
            "fact_id",
            name="uq_agent_memory_user_thread_fact",
        ),
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    fact_id: str = Field(index=True, nullable=False)
    user_id: int = Field(foreign_key="users.id", index=True, nullable=False)
    thread_id: Optional[str] = Field(index=True, default=None)
    kind: str = Field(index=True, nullable=False)  # episodic | semantic | profile
    content: str = Field(nullable=False)
    importance: float = Field(default=0.5, ge=0.0, le=1.0)
    source: str = Field(default="conversation")
    created_at: datetime = Field(  # type: ignore[call-overload]  # SQLModel Field stub lacks sa_type overload
        default_factory=lambda: datetime.now(timezone.utc),
        nullable=False,
        index=True,
        sa_type=DateTime(timezone=True),
    )
    metadata_json: Optional[str] = Field(default=None)

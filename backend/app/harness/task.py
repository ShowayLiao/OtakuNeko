from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from pydantic import BaseModel, Field


def utc_now() -> datetime:
    """Return the current UTC datetime with timezone information."""
    return datetime.now(timezone.utc)


class AgentTask(BaseModel):
    """Minimal representation of an agent execution task."""

    model_config = {"populate_by_name": True}

    task_id: Optional[int] = Field(default=None, description="Unique task identifier")
    user_id: int = Field(description="ID of the user who created this task")
    goal: str = Field(description="The goal or prompt for the agent to execute")
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        alias="task_metadata",
        description="Arbitrary metadata attached to the task",
    )
    created_at: datetime = Field(
        default_factory=utc_now,
        description="UTC timestamp when the task was created",
    )

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from app.harness.task import AgentTask
from app.harness.contracts import RunResult


class AgentState(BaseModel):
    """Execution state tracked during an agent run."""

    task: AgentTask = Field(description="The task being executed")
    current_step: str = Field(default="", description="Label of the current execution step")
    context: dict[str, Any] = Field(default_factory=dict, description="Scratch context accumulated during execution")
    result: Any = Field(default=None, description="Final result produced by the agent")
    status: str = Field(
        default="pending",
        description="Execution status: pending | running | completed | failed | cancelled | timeout",
    )
    terminal_result: RunResult | None = Field(
        default=None,
        exclude=True,
        description="The single in-memory terminal result owned by the Coordinator",
    )
    budget: dict[str, Any] = Field(
        default_factory=dict,
        exclude=True,
        description="In-memory budget snapshot; durable Run/Event state is deferred",
    )

    def to_dict(self) -> dict[str, Any]:
        """Serialize state to a plain dict for persistence."""
        return self.model_dump()

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AgentState:
        """Restore state from a plain dict."""
        return cls.model_validate(data)

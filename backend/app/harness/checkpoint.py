from __future__ import annotations

from typing import Protocol

from app.harness.state import AgentState


class CheckpointStore(Protocol):
    """Abstract checkpoint persistence interface.

    HARNESS-002: interface only, no database implementation.
    """

    async def save_state(self, state: AgentState) -> None:
        ...

    async def load_state(self, task_id: int) -> AgentState | None:
        ...


class InMemoryCheckpointStore:
    """In-memory checkpoint store for testing and local development."""

    def __init__(self):
        self._states: dict[int, AgentState] = {}

    async def save_state(self, state: AgentState) -> None:
        task_id = state.task.task_id
        if task_id is not None:
            self._states[task_id] = state

    async def load_state(self, task_id: int) -> AgentState | None:
        return self._states.get(task_id)

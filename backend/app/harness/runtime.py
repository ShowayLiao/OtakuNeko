from __future__ import annotations

from typing import Any, AsyncIterator, Protocol

from app.harness.checkpoint import CheckpointStore
from app.harness.task import AgentTask
from app.harness.state import AgentState


class AgentAdapter(Protocol):
    """Protocol for agent implementations that the runtime can invoke.

    Non-streaming agents implement this protocol.
    """

    async def run(self, state: AgentState) -> Any:
        ...


class StreamingAgentAdapter(Protocol):
    """Protocol for agents that expose incremental output."""

    async def stream(self, state: AgentState, **kwargs: Any) -> AsyncIterator[Any]:
        ...


class AgentRuntime:
    """Execution wrapper around an agent adapter.

    Responsibilities:
    - receive task
    - create state
    - invoke adapter
    - return result
    """

    def __init__(
        self,
        adapter: AgentAdapter | StreamingAgentAdapter,
        checkpoint_store: CheckpointStore | None = None,
    ):
        self.adapter = adapter
        self.checkpoint_store = checkpoint_store

    async def _save_checkpoint(self, state: AgentState) -> None:
        if self.checkpoint_store is not None:
            await self.checkpoint_store.save_state(state)

    async def execute(self, task: AgentTask) -> AgentState:
        state = AgentState(task=task, status="running")
        await self._save_checkpoint(state)
        try:
            state.result = await self.adapter.run(state)
            state.status = "completed"
        except Exception:
            state.status = "failed"
            await self._save_checkpoint(state)
            raise
        await self._save_checkpoint(state)
        return state

    async def stream(self, task: AgentTask, **kwargs: Any) -> AsyncIterator[Any]:
        """Stream an agent response while tracking its execution state."""
        state = AgentState(task=task, status="running", context=kwargs)
        await self._save_checkpoint(state)
        try:
            stream = getattr(self.adapter, "stream", None)
            if stream is None:
                raise TypeError("The configured adapter does not support streaming")
            async for chunk in stream(state, **kwargs):
                yield chunk
        except Exception:
            state.status = "failed"
            await self._save_checkpoint(state)
            raise
        state.status = "completed"
        await self._save_checkpoint(state)

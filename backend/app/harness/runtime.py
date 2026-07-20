from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, AsyncIterator, Protocol

from app.harness.checkpoint import CheckpointStore
from app.harness.task import AgentTask
from app.harness.state import AgentState
from app.trace import AgentTrace
from app.trace.store import TraceStore


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


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

    When a TraceStore is provided, the runtime emits lifecycle trace
    events (task_start, task_end, task_failed) automatically.  No
    overhead when trace_store is None (the default).
    """

    def __init__(
        self,
        adapter: AgentAdapter | StreamingAgentAdapter,
        checkpoint_store: CheckpointStore | None = None,
        *,
        trace_store: TraceStore | None = None,
    ):
        self.adapter = adapter
        self.checkpoint_store = checkpoint_store
        self.trace_store = trace_store

    @property
    def adapter_name(self) -> str:
        """Human-readable identifier for the wrapped adapter."""
        cls = getattr(self.adapter, "__class__", None)
        if cls is not None:
            return cls.__name__
        return type(self.adapter).__name__

    async def _save_checkpoint(self, state: AgentState) -> None:
        if self.checkpoint_store is not None:
            await self.checkpoint_store.save_state(state)

    async def execute(self, task: AgentTask) -> AgentState:
        trace: AgentTrace | None = None
        if self.trace_store is not None:
            trace = AgentTrace(
                task_id=task.task_id,
                user_id=task.user_id,
                agent_name=self.adapter_name,
                goal=task.goal,
            )

        state = AgentState(task=task, status="running")
        await self._save_checkpoint(state)
        try:
            state.result = await self.adapter.run(state)
            state.status = "completed"
            if trace is not None:
                trace.mark_completed()
        except Exception:
            state.status = "failed"
            if trace is not None:
                trace.mark_failed("execute() raised an exception")
            await self._save_checkpoint(state)
            raise
        finally:
            if trace is not None and self.trace_store is not None:
                await self.trace_store.record(trace)
        await self._save_checkpoint(state)
        return state

    async def stream(self, task: AgentTask, **kwargs: Any) -> AsyncIterator[Any]:
        """Stream an agent response while tracking its execution state."""
        trace: AgentTrace | None = None
        if self.trace_store is not None:
            trace = AgentTrace(
                task_id=task.task_id,
                user_id=task.user_id,
                agent_name=self.adapter_name,
                goal=task.goal,
            )

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
            if trace is not None:
                trace.mark_failed("stream() raised an exception")
            await self._save_checkpoint(state)
            raise
        finally:
            if trace is not None and self.trace_store is not None:
                if trace.status == "running":
                    trace.mark_completed()
                await self.trace_store.record(trace)
        state.status = "completed"
        await self._save_checkpoint(state)

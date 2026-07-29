from __future__ import annotations

import asyncio
from contextlib import nullcontext
from datetime import datetime, timezone
from typing import Any, AsyncIterator, Protocol

from app.harness.checkpoint import CheckpointStore
from app.harness.task import AgentTask
from app.harness.state import AgentState
from app.trace import AgentTrace, TraceEvent, TraceEventType, TraceStep
from app.trace.redaction import sanitize_trace
from app.trace.recorder import bind_trace
from app.trace.store import TraceStore
from app.core.logging import get_logger

logger = get_logger(__name__)


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

    async def _record_trace(self, trace: AgentTrace) -> None:
        if self.trace_store is None:
            return
        try:
            await self.trace_store.record(sanitize_trace(trace))
        except Exception:
            logger.exception(
                "trace_storage_failed",
                extra={"trace_id": trace.trace_id},
            )

    async def execute(self, task: AgentTask) -> AgentState:
        trace: AgentTrace | None = None
        if self.trace_store is not None:
            trace = AgentTrace(
                task_id=task.task_id,
                user_id=task.user_id,
                agent_name=self.adapter_name,
                goal=task.goal,
            )
            if task.metadata.get("trace_id"):
                trace.trace_id = str(task.metadata["trace_id"])
            scheduled_step = TraceStep(
                    step_index=0,
                    step_label="scheduled_context",
                    agent_name=self.adapter_name,
                    input_summary=str(
                        {
                            "task_def_id": task.metadata.get("task_def_id"),
                            "run_id": task.metadata.get("run_id"),
                            "scheduled_slot": task.metadata.get("scheduled_slot"),
                        }
                    ),
                )
            scheduled_step.complete()
            trace.steps.append(scheduled_step)

        state = AgentState(task=task, status="running")
        await self._save_checkpoint(state)
        try:
            trace_context = bind_trace(trace) if trace is not None else nullcontext()
            with trace_context as recorder:
                if recorder is not None:
                    recorder.record(
                        TraceEventType.NODE_START,
                        "agent.execute",
                        {"agent": self.adapter_name},
                    )
                try:
                    state.result = await self.adapter.run(state)
                except BaseException as exc:
                    if recorder is not None:
                        status = (
                            "cancelled"
                            if isinstance(exc, (asyncio.CancelledError, GeneratorExit))
                            else "failed"
                        )
                        recorder.record(
                            TraceEventType.FAILURE,
                            "agent.execute",
                            {"error_category": type(exc).__name__},
                            status=status,
                        )
                        recorder.record(
                            TraceEventType.NODE_END,
                            "agent.execute",
                            {"outcome": status},
                            status=status,
                        )
                    raise
                if recorder is not None:
                    recorder.record(
                        TraceEventType.NODE_END,
                        "agent.execute",
                        {"outcome": "completed"},
                    )
            state.status = "completed"
            if trace is not None:
                trace.mark_completed()
        except (asyncio.CancelledError, GeneratorExit):
            state.status = "cancelled"
            if trace is not None:
                trace.mark_cancelled()
            await self._save_checkpoint(state)
            raise
        except Exception:
            state.status = "failed"
            if trace is not None:
                trace.mark_failed("execute() raised an exception")
            await self._save_checkpoint(state)
            raise
        finally:
            if trace is not None and self.trace_store is not None:
                await self._record_trace(trace)
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
        stream_completed = False
        try:
            stream = getattr(self.adapter, "stream", None)
            if stream is None:
                raise TypeError("The configured adapter does not support streaming")
            trace_context = bind_trace(trace) if trace is not None else nullcontext()
            with trace_context as recorder:
                if recorder is not None:
                    recorder.record(
                        TraceEventType.NODE_START,
                        "agent.stream",
                        {"agent": self.adapter_name},
                    )
                try:
                    async for chunk in stream(state, **kwargs):
                        if trace is not None and isinstance(chunk, dict):
                            self._record_stream_trace(trace, chunk)
                        yield chunk
                except BaseException as exc:
                    if recorder is not None:
                        status = (
                            "cancelled"
                            if isinstance(exc, (asyncio.CancelledError, GeneratorExit))
                            else "failed"
                        )
                        recorder.record(
                            TraceEventType.FAILURE,
                            "agent.stream",
                            {"error_category": type(exc).__name__},
                            status=status,
                        )
                        recorder.record(
                            TraceEventType.NODE_END,
                            "agent.stream",
                            {"outcome": status},
                            status=status,
                        )
                    raise
                if recorder is not None:
                    recorder.record(
                        TraceEventType.NODE_END,
                        "agent.stream",
                        {"outcome": "completed"},
                    )
            stream_completed = True
        except (asyncio.CancelledError, GeneratorExit):
            state.status = "cancelled"
            if trace is not None:
                trace.mark_cancelled()
            await self._save_checkpoint(state)
            raise
        except Exception:
            state.status = "failed"
            if trace is not None:
                trace.mark_failed("stream() raised an exception")
            await self._save_checkpoint(state)
            raise
        finally:
            if trace is not None and self.trace_store is not None:
                if trace.status == "running":
                    if stream_completed:
                        trace.mark_completed()
                    else:
                        trace.mark_cancelled()
                await self._record_trace(trace)
        state.status = "completed"
        await self._save_checkpoint(state)

    def _record_stream_trace(self, trace: AgentTrace, chunk: dict[str, Any]) -> None:
        if chunk.get("type") != "route_decision":
            return
        step = TraceStep(
            step_index=len(trace.steps),
            step_label="routing",
            agent_name=str(chunk.get("agent", self.adapter_name)),
            output_summary=str(chunk.get("route", "unknown")),
        )
        step.events.append(
            TraceEvent(
                event_type=TraceEventType.ROUTING_DECISION,
                correlation_id=trace.trace_id,
                data={
                    "route": chunk.get("route"),
                    "agent": chunk.get("agent"),
                    "confidence": chunk.get("confidence"),
                    "rationale_present": bool(chunk.get("rationale")),
                },
                status="completed",
            )
        )
        step.complete()
        trace.add_step(step)

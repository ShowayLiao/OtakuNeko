"""Context-local structured trace recording for agent boundaries."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager, contextmanager
from contextvars import ContextVar
from datetime import datetime, timezone
from time import monotonic
from typing import Any, AsyncIterator, Iterator

from app.trace import AgentTrace, TraceEvent, TraceEventType, TraceStep
from app.trace.redaction import redact

_current_recorder: ContextVar[TraceRecorder | None] = ContextVar(
    "current_trace_recorder", default=None
)
_current_parent_event_id: ContextVar[str | None] = ContextVar(
    "current_parent_trace_event_id", default=None
)


def safe_argument_shape(value: Any) -> Any:
    """Describe input structure without retaining input values."""
    if isinstance(value, dict):
        return {
            str(key): safe_argument_shape(child)
            for key, child in list(value.items())[:200]
        }
    if isinstance(value, (list, tuple)):
        child_types = sorted({type(child).__name__ for child in value[:200]})
        return {"type": "list", "length": min(len(value), 200), "items": child_types}
    if value is None:
        return "null"
    return type(value).__name__


class TraceRecorder:
    """Append bounded spans to one trace while preserving parent context."""

    def __init__(self, trace: AgentTrace) -> None:
        self.trace = trace

    @asynccontextmanager
    async def span(
        self,
        event_type: TraceEventType | str,
        operation: str,
        data: dict[str, Any] | None = None,
    ) -> AsyncIterator[TraceEvent]:
        event = TraceEvent(
            event_type=event_type,
            correlation_id=self.trace.trace_id,
            parent_event_id=_current_parent_event_id.get(),
            data=redact({"operation": operation, **(data or {})}),
        )
        step = TraceStep(
            step_index=len(self.trace.steps),
            step_label=operation,
            agent_name=self.trace.agent_name,
        )
        step.events.append(event)
        self.trace.add_step(step)
        parent_token = _current_parent_event_id.set(event.event_id)
        started = monotonic()
        try:
            yield event
        except asyncio.TimeoutError:
            event.status = "timeout"
            event.data["error_category"] = "timeout"
            step.status = "timeout"
            raise
        except asyncio.CancelledError:
            event.status = "cancelled"
            event.data["error_category"] = "cancelled"
            step.status = "cancelled"
            raise
        except GeneratorExit:
            event.status = "cancelled"
            event.data["error_category"] = "cancelled"
            step.status = "cancelled"
            raise
        except Exception as exc:
            event.status = "failed"
            event.data["error_category"] = type(exc).__name__
            step.status = "failed"
            raise
        finally:
            event.duration_ms = (monotonic() - started) * 1000
            if event.status == "running":
                event.status = "completed"
            if step.status == "running":
                step.status = event.status
            step.completed_at = datetime.now(timezone.utc)
            _current_parent_event_id.reset(parent_token)

    def record(
        self,
        event_type: TraceEventType | str,
        operation: str,
        data: dict[str, Any] | None = None,
        *,
        status: str = "completed",
        parent_event_id: str | None = None,
        duration_ms: float = 0,
    ) -> TraceEvent:
        event = TraceEvent(
            event_type=event_type,
            correlation_id=self.trace.trace_id,
            parent_event_id=parent_event_id or _current_parent_event_id.get(),
            data=redact({"operation": operation, **(data or {})}),
            status=status,
            duration_ms=duration_ms,
        )
        step = TraceStep(
            step_index=len(self.trace.steps),
            step_label=operation,
            agent_name=self.trace.agent_name,
        )
        step.events.append(event)
        step.complete()
        if status != "completed":
            step.status = status
        self.trace.add_step(step)
        return event


@contextmanager
def bind_trace(trace: AgentTrace) -> Iterator[TraceRecorder]:
    recorder = TraceRecorder(trace)
    recorder_token = _current_recorder.set(recorder)
    parent_token = _current_parent_event_id.set(None)
    try:
        yield recorder
    finally:
        _current_parent_event_id.reset(parent_token)
        _current_recorder.reset(recorder_token)


def current_trace_recorder() -> TraceRecorder | None:
    return _current_recorder.get()


@asynccontextmanager
async def trace_span(
    event_type: TraceEventType | str,
    operation: str,
    data: dict[str, Any] | None = None,
) -> AsyncIterator[TraceEvent | None]:
    recorder = current_trace_recorder()
    if recorder is None:
        yield None
        return
    async with recorder.span(event_type, operation, data) as event:
        yield event

"""Context-local structured trace recording for agent boundaries."""

from __future__ import annotations

import asyncio
import hashlib
import json
from contextlib import asynccontextmanager, contextmanager
from contextvars import ContextVar
from datetime import datetime, timezone
from time import monotonic
from typing import Any, AsyncIterator, Iterator, Literal, cast

from app.trace import AgentTrace, TraceEvent, TraceEventType, TraceStep
from app.trace.redaction import redact

_current_recorder: ContextVar[TraceRecorder | None] = ContextVar(
    "current_trace_recorder", default=None
)
_current_parent_event_id: ContextVar[str | None] = ContextVar(
    "current_parent_trace_event_id", default=None
)

_OBSERVED_VALUE_KEYS = frozenset(
    {
        "arguments",
        "content",
        "input",
        "messages",
        "output",
        "prompt",
        "raw_prompt",
        "response",
        "result",
        "text",
        "tool_output",
    }
)
_ERROR_VALUE_KEYS = frozenset({"error", "error_detail", "exception"})
_USAGE_KEYS = frozenset(
    {
        "cached_tokens",
        "completion_tokens",
        "cost_usd",
        "input_tokens",
        "output_tokens",
        "prompt_tokens",
        "reasoning_tokens",
        "total_tokens",
    }
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


def _payload_hash(value: Any) -> str:
    try:
        encoded = json.dumps(
            redact(value),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        )
    except (TypeError, ValueError):
        encoded = repr(type(value).__name__)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _safe_observation(value: Any) -> dict[str, Any]:
    if isinstance(value, str):
        return {
            "length": len(value),
            "sha256": hashlib.sha256(value.encode("utf-8")).hexdigest(),
        }
    if isinstance(value, (dict, list, tuple)):
        return {"count": len(value), "sha256": _payload_hash(value)}
    return {
        "type": type(value).__name__,
        "sha256": _payload_hash(value),
    }


def _safe_event_data(data: dict[str, Any]) -> dict[str, Any]:
    safe: dict[str, Any] = {}
    for key, value in data.items():
        normalized = str(key).lower().replace("-", "_").replace(" ", "_")
        if normalized in _OBSERVED_VALUE_KEYS:
            safe[str(key)] = _safe_observation(value)
        elif normalized in _ERROR_VALUE_KEYS:
            safe[str(key)] = {"error_category": type(value).__name__}
        else:
            safe[str(key)] = redact(value)
    return safe


def _event_metadata(data: dict[str, Any]) -> dict[str, Any]:
    usage = data.get("usage")
    return {
        "run_id": data.get("run_id"),
        "invocation_id": data.get("invocation_id"),
        "provider": data.get("provider"),
        "model": data.get("model"),
        "usage": _safe_usage(usage),
        "latency_ms": data.get("latency_ms", data.get("duration_ms")),
        "error_code": data.get("error_code"),
    }


def _safe_usage(value: Any) -> dict[str, int | float]:
    if not isinstance(value, dict):
        return {}
    safe: dict[str, int | float] = {}
    for key, item in value.items():
        normalized = str(key).lower().replace("-", "_").replace(" ", "_")
        if (
            normalized in _USAGE_KEYS
            and isinstance(item, (int, float))
            and not isinstance(item, bool)
        ):
            safe[normalized] = item
    return safe


class TraceRecorder:
    """Append bounded spans to one trace while preserving parent context."""

    def __init__(self, trace: AgentTrace, *, run_id: str | None = None) -> None:
        self.trace = trace
        if run_id is not None:
            self.trace.run_id = run_id
        self.run_id = run_id or trace.run_id or trace.trace_id
        self._sequence = max(
            (event.sequence or 0 for step in trace.steps for event in step.events),
            default=0,
        )

    def _new_event(
        self,
        event_type: TraceEventType | str,
        operation: str,
        data: dict[str, Any] | None,
        *,
        status: str = "running",
        duration_ms: float | None = None,
        parent_event_id: str | None = None,
    ) -> TraceEvent:
        raw_data = {"operation": operation, **(data or {})}
        metadata = _event_metadata(raw_data)
        self._sequence += 1
        return TraceEvent(
            event_type=TraceEventType(event_type),
            run_id=metadata["run_id"] or self.run_id,
            sequence=self._sequence,
            data=_safe_event_data(raw_data),
            status=cast(
                Literal["running", "completed", "failed", "timeout", "cancelled"],
                status,
            ),
            duration_ms=duration_ms,
            latency_ms=metadata["latency_ms"],
            correlation_id=self.run_id,
            parent_event_id=parent_event_id or _current_parent_event_id.get(),
            invocation_id=metadata["invocation_id"],
            provider=metadata["provider"],
            model=metadata["model"],
            usage=metadata["usage"],
            error_code=metadata["error_code"],
        )

    @asynccontextmanager
    async def span(
        self,
        event_type: TraceEventType | str,
        operation: str,
        data: dict[str, Any] | None = None,
    ) -> AsyncIterator[TraceEvent]:
        event = self._new_event(event_type, operation, data)
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
            event.latency_ms = event.duration_ms
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
        event = self._new_event(
            event_type,
            operation,
            data,
            status=status,
            duration_ms=duration_ms,
            parent_event_id=parent_event_id,
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
def bind_trace(
    trace: AgentTrace, *, run_id: str | None = None
) -> Iterator[TraceRecorder]:
    recorder = TraceRecorder(trace, run_id=run_id)
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

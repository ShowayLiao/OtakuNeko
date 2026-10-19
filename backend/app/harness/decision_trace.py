"""Safe projection from canonical Runtime events into agent traces."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from math import isfinite
from typing import Any, Literal
from uuid import uuid4

from app.harness.contracts import ExecutionContext
from app.harness.task import AgentTask
from app.trace import AgentTrace, TraceEvent, TraceEventType, TraceStep


_EVENT_TYPES = {
    "model_call": TraceEventType.MODEL_CALL,
    "tool_call_start": TraceEventType.TOOL_CALL_START,
    "tool_call_end": TraceEventType.TOOL_CALL_END,
    "policy_denied": TraceEventType.FAILURE,
    "run_failed": TraceEventType.FAILURE,
    "error": TraceEventType.FAILURE,
    "budget_exceeded": TraceEventType.FAILURE,
    "run_completed": TraceEventType.AGENT_RESULT,
    "cancelled": TraceEventType.AGENT_RESULT,
    "run_cancelled": TraceEventType.AGENT_RESULT,
    "timeout": TraceEventType.AGENT_RESULT,
    "run_timeout": TraceEventType.AGENT_RESULT,
}
_FAILURE_EVENT_TYPES = {"policy_denied", "run_failed", "error", "budget_exceeded"}
_CANCELLED_EVENT_TYPES = {"cancelled", "run_cancelled"}
_TIMEOUT_EVENT_TYPES = {"timeout", "run_timeout"}
_USAGE_INTEGER_FIELDS = (
    "prompt_tokens",
    "completion_tokens",
    "total_tokens",
    "latency_ms",
)
_USAGE_COST_FIELD = "estimated_cost_usd"
_ERROR_CODE_PATTERN = re.compile(r"[a-z][a-z0-9_]{0,63}\Z")
_EventStatus = Literal["running", "completed", "failed", "timeout", "cancelled"]


def _safe_error_code(value: Any) -> str | None:
    if isinstance(value, str) and _ERROR_CODE_PATTERN.fullmatch(value):
        return value
    return None


def _safe_number(value: Any) -> int | float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    try:
        normalized = float(value)
    except OverflowError:
        return None
    if not isfinite(normalized) or normalized < 0:
        return None
    return normalized


def _safe_usage(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}

    safe: dict[str, Any] = {}
    for key in _USAGE_INTEGER_FIELDS:
        item = value.get(key)
        if type(item) is int and item >= 0:
            safe[key] = item

    cost = value.get(_USAGE_COST_FIELD)
    if isinstance(cost, str) and len(cost) <= 32:
        try:
            parsed_cost = Decimal(cost)
        except InvalidOperation:
            pass
        else:
            if parsed_cost.is_finite() and parsed_cost >= 0:
                safe[_USAGE_COST_FIELD] = cost
    elif isinstance(cost, (int, float)):
        safe_cost = _safe_number(cost)
        if safe_cost is not None:
            safe[_USAGE_COST_FIELD] = safe_cost

    return safe


def _event_status(event_type: str, value: Any) -> _EventStatus:
    if event_type in _FAILURE_EVENT_TYPES:
        return "failed"
    if event_type in _CANCELLED_EVENT_TYPES:
        return "cancelled"
    if event_type in _TIMEOUT_EVENT_TYPES:
        return "timeout"
    if event_type == "run_completed":
        return "completed"

    if not isinstance(value, str):
        return "running"
    status = value.lower()
    if status in {"success", "succeeded", "completed", "degraded"}:
        return "completed"
    if status in {"failure", "failed", "denied", "policy_denied", "error"}:
        return "failed"
    if status in {"timeout", "timed_out"}:
        return "timeout"
    if status in {"cancelled", "canceled"}:
        return "cancelled"
    return "running"


class DecisionTraceProjection:
    """Project a narrow, safe subset of Runtime events into an ``AgentTrace``."""

    def __init__(self, context: ExecutionContext, task: AgentTask) -> None:
        self.trace = AgentTrace(
            trace_id=context.trace_id,
            run_id=context.run_id,
            user_id=context.principal_id,
            agent_name="primary-runtime",
            goal="",
        )
        self._step: TraceStep | None = None

    def _get_step(self) -> TraceStep:
        if self._step is None:
            self._step = TraceStep(
                step_index=0,
                step_label="primary-runtime",
                agent_name="primary-runtime",
            )
            self.trace.add_step(self._step)
        return self._step

    def observe(self, event: dict[str, Any]) -> None:
        """Append a whitelisted projection of one Runtime stream event."""
        raw_type = event.get("type")
        if not isinstance(raw_type, str):
            return
        event_type = raw_type.strip().lower()
        trace_event_type = _EVENT_TYPES.get(event_type)
        if trace_event_type is None:
            return

        sequence = event.get("sequence")
        if type(sequence) is not int or sequence < 1:
            sequence = None

        invocation_id = event.get("invocation_id")
        if not isinstance(invocation_id, str) or not invocation_id:
            invocation_id = None

        event_id = event.get("event_id")
        if not isinstance(event_id, str) or not event_id:
            event_id = None

        provider = event.get("provider")
        if not isinstance(provider, str):
            provider = None

        model = event.get("model")
        if not isinstance(model, str):
            model = None

        usage = _safe_usage(event.get("usage"))
        latency_ms = _safe_number(event.get("latency_ms"))
        if latency_ms is None:
            latency_ms = _safe_number(usage.get("latency_ms"))

        trace_event = TraceEvent(
            event_id=event_id or uuid4().hex,
            run_id=self.trace.run_id,
            sequence=sequence,
            event_type=trace_event_type,
            data={},
            duration_ms=_safe_number(event.get("duration_ms")),
            latency_ms=latency_ms,
            status=_event_status(event_type, event.get("status")),
            invocation_id=invocation_id,
            provider=provider,
            model=model,
            usage=usage,
            error_code=_safe_error_code(event.get("error_code")),
        )
        self._get_step().events.append(trace_event)

    def finish(self, status: str, error_code: str | None = None) -> AgentTrace:
        """Set a terminal status and finish projected steps; pauses remain open."""
        normalized_status = status.lower() if isinstance(status, str) else ""
        status_map = {
            "success": "completed",
            "succeeded": "completed",
            "completed": "completed",
            "failure": "failed",
            "failed": "failed",
            "timeout": "timeout",
            "timed_out": "timeout",
            "cancelled": "cancelled",
            "canceled": "cancelled",
        }
        terminal_status = status_map.get(normalized_status)
        if terminal_status is None:
            return self.trace

        completed_at = datetime.now(timezone.utc)
        self.trace.status = terminal_status
        self.trace.completed_at = completed_at
        self.trace.total_duration_ms = (
            completed_at - self.trace.started_at
        ).total_seconds() * 1000
        self.trace.error = _safe_error_code(error_code)

        for step in self.trace.steps:
            if step.completed_at is None:
                step.status = terminal_status
                step.completed_at = completed_at

        return self.trace

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
    "route_decision": TraceEventType.ROUTING_DECISION,
    "agent_result": TraceEventType.AGENT_RESULT,
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
_SAFE_DECISION_FIELDS = frozenset(
    {
        "schema_version",
        "decision_id",
        "run_id",
        "action",
        "capability",
        "capability_version",
        "arguments",
        "content",
        "other",
    }
)
_SAFE_DECISION_REASONS = frozenset(
    {
        "invalid_model_result",
        "model_cancelled",
        "provider_failure",
        "invalid_decision_shape",
        "schema_version_mismatch",
        "run_identity_mismatch",
        "authority_field_rejected",
        "decision_schema_invalid",
        "missing_capability",
        "missing_capability_version",
        "capability_version_mismatch",
        "invalid_arguments",
        "arguments_too_large",
        "multiple_tool_proposals",
        "invalid_tool_arguments",
        "empty_model_output",
        "invalid_json",
        "invalid_decision",
    }
)
_SAFE_FINISH_REASONS = frozenset(
    {
        "stop",
        "length",
        "tool_calls",
        "function_call",
        "content_filter",
        "end_turn",
        "max_tokens",
        "stop_sequence",
        "safety",
        "recitation",
        "other",
    }
)
_SAFE_PROVIDER_CATEGORIES = frozenset(
    {
        "authentication",
        "invalid_request",
        "not_found",
        "rate_limit",
        "server_error",
        "timeout",
        "network",
        "network_blocked",
        "dns",
        "endpoint_policy",
        "cancelled",
        "other",
    }
)
_SAFE_PROVIDER_ERROR_CODES = frozenset(
    {
        "auth",
        "rate_limited",
        "timeout",
        "invalid_request",
        "not_found",
        "server_error",
        "transient",
        "network_blocked",
        "permanent",
        "cancelled",
        "dns",
        "ssrf",
    }
)
_SAFE_PROVIDER_STAGES = frozenset(
    {
        "connection_check",
        "request",
        "stream_iteration",
        "response_normalization",
        "gateway_stream",
        "unknown",
    }
)
_SAFE_PROVIDER_RESPONSE_CODES = frozenset(
    {
        "account_deactivated",
        "billing_hard_limit_reached",
        "context_length_exceeded",
        "incorrect_api_key",
        "insufficient_quota",
        "invalid_api_key",
        "invalid_parameter",
        "invalid_request_error",
        "model_not_found",
        "not_found_error",
        "overloaded_error",
        "permission_denied",
        "rate_limit_exceeded",
        "server_error",
        "unsupported_value",
    }
)
_SAFE_PROVIDER_RESPONSE_TYPES = frozenset(
    {
        "authentication_error",
        "invalid_request_error",
        "not_found_error",
        "permission_error",
        "rate_limit_error",
        "server_error",
    }
)
_SAFE_PROVIDER_PARAMS = frozenset(
    {
        "input",
        "max_tokens",
        "messages",
        "model",
        "prompt",
        "response_format",
        "stream",
        "temperature",
        "tool_choice",
        "tools",
    }
)


def _safe_error_code(value: Any) -> str | None:
    if isinstance(value, str) and _ERROR_CODE_PATTERN.fullmatch(value):
        return value
    return None


def _safe_trace_identifier(value: Any) -> str | None:
    if (
        isinstance(value, str)
        and 1 <= len(value) <= 64
        and re.fullmatch(r"[A-Za-z0-9_.-]+", value)
    ):
        return value
    return None


def _safe_decision_reason(value: Any) -> str | None:
    if isinstance(value, str) and value in _SAFE_DECISION_REASONS:
        return value
    return None


def _safe_decision_fields(value: Any) -> list[str]:
    if not isinstance(value, (list, tuple)):
        return []
    fields: set[str] = set()
    for item in value[:8]:
        field = (
            item if isinstance(item, str) and item in _SAFE_DECISION_FIELDS else "other"
        )
        fields.add(field)
    return sorted(fields)


def _safe_finish_reason(value: Any) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    normalized = value.strip().lower().replace(" ", "_")
    return normalized if normalized in _SAFE_FINISH_REASONS else "other"


def _safe_provider_failure(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    category = value.get("category")
    stage = value.get("call_stage")
    if category not in _SAFE_PROVIDER_CATEGORIES or stage not in _SAFE_PROVIDER_STAGES:
        return None

    safe: dict[str, Any] = {"category": category, "call_stage": stage}
    provider_error_code = value.get("provider_error_code")
    if provider_error_code in _SAFE_PROVIDER_ERROR_CODES:
        safe["provider_error_code"] = provider_error_code
    exception_type = value.get("exception_type")
    if (
        isinstance(exception_type, str)
        and 1 <= len(exception_type) <= 64
        and re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*", exception_type)
    ):
        safe["exception_type"] = exception_type
    raw_chain = value.get("exception_chain")
    if isinstance(raw_chain, list):
        safe_chain = [
            item
            for item in raw_chain[:12]
            if isinstance(item, str)
            and 1 <= len(item) <= 64
            and re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*", item)
        ]
        if safe_chain:
            safe["exception_chain"] = safe_chain
    status = value.get("http_status")
    if type(status) is int and 100 <= status <= 599:
        safe["http_status"] = status
    for field in ("os_error_number", "os_error_windows_code"):
        os_code = value.get(field)
        if type(os_code) is int and 0 <= os_code <= 65535:
            safe[field] = os_code

    raw_detail = value.get("response_detail")
    if isinstance(raw_detail, dict):
        detail: dict[str, str] = {}
        code = raw_detail.get("code")
        if code in _SAFE_PROVIDER_RESPONSE_CODES:
            detail["code"] = code
        response_type = raw_detail.get("type")
        if response_type in _SAFE_PROVIDER_RESPONSE_TYPES:
            detail["type"] = response_type
        param = raw_detail.get("param")
        if param in _SAFE_PROVIDER_PARAMS:
            detail["param"] = param
        if detail:
            safe["response_detail"] = detail
    return safe


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

        trace_data: dict[str, Any] = {}
        if event_type == "model_call":
            for field in ("operation", "call_role"):
                value = _safe_trace_identifier(event.get(field))
                if value is not None:
                    trace_data[field] = value
            finish_reason = _safe_finish_reason(event.get("finish_reason"))
            if finish_reason is not None:
                trace_data["finish_reason"] = finish_reason
            provider_failure = _safe_provider_failure(event.get("provider_failure"))
            if provider_failure is not None:
                trace_data["provider_failure"] = provider_failure
            repair_reason = _safe_decision_reason(
                event.get("decision_repair_reason_code")
            )
            if repair_reason is not None:
                trace_data["decision_repair_reason_code"] = repair_reason
                trace_data["decision_repair_fields"] = _safe_decision_fields(
                    event.get("decision_repair_fields")
                )
        elif event_type == "run_failed":
            failure_reason = _safe_decision_reason(
                event.get("decision_failure_reason_code")
            )
            if failure_reason is not None:
                trace_data["decision_failure_reason_code"] = failure_reason
                trace_data["decision_failure_fields"] = _safe_decision_fields(
                    event.get("decision_failure_fields")
                )
        elif event_type == "route_decision":
            for field in ("agent", "route"):
                value = _safe_trace_identifier(event.get(field))
                if value is not None:
                    trace_data[field] = value
            for field in ("router_version", "router_status"):
                value = _safe_trace_identifier(event.get(field))
                if value is not None:
                    trace_data[field] = value
        elif event_type == "agent_result":
            agent = _safe_trace_identifier(event.get("agent"))
            result = event.get("result")
            name = _safe_trace_identifier(
                result.get("name") if isinstance(result, dict) else None
            )
            kind = result.get("kind") if isinstance(result, dict) else None
            if agent is not None:
                trace_data["agent"] = agent
            if name is not None:
                trace_data["name"] = name
            if kind in {"capability", "subagent"}:
                trace_data["kind"] = kind

        trace_event = TraceEvent(
            event_id=event_id or uuid4().hex,
            run_id=self.trace.run_id,
            sequence=sequence,
            event_type=trace_event_type,
            data=trace_data,
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

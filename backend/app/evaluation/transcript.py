"""Redacted per-case transcript artifacts for evaluation runs.

Transcripts preserve the synthetic evaluation conversation, Decisions,
Invocations, results, persisted events, Trace projection, terminal facts and
errors so a case can be reviewed after success or failure. They differ from the
Trace redaction policy on purpose:

- secret and chain-of-thought keys are dropped, and values are truncated;
- evaluation message/answer text is kept (bounded) for reproducibility;
- raw argument values and raw provider payloads are never exported;
- the Trace projection uses the stricter ``redact`` policy.
"""

from __future__ import annotations

import json
from pathlib import Path
import re
from typing import Any

from app.evaluation.errors import safe_error
from app.evaluation.types import EvalCase, ExecutionResult
from app.trace.redaction import redact

SCHEMA_VERSION = 1
_TERMINAL_TYPES = {
    "run_completed": "completed",
    "run_failed": "failed",
    "run_cancelled": "cancelled",
    "run_timeout": "timeout",
}
_SECRET_KEYS = frozenset(
    {
        "api_key",
        "apikey",
        "authorization",
        "token",
        "access_token",
        "refresh_token",
        "secret",
        "password",
        "passwd",
        "x_api_key",
        "x_api_token",
        "credential",
        "credentials",
    }
)
_COT_KEYS = frozenset(
    {
        "chain_of_thought",
        "reasoning_trace",
        "reasoning_content",
        "internal_thought",
    }
)
_MAX_STRING_LENGTH = 2000
_MAX_COLLECTION_ITEMS = 200
_REDACTED = "[REDACTED]"
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


def _normalized_key(key: object) -> str:
    return str(key).lower().replace("-", "_").replace(" ", "_")


def _safe(value: Any) -> Any:
    if isinstance(value, dict):
        result: dict[str, Any] = {}
        for key, child in list(value.items())[:_MAX_COLLECTION_ITEMS]:
            normalized = _normalized_key(key)
            if normalized in _SECRET_KEYS:
                result[str(key)] = _REDACTED
            elif normalized in _COT_KEYS:
                continue
            else:
                result[str(key)] = _safe(child)
        return result
    if isinstance(value, (list, tuple)):
        return [_safe(item) for item in list(value)[:_MAX_COLLECTION_ITEMS]]
    if isinstance(value, str) and len(value) > _MAX_STRING_LENGTH:
        return value[:_MAX_STRING_LENGTH] + "... (truncated)"
    return value


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


def _safe_event(event: dict[str, Any]) -> dict[str, Any]:
    safe = _safe(event)
    if event.get("type") == "model_call":
        provider_failure = _safe_provider_failure(event.get("provider_failure"))
        safe.pop("provider_failure", None)
        if provider_failure is not None:
            safe["provider_failure"] = provider_failure
    return safe


def _is_thinking_chunk(event: dict[str, Any]) -> bool:
    if any(event.get(field) == "thinking_chunk" for field in ("type", "event_type")):
        return True
    payload = event.get("payload")
    return isinstance(payload, dict) and payload.get("type") == "thinking_chunk"


def _events(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [_safe_event(event) for event in events if not _is_thinking_chunk(event)][
        :_MAX_COLLECTION_ITEMS
    ]


def _decisions(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "decision_id": event.get("decision_id"),
            "action": event.get("action"),
            "capability": event.get("capability"),
            "capability_version": event.get("capability_version"),
            "argument_keys": sorted(
                str(key) for key in event.get("argument_keys") or []
            ),
        }
        for event in events
        if event.get("type") == "model_decision"
    ]


def _invocations(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    records: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    for index, event in enumerate(events):
        event_type = event.get("type")
        if event_type not in {"tool_call_start", "tool_call_end"}:
            continue
        key = str(
            event.get("invocation_id")
            or event.get("id")
            or f"{event.get('capability') or 'unknown'}:{index}"
        )
        record = records.get(key)
        if record is None:
            record = {
                "invocation_id": key,
                "capability": event.get("capability") or event.get("name"),
                "capability_version": event.get("capability_version"),
                "argument_keys": [],
                "status": None,
                "error_code": None,
                "result": None,
                "observations": [],
            }
            records[key] = record
            order.append(key)
        if event_type == "tool_call_start":
            record["argument_keys"] = sorted(
                str(key) for key in event.get("argument_keys") or []
            )
            continue
        observation = {
            "status": event.get("status"),
            "error_code": event.get("error_code"),
            "result": _safe(event.get("output")),
        }
        record["observations"].append(observation)
        record["status"] = observation["status"]
        record["error_code"] = observation["error_code"]
        record["result"] = observation["result"]
    return [records[key] for key in order]


def _terminal(events: list[dict[str, Any]]) -> dict[str, Any]:
    terminal = {
        "type": None,
        "status": "missing",
        "error_code": None,
        "termination_reason": None,
    }
    terminal_event = None
    for event in reversed(events):
        terminal_type = event.get("type")
        if terminal_type in _TERMINAL_TYPES:
            terminal_event = event
            terminal = {
                "type": terminal_type,
                "status": _TERMINAL_TYPES[str(terminal_type)],
                "error_code": event.get("error_code"),
                "termination_reason": event.get("termination_reason"),
            }
            break
    if terminal_event is not None and terminal_event.get("type") == "run_failed":
        for field in (
            "decision_failure_reason_code",
            "decision_failure_fields",
        ):
            if field in terminal_event:
                terminal[field] = _safe(terminal_event[field])
    for event in reversed(events):
        if event.get("type") == "model_call" and "finish_reason" in event:
            terminal["finish_reason"] = _safe(event["finish_reason"])
            provider_failure = _safe_provider_failure(event.get("provider_failure"))
            if provider_failure is not None:
                terminal["provider_failure"] = provider_failure
            break
    return terminal


def build_transcript(
    *,
    case: EvalCase,
    run_id: str,
    trace_id: str | None,
    events: list[dict[str, Any]],
    persisted_events: list[dict[str, Any]],
    trace: dict[str, Any] | None,
    result: ExecutionResult | None,
    error: BaseException | None,
) -> dict[str, Any]:
    error_payload = None
    if error is not None:
        root = error.__cause__ or error
        error_payload = {
            "category": type(root).__name__,
            "safe": safe_error(root, "execution_failed"),
        }
    thinking_chunks_omitted = {
        "events": sum(_is_thinking_chunk(event) for event in events),
        "persisted_events": sum(
            _is_thinking_chunk(event) for event in persisted_events
        ),
    }
    return {
        "schema_version": SCHEMA_VERSION,
        "case_id": case.id,
        "run_id": run_id,
        "trace_id": trace_id,
        "case": {
            "category": case.category.value,
            "tags": list(case.tags),
            "input_messages": [
                message.model_dump(mode="json") for message in case.input_messages
            ],
            "memory_fixtures": [
                fixture.model_dump(mode="json") for fixture in case.memory_fixtures
            ],
            "deterministic": (
                case.deterministic.model_dump(mode="json")
                if case.deterministic is not None
                else None
            ),
            "answer_quality": (
                case.answer_quality.model_dump(mode="json")
                if case.answer_quality is not None
                else None
            ),
            "approval_actions": [approval.action for approval in case.approvals],
        },
        "decisions": _decisions(events),
        "invocations": _invocations(events),
        "result": result.model_dump(mode="json") if result is not None else None,
        "events": _events(events),
        "persisted_events": [
            {
                "sequence": event.get("sequence"),
                "event_type": event.get("event_type"),
                "invocation_id": event.get("invocation_id"),
                "payload": _safe_persisted_payload(event),
            }
            for event in persisted_events
            if not _is_thinking_chunk(event)
        ],
        "trace": redact(trace) if trace is not None else None,
        "terminal": _terminal(events),
        "error": error_payload,
        "redaction": {
            "policy": "transcript-v1",
            "secret_keys": "redacted",
            "chain_of_thought": "dropped",
            "thinking_chunk_events_omitted": thinking_chunks_omitted,
            "argument_values": "omitted (keys only)",
            "provider_payload": "not exported",
            "trace_projection": "trace-redaction policy",
        },
    }


def _safe_persisted_payload(event: dict[str, Any]) -> dict[str, Any]:
    payload = event.get("payload") or {}
    safe = _safe(payload)
    if event.get("event_type") == "model_call" and isinstance(safe, dict):
        provider_failure = _safe_provider_failure(
            payload.get("provider_failure") if isinstance(payload, dict) else None
        )
        safe.pop("provider_failure", None)
        if provider_failure is not None:
            safe["provider_failure"] = provider_failure
    return safe


def _file_name(case_id: str) -> str:
    return f"{re.sub(r'[^A-Za-z0-9._-]', '_', case_id)}.json"


def transcript_path(directory: str | Path, case_id: str) -> Path:
    """Stable per-case transcript path used by reports and review queues."""
    return Path(directory) / _file_name(case_id)


def trace_artifact_path(directory: str | Path, case_id: str) -> Path:
    """Stable path for the redacted Trace projection linked from a report."""
    return Path(directory) / "traces" / f"{Path(_file_name(case_id)).stem}.trace.json"


def write_transcript(
    directory: str | Path,
    case_id: str,
    payload: dict[str, Any],
) -> Path:
    root = Path(directory)
    root.mkdir(parents=True, exist_ok=True)
    target = transcript_path(root, case_id)
    temporary = target.with_suffix(target.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    temporary.replace(target)
    return target


def write_trace(
    directory: str | Path,
    case_id: str,
    payload: dict[str, Any],
) -> Path:
    """Persist the redacted Trace projection beside a case's transcript."""
    target = trace_artifact_path(directory, case_id)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(target.suffix + ".tmp")
    temporary.write_text(
        json.dumps(redact(payload), ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    temporary.replace(target)
    return target

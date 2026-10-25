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


def _events(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [_safe(event) for event in events[:_MAX_COLLECTION_ITEMS]]


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
    for event in reversed(events):
        terminal_type = event.get("type")
        if terminal_type in _TERMINAL_TYPES:
            return {
                "type": terminal_type,
                "status": _TERMINAL_TYPES[str(terminal_type)],
                "error_code": event.get("error_code"),
                "termination_reason": event.get("termination_reason"),
            }
    return {
        "type": None,
        "status": "missing",
        "error_code": None,
        "termination_reason": None,
    }


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
                "payload": _safe(event.get("payload") or {}),
            }
            for event in persisted_events
        ],
        "trace": redact(trace) if trace is not None else None,
        "terminal": _terminal(events),
        "error": error_payload,
        "redaction": {
            "policy": "transcript-v1",
            "secret_keys": "redacted",
            "chain_of_thought": "dropped",
            "argument_values": "omitted (keys only)",
            "provider_payload": "not exported",
            "trace_projection": "trace-redaction policy",
        },
    }


def _file_name(case_id: str) -> str:
    return f"{re.sub(r'[^A-Za-z0-9._-]', '_', case_id)}.json"


def transcript_path(directory: str | Path, case_id: str) -> Path:
    """Stable per-case transcript path used by reports and review queues."""
    return Path(directory) / _file_name(case_id)


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

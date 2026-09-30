"""Redaction policy for trace payloads — TRACE-002 Step 01.

Recursively removes configured secret keys and truncates large strings
and collections.  Must run before any TraceStore call.
"""

from __future__ import annotations

from typing import Any

from app.trace import AgentTrace

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

_PRIVATE_KEYS = frozenset(
    {
        "goal",
        "prompt",
        "messages",
        "memory",
        "raw_memory",
        "raw_prompt",
        "content",
    }
)

_MAX_STRING_LENGTH = 2000
_MAX_COLLECTION_ITEMS = 200


class UnsafeTraceDataError(ValueError):
    """Raised when prohibited reasoning data reaches the persistence boundary."""


def _normalized_key(key: object) -> str:
    return str(key).lower().replace("-", "_").replace(" ", "_")


def _contains_cot(value: Any) -> bool:
    if isinstance(value, dict):
        return any(
            _normalized_key(key) in _COT_KEYS or _contains_cot(child)
            for key, child in value.items()
        )
    if isinstance(value, (list, tuple)):
        return any(_contains_cot(item) for item in value)
    return False


def redact(value: Any, path: str = "") -> Any:
    """Recursively redact secrets and truncate oversized values."""
    if isinstance(value, dict):
        result: dict[str, Any] = {}
        for key, child in list(value.items())[:_MAX_COLLECTION_ITEMS]:
            child_path = f"{path}.{key}" if path else key
            key_lower = _normalized_key(key)
            if key_lower in _SECRET_KEYS:
                result[str(key)] = _REDACTED
            elif key_lower in _COT_KEYS:
                continue  # drop chain-of-thought entirely
            elif key_lower in _PRIVATE_KEYS:
                result[str(key)] = _REDACTED
            else:
                result[str(key)] = redact(child, child_path)
        return result

    if isinstance(value, (list, tuple)):
        truncated = list(value)[:_MAX_COLLECTION_ITEMS]
        return [redact(item, f"{path}[{i}]") for i, item in enumerate(truncated)]

    if isinstance(value, str) and len(value) > _MAX_STRING_LENGTH:
        return value[:_MAX_STRING_LENGTH] + "... (truncated)"

    return value


def sanitize_trace(trace: AgentTrace) -> AgentTrace:
    """Return a bounded, persistence-safe copy of a trace."""
    payload = trace.model_dump(mode="json")
    if _contains_cot(payload):
        raise UnsafeTraceDataError(
            "chain-of-thought fields are prohibited in persisted traces"
        )
    return AgentTrace.model_validate(redact(payload))


_REDACTED = "[REDACTED]"

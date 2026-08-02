"""The single safe-result boundary for capability and tool execution."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
import hashlib
import json
import math
from typing import Any

from app.capabilities.types import ActionDescriptor, CapabilityResult


DEFAULT_MAX_OUTPUT_FIELDS = 128
DEFAULT_MAX_OUTPUT_DEPTH = 8
DEFAULT_MAX_OUTPUT_STRING_BYTES = 4096
DEFAULT_MAX_INPUT_DEPTH = 8
DEFAULT_MAX_INPUT_FIELDS = 128
DEFAULT_MAX_INPUT_STRING_BYTES = 4096

_SENSITIVE_KEY_PARTS = frozenset(
    {
        "api_key",
        "apikey",
        "authorization",
        "cookie",
        "password",
        "secret",
        "token",
        "prompt",
        "chain_of_thought",
        "raw_provider",
        "raw_response",
        "raw",
        "provider_payload",
        "exception",
        "stack_trace",
        "reasoning",
        "chain_of_thought",
        "co_t",
        "thoughts",
    }
)


class SchemaContractError(ValueError):
    """Input or output did not satisfy its declared public schema."""


class OutputBoundsError(ValueError):
    """An output exceeded a public result bound."""

    def __init__(self, reason: str, *, payload_bytes: int | None = None) -> None:
        self.reason = reason
        self.payload_bytes = payload_bytes
        super().__init__(reason)


def _json_type_matches(value: Any, expected: str) -> bool:
    return {
        "object": isinstance(value, dict),
        "array": isinstance(value, list),
        "string": isinstance(value, str),
        "integer": isinstance(value, int) and not isinstance(value, bool),
        "number": isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(value),
        "boolean": isinstance(value, bool),
        "null": value is None,
    }.get(expected, False)


def _schema_error(value: Any, schema: dict[str, Any], path: str) -> str | None:
    if "const" in schema and value != schema["const"]:
        return f"{path} does not match const"
    expected = schema.get("type")
    if isinstance(expected, list):
        if not any(_json_type_matches(value, item) for item in expected):
            return f"{path} has an invalid type"
    elif isinstance(expected, str) and not _json_type_matches(value, expected):
        return f"{path} must be of type {expected}"
    if "enum" in schema and value not in schema["enum"]:
        return f"{path} must match enum"

    if isinstance(value, str):
        if isinstance(schema.get("minLength"), int) and len(value) < schema["minLength"]:
            return f"{path} is shorter than allowed"
        if isinstance(schema.get("maxLength"), int) and len(value) > schema["maxLength"]:
            return f"{path} is longer than allowed"
    if isinstance(value, dict):
        properties = schema.get("properties", {})
        if not isinstance(properties, dict):
            return f"{path} has an invalid properties schema"
        for required in schema.get("required", []) or []:
            if required not in value:
                return f"{path}.{required} is required"
        for key, child in value.items():
            child_schema = properties.get(key)
            if child_schema is None:
                if schema.get("additionalProperties") is False:
                    return f"{path}.{key} is not allowed"
                if isinstance(schema.get("additionalProperties"), dict):
                    child_schema = schema["additionalProperties"]
            if isinstance(child_schema, dict):
                error = _schema_error(child, child_schema, f"{path}.{key}")
                if error:
                    return error
    if isinstance(value, list) and isinstance(schema.get("items"), dict):
        for index, child in enumerate(value):
            error = _schema_error(child, schema["items"], f"{path}[{index}]")
            if error:
                return error
    for keyword in ("allOf", "anyOf", "oneOf"):
        alternatives = schema.get(keyword)
        if not isinstance(alternatives, list):
            continue
        matches = [
            _schema_error(value, child, path) is None
            for child in alternatives
            if isinstance(child, dict)
        ]
        if keyword == "allOf" and not all(matches):
            return f"{path} does not match allOf"
        if keyword == "anyOf" and not any(matches):
            return f"{path} does not match anyOf"
        if keyword == "oneOf" and sum(matches) != 1:
            return f"{path} does not match oneOf"
    return None


def validate_input(arguments: dict[str, Any], descriptor: ActionDescriptor) -> None:
    _validate_bounds(
        arguments,
        max_payload_bytes=descriptor.max_payload_bytes,
        max_depth=DEFAULT_MAX_INPUT_DEPTH,
        max_fields=DEFAULT_MAX_INPUT_FIELDS,
        max_string_bytes=DEFAULT_MAX_INPUT_STRING_BYTES,
        label="input",
    )
    error = _schema_error(arguments, descriptor.input_schema, "arguments")
    if error:
        raise SchemaContractError(error)


def _validate_bounds(
    value: Any,
    *,
    max_payload_bytes: int,
    max_depth: int,
    max_fields: int,
    max_string_bytes: int,
    label: str,
) -> None:
    fields = 0

    def visit(item: Any, depth: int) -> None:
        nonlocal fields
        if depth > max_depth:
            raise OutputBoundsError(f"{label} nesting exceeds the configured limit")
        if isinstance(item, dict):
            fields += len(item)
            if fields > max_fields:
                raise OutputBoundsError(f"{label} field count exceeds the configured limit")
            for key, child in item.items():
                if not isinstance(key, str):
                    raise OutputBoundsError(f"{label} contains a non-string field")
                visit(child, depth + 1)
        elif isinstance(item, list):
            fields += len(item)
            if fields > max_fields:
                raise OutputBoundsError(f"{label} item count exceeds the configured limit")
            for child in item:
                visit(child, depth + 1)
        elif isinstance(item, str) and len(item.encode("utf-8")) > max_string_bytes:
            raise OutputBoundsError(f"{label} string exceeds the configured limit")

    visit(value, 0)
    try:
        payload_bytes = len(json.dumps(value, ensure_ascii=False, allow_nan=False).encode("utf-8"))
    except (TypeError, ValueError) as exc:
        raise SchemaContractError(f"{label} is not JSON serializable") from exc
    if payload_bytes > max_payload_bytes:
        raise OutputBoundsError(f"{label} payload exceeds the configured limit", payload_bytes=payload_bytes)


def _safe_value(value: Any, *, max_depth: int, max_string_bytes: int) -> Any:
    if isinstance(value, dict):
        safe: dict[str, Any] = {}
        for key, child in value.items():
            key_text = str(key)
            lowered = key_text.lower()
            if any(part in lowered for part in _SENSITIVE_KEY_PARTS):
                safe[key_text] = "[REDACTED]"
            else:
                safe[key_text] = _safe_value(child, max_depth=max_depth - 1, max_string_bytes=max_string_bytes)
        return safe
    if isinstance(value, list):
        return [
            _safe_value(child, max_depth=max_depth - 1, max_string_bytes=max_string_bytes)
            for child in value
        ]
    if isinstance(value, str):
        encoded = value.encode("utf-8")
        if len(encoded) > max_string_bytes:
            return encoded[:max_string_bytes].decode("utf-8", errors="ignore") + "...[TRUNCATED]"
        return value
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(type(value).__name__)


@dataclass(frozen=True)
class NormalizedResult:
    status: str
    error_code: str | None
    retryable: bool
    safe_output: dict[str, Any]
    artifacts: list[dict[str, Any]] = field(default_factory=list)
    usage: dict[str, Any] = field(default_factory=dict)
    latency_ms: int = 0
    provenance: dict[str, Any] = field(default_factory=dict)
    run_id: str = ""
    decision_id: str = ""
    invocation_id: str = ""
    trace_id: str = ""
    sequence: int | None = None
    capability: str = ""
    capability_version: str = ""

    def canonical_projection(self) -> dict[str, Any]:
        return {
            "schema_version": "v1",
            "run_id": self.run_id,
            "decision_id": self.decision_id,
            "invocation_id": self.invocation_id,
            "trace_id": self.trace_id,
            "sequence": self.sequence,
            "capability": self.capability,
            "capability_version": self.capability_version,
            "status": self.status,
            "error_code": self.error_code,
            "retryable": self.retryable,
            "safe_output": deepcopy(self.safe_output),
            "artifacts": deepcopy(self.artifacts),
            "usage": deepcopy(self.usage),
            "latency_ms": self.latency_ms,
            "provenance": deepcopy(self.provenance),
        }

    def model_projection(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "decision_id": self.decision_id,
            "invocation_id": self.invocation_id,
            "trace_id": self.trace_id,
            "status": self.status,
            "error_code": self.error_code,
            "safe_output": deepcopy(self.safe_output),
            "provenance": deepcopy(self.provenance),
        }

    def ui_projection(self) -> dict[str, Any]:
        output = deepcopy(self.safe_output)
        output.setdefault("success", self.status == "succeeded")
        if self.error_code is not None:
            output.setdefault("error_type", self.error_code)
        output["run_id"] = self.run_id
        output["decision_id"] = self.decision_id
        output["invocation_id"] = self.invocation_id
        output["trace_id"] = self.trace_id
        return output


class ResultNormalizer:
    """Normalize raw capability results before any model, event, or UI use."""

    def normalize(
        self,
        raw: Any,
        *,
        descriptor: ActionDescriptor,
        run_id: str,
        decision_id: str,
        invocation_id: str,
        trace_id: str,
        sequence: int | None = None,
        latency_ms: int = 0,
    ) -> NormalizedResult:
        if isinstance(raw, CapabilityResult):
            raw = raw.to_dict()
        if not isinstance(raw, dict):
            raw = {"success": True, "value": raw}
        success = bool(raw.get("success", True))
        error_code = str(raw.get("error_type")) if raw.get("error_type") else None
        retryable = bool(raw.get("retryable", False))
        data = raw.get("data") if isinstance(raw.get("data"), dict) else {
            key: value
            for key, value in raw.items()
            if key not in {"success", "error", "error_type", "retryable", "latency_ms"}
        }
        try:
            _validate_bounds(
                data,
                max_payload_bytes=descriptor.max_payload_bytes,
                max_depth=DEFAULT_MAX_OUTPUT_DEPTH,
                max_fields=DEFAULT_MAX_OUTPUT_FIELDS,
                max_string_bytes=DEFAULT_MAX_OUTPUT_STRING_BYTES,
                label="output",
            )
            schema_error = _schema_error(data, descriptor.output_schema, "output")
            if schema_error:
                raise SchemaContractError(schema_error)
        except SchemaContractError:
            return self._failure(
                "invalid_output",
                "Capability output did not match its declared contract",
                raw,
                run_id=run_id,
                decision_id=decision_id,
                invocation_id=invocation_id,
                trace_id=trace_id,
                sequence=sequence,
                capability=descriptor.name,
                capability_version=descriptor.version,
                latency_ms=latency_ms,
            )
        except OutputBoundsError as exc:
            digest = hashlib.sha256(repr(raw).encode("utf-8", errors="replace")).hexdigest()
            return NormalizedResult(
                status="failed",
                error_code="payload_too_large",
                retryable=False,
                safe_output={"error_type": "payload_too_large", "message": "Capability output was bounded"},
                artifacts=[{"artifact_id": digest, "kind": "bounded_output", "size_bytes": exc.payload_bytes}],
                latency_ms=latency_ms,
                provenance=self._provenance("capability", bounded=True),
                run_id=run_id,
                decision_id=decision_id,
                invocation_id=invocation_id,
                trace_id=trace_id,
                sequence=sequence,
                capability=descriptor.name,
                capability_version=descriptor.version,
            )

        safe_data = _safe_value(data, max_depth=DEFAULT_MAX_OUTPUT_DEPTH, max_string_bytes=DEFAULT_MAX_OUTPUT_STRING_BYTES)
        if not isinstance(safe_data, dict):
            safe_data = {"value": safe_data}
        if not success:
            safe_data = {
                "error_type": error_code or "tool_error",
                "message": "Capability execution failed",
            }
        return NormalizedResult(
            status="succeeded" if success else "failed",
            error_code=error_code,
            retryable=retryable,
            safe_output=safe_data,
            latency_ms=latency_ms,
            provenance=self._provenance("capability"),
            run_id=run_id,
            decision_id=decision_id,
            invocation_id=invocation_id,
            trace_id=trace_id,
            sequence=sequence,
            capability=descriptor.name,
            capability_version=descriptor.version,
        )

    @staticmethod
    def _provenance(source: str, *, bounded: bool = False) -> dict[str, Any]:
        return {"source": source, "trust": "untrusted", "bounded": bounded, "redacted": True}

    def _failure(self, error_code: str, message: str, raw: Any, **metadata: Any) -> NormalizedResult:
        return NormalizedResult(
            status="failed",
            error_code=error_code,
            retryable=False,
            safe_output={"error_type": error_code, "message": message},
            provenance=self._provenance("capability"),
            **metadata,
        )

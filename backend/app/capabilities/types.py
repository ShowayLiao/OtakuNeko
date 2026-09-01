"""Capability action descriptors and typed result contracts.

All capabilities return ``CapabilityResult`` (success or error) from
``execute()`` so callers — agents, MCP, tools — can inspect outcomes
without parsing ad-hoc dicts.
"""

from __future__ import annotations

import json
from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any


CONTRACT_VERSION = "v1"
DEFAULT_MAX_PAYLOAD_BYTES = 1024 * 1024


def _default_output_schema() -> dict[str, Any]:
    return {"type": "object", "additionalProperties": True}


def _schema_type_matches(value: Any, expected: str) -> bool:
    return {
        "object": isinstance(value, dict),
        "array": isinstance(value, list),
        "string": isinstance(value, str),
        "integer": isinstance(value, int) and not isinstance(value, bool),
        "number": isinstance(value, (int, float)) and not isinstance(value, bool),
        "boolean": isinstance(value, bool),
        "null": value is None,
    }.get(expected, True)


def _matches_output_schema(value: Any, schema: dict[str, Any]) -> bool:
    expected_type = schema.get("type")
    if isinstance(expected_type, str) and not _schema_type_matches(value, expected_type):
        return False
    if isinstance(value, dict):
        properties = schema.get("properties", {})
        required = schema.get("required", [])
        if any(key not in value for key in required):
            return False
        if schema.get("additionalProperties") is False:
            allowed = set(properties)
            if any(key not in allowed for key in value):
                return False
        return all(
            key not in properties or _matches_output_schema(value[key], properties[key])
            for key in value
        )
    if isinstance(value, list) and isinstance(schema.get("items"), dict):
        return all(_matches_output_schema(item, schema["items"]) for item in value)
    return True


@dataclass(frozen=True)
class ActionDescriptor:
    """Immutable action descriptor for capability introspection.

    Agents and the MCP server use these descriptors to discover what a
    capability can do, without hard-coding action lists.
    """

    name: str
    description: str
    input_schema: dict[str, Any]
    public_name: str | None = None
    requires_auth: bool = False
    is_side_effect: bool = False
    version: str = CONTRACT_VERSION
    output_schema: dict[str, Any] = field(default_factory=_default_output_schema)
    risk_level: str = "low"
    timeout_seconds: float = 30.0
    retry_class: str = "none"
    idempotency_mode: str = "none"
    approval_required: bool = False
    max_payload_bytes: int = DEFAULT_MAX_PAYLOAD_BYTES
    max_output_fields: int | None = None

    def __post_init__(self) -> None:
        if self.is_side_effect and not self.approval_required:
            object.__setattr__(self, "approval_required", True)
        if self.max_output_fields is not None and self.max_output_fields < 1:
            raise ValueError("max_output_fields must be positive when configured")

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "public_name": self.public_name,
            "description": self.description,
            "input_schema": self.input_schema,
            "requires_auth": self.requires_auth,
            "is_side_effect": self.is_side_effect,
            "version": self.version,
            "output_schema": self.output_schema,
            "risk_level": self.risk_level,
            "timeout_seconds": self.timeout_seconds,
            "retry_class": self.retry_class,
            "idempotency_mode": self.idempotency_mode,
            "approval_required": self.approval_required,
            "max_payload_bytes": self.max_payload_bytes,
            "max_output_fields": self.max_output_fields,
        }

    def model_json_schema(self) -> dict[str, Any]:
        """Return the JSON schema for this action's parameters."""
        return self.input_schema


@dataclass(frozen=True)
class PublicActionDefinition:
    """Dependency-free, versioned definition exposed to adapters."""

    capability_name: str
    name: str
    public_name: str
    version: str
    description: str
    input_schema: dict[str, Any]
    output_schema: dict[str, Any]
    risk_level: str
    timeout_seconds: float
    retry_class: str
    idempotency_mode: str
    approval_required: bool
    requires_auth: bool
    is_side_effect: bool
    max_payload_bytes: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "capability_name": self.capability_name,
            "name": self.name,
            "public_name": self.public_name,
            "version": self.version,
            "description": self.description,
            "input_schema": deepcopy(self.input_schema),
            "output_schema": deepcopy(self.output_schema),
            "risk_level": self.risk_level,
            "timeout_seconds": self.timeout_seconds,
            "retry_class": self.retry_class,
            "idempotency_mode": self.idempotency_mode,
            "approval_required": self.approval_required,
            "requires_auth": self.requires_auth,
            "is_side_effect": self.is_side_effect,
            "max_payload_bytes": self.max_payload_bytes,
        }


@dataclass
class CapabilityResult:
    """Typed result contract shared by every capability execution."""

    success: bool
    data: dict[str, Any] = field(default_factory=dict)
    error: str | None = None
    error_type: str | None = None

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {"success": self.success, **self.data}
        if self.error is not None:
            result["error"] = self.error
        if self.error_type is not None:
            result["error_type"] = self.error_type
        return result

    def to_safe_dict(
        self,
        *,
        output_schema: dict[str, Any] | None = None,
        max_payload_bytes: int = DEFAULT_MAX_PAYLOAD_BYTES,
    ) -> dict[str, Any]:
        """Return a bounded, structured envelope safe for adapter boundaries."""
        if output_schema is not None and not _matches_output_schema(self.data, output_schema):
            return {
                "success": False,
                "data": {},
                "error": "Capability output did not match its declared schema",
                "error_type": "invalid_output",
            }

        envelope: dict[str, Any] = {"success": self.success, "data": self.data}
        if self.error is not None:
            envelope["error"] = self.error
        if self.error_type is not None:
            envelope["error_type"] = self.error_type
        try:
            payload_size = len(json.dumps(envelope, ensure_ascii=False).encode("utf-8"))
        except (TypeError, ValueError):
            return {
                "success": False,
                "data": {},
                "error": "Capability output was not JSON serializable",
                "error_type": "invalid_output",
            }
        if payload_size > max_payload_bytes:
            return {
                "success": False,
                "data": {},
                "error": "Capability output exceeded the public payload limit",
                "error_type": "payload_too_large",
            }
        return envelope

    @classmethod
    def ok(cls, **data: Any) -> CapabilityResult:
        """Create a success result with optional payload."""
        return cls(success=True, data=data)

    @classmethod
    def fail(cls, error: str, error_type: str | None = None, **data: Any) -> CapabilityResult:
        """Create a typed error result."""
        return cls(success=False, error=error, error_type=error_type, data=data)

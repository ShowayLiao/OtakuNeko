"""Capability action descriptors and typed result contracts.

All capabilities return ``CapabilityResult`` (success or error) from
``execute()`` so callers — agents, MCP, tools — can inspect outcomes
without parsing ad-hoc dicts.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ActionDescriptor:
    """Immutable action descriptor for capability introspection.

    Agents and the MCP server use these descriptors to discover what a
    capability can do, without hard-coding action lists.
    """

    name: str
    description: str
    input_schema: dict[str, Any]
    requires_auth: bool = False
    is_side_effect: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.input_schema,
            "requires_auth": self.requires_auth,
            "is_side_effect": self.is_side_effect,
        }

    def model_json_schema(self) -> dict[str, Any]:
        """Return the JSON schema for this action's parameters."""
        return self.input_schema


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

    @classmethod
    def ok(cls, **data: Any) -> CapabilityResult:
        """Create a success result with optional payload."""
        return cls(success=True, data=data)

    @classmethod
    def fail(cls, error: str, error_type: str | None = None, **data: Any) -> CapabilityResult:
        """Create a typed error result."""
        return cls(success=False, error=error, error_type=error_type, data=data)

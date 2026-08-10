"""LangChain adapter for capability actions — CAPABILITY-003 Step 02.

Creates LangChain-compatible tools from capability action descriptors
and delegates execution to ``BaseCapability.execute``.
"""

from __future__ import annotations

from typing import Any

from langchain_core.tools import BaseTool, tool

from app.capabilities.base import BaseCapability
from app.capabilities.factory import (
    build_capability_registry as _build_capability_registry,
)
from app.capabilities.registry import CapabilityRegistry
from app.capabilities.types import ActionDescriptor, CapabilityResult
from app.core.logging import get_logger
from app.harness.contracts import ExecutionContext
from app.harness.capability_adapter import CapabilityAdapter

logger = get_logger(__name__)

_DEFAULT_ACTIVE_CAPABILITIES = frozenset({"anime", "system", "recommendation"})
_MODEL_OWNED_FIELDS = frozenset({"user_id", "principal_id", "db", "token"})


def build_capability_registry() -> CapabilityRegistry:
    """Compatibility import; new callers should use ``capabilities.factory``."""
    return _build_capability_registry()


def _build_runtime_tool(
    capability: BaseCapability,
    descriptor: ActionDescriptor,
    *,
    input_schema: dict[str, Any] | None = None,
    context: ExecutionContext | None = None,
    capability_adapter: CapabilityAdapter | None = None,
) -> BaseTool:
    """Create a LangChain BaseTool from a capability action descriptor.

    The tool validates public inputs and delegates authenticated execution to
    ``CapabilityAdapter`` when a runtime context is present.
    """

    if descriptor.public_name is None:
        raise ValueError(
            f"Action '{capability.name}.{descriptor.name}' has no public name"
        )

    @tool(descriptor.public_name)
    async def _inner(**kwargs: Any) -> dict[str, Any]:
        """Auto-generated tool — see descriptor.description."""
        public_kwargs = dict(kwargs)
        public_kwargs.pop("user_id", None)
        public_kwargs.pop("principal_id", None)
        if context is not None:
            adapter = capability_adapter or CapabilityAdapter(capability)
            result = await adapter.execute(context, descriptor.name, public_kwargs)
        else:
            result = await capability.execute(descriptor.name, **public_kwargs)
        if isinstance(result, CapabilityResult):
            return result.to_safe_dict(
                output_schema=descriptor.output_schema,
                max_payload_bytes=descriptor.max_payload_bytes,
            )
        return result

    _inner.name = descriptor.public_name
    _inner.description = descriptor.description

    # Build Pydantic args schema from input_schema
    public_input_schema = _public_schema(
        input_schema if input_schema is not None else descriptor.input_schema
    )
    if public_input_schema:
        try:
            from pydantic import create_model, Field
            props = public_input_schema.get("properties", {})
            required = set(public_input_schema.get("required", []) or [])
            fields: dict[str, Any] = {}
            for field_name, field_schema in props.items():
                field_type = _json_type_to_python(field_schema.get("type", "string"))
                default = ... if field_name in required else None
                fields[field_name] = (field_type, Field(default=default, description=field_schema.get("description", "")))
            if fields:
                schema = create_model(f"{descriptor.name}_args", **fields)
                _inner.args_schema = schema
        except Exception:
            logger.warning("schema_build_failed", extra={"action": descriptor.name})
            pass

    return _inner


def _public_schema(schema: dict[str, Any]) -> dict[str, Any]:
    """Copy a schema while excluding model-owned authority fields."""
    copied = dict(schema)
    properties = copied.get("properties")
    if isinstance(properties, dict):
        copied["properties"] = {
            name: _public_schema(value) if isinstance(value, dict) else value
            for name, value in properties.items()
            if name not in _MODEL_OWNED_FIELDS
        }
    required = copied.get("required")
    if isinstance(required, list):
        copied["required"] = [name for name in required if name not in _MODEL_OWNED_FIELDS]
    for key in ("items", "additionalProperties"):
        value = copied.get(key)
        if isinstance(value, dict):
            copied[key] = _public_schema(value)
    return copied


def _json_type_to_python(json_type: Any) -> type:
    if isinstance(json_type, list):
        json_type = next((item for item in json_type if item != "null"), "string")
    mapping = {
        "string": str,
        "integer": int,
        "number": float,
        "boolean": bool,
        "array": list,
        "object": dict,
    }
    return mapping.get(json_type, str)


def derive_tools(
    registry: CapabilityRegistry,
    *,
    allowlist: set[str] | None = None,
    context: ExecutionContext | None = None,
    capability_adapter: CapabilityAdapter | None = None,
) -> list[BaseTool]:
    """Derive read-only LangChain tools from versioned public definitions."""
    tools: list[BaseTool] = []
    definitions = registry.allowed_public_definitions(allowlist)
    if allowlist is None:
        definitions = [
            definition
            for definition in definitions
            if definition.capability_name in _DEFAULT_ACTIVE_CAPABILITIES
        ]
    for definition in definitions:
        owner = registry.find_action(definition.public_name)
        if owner is None:
            continue
        capability, descriptor = owner
        tools.append(
            _build_runtime_tool(
                capability,
                descriptor,
                input_schema=definition.input_schema,
                context=context,
                capability_adapter=capability_adapter,
            )
        )
    return tools

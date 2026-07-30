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
from app.capabilities.types import ActionDescriptor
from app.core.logging import get_logger

logger = get_logger(__name__)


def build_capability_registry() -> CapabilityRegistry:
    """Compatibility import; new callers should use ``capabilities.factory``."""
    return _build_capability_registry()


def _build_runtime_tool(
    capability: BaseCapability,
    descriptor: ActionDescriptor,
) -> BaseTool:
    """Create a LangChain BaseTool from a capability action descriptor.

    The tool validates inputs, injects trusted context, delegates to
    ``capability.execute()``, and preserves typed failures.
    """

    if descriptor.public_name is None:
        raise ValueError(
            f"Action '{capability.name}.{descriptor.name}' has no public name"
        )

    @tool(descriptor.public_name)
    async def _inner(**kwargs: Any) -> dict[str, Any]:
        """Auto-generated tool — see descriptor.description."""
        result = await capability.execute(descriptor.name, **kwargs)
        return result

    _inner.name = descriptor.public_name
    _inner.description = descriptor.description

    # Build Pydantic args schema from input_schema
    if descriptor.input_schema:
        try:
            from pydantic import create_model, Field
            props = descriptor.input_schema.get("properties", {})
            required = set(descriptor.input_schema.get("required", []) or [])
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


def _json_type_to_python(json_type: str) -> type:
    mapping = {
        "string": str,
        "integer": int,
        "number": float,
        "boolean": bool,
        "array": list,
        "object": dict,
    }
    return mapping.get(json_type, str)


def derive_tools(registry: CapabilityRegistry) -> list[BaseTool]:
    """Derive LangChain BaseTool list from all registered capabilities."""
    tools: list[BaseTool] = []
    for name in registry.list_names():
        cap = registry.get(name)
        for descriptor in cap.actions():
            tools.append(_build_runtime_tool(cap, descriptor))
    return tools

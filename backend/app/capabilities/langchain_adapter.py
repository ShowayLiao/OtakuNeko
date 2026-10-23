"""LangChain adapter for capability actions.

New callers receive a Dispatcher-backed tool: schema validation, policy,
identity injection, and result normalization stay on the canonical Harness
boundary. The legacy ``capability_adapter`` argument is used only for
synthetic/legacy descriptors that require runtime-owned input fields, which the
Dispatcher intentionally rejects from model arguments.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Callable
from uuid import uuid4

from langchain_core.tools import BaseTool, tool

from app.capabilities.base import BaseCapability
from app.capabilities.factory import (
    build_capability_registry as _build_capability_registry,
)
from app.capabilities.registry import CapabilityRegistry
from app.capabilities.types import ActionDescriptor, CapabilityResult
from app.core.logging import get_logger
from app.harness.authority import (
    RUNTIME_OWNED_FIELDS,
    contains_runtime_owned_field,
    strip_runtime_owned_fields,
)
from app.harness.capability_adapter import CapabilityAdapter
from app.harness.contracts import AgentDecision, ErrorCode, ExecutionContext
from app.harness.dispatcher import Dispatcher

logger = get_logger(__name__)

_DEFAULT_ACTIVE_CAPABILITIES = frozenset({"anime", "system", "recommendation"})


def build_capability_registry() -> CapabilityRegistry:
    """Compatibility import; new callers should use ``capabilities.factory``."""
    return _build_capability_registry()


def _single_capability_dispatcher(
    capability: BaseCapability,
    *,
    adapter_factory: Callable[[Any], Any] | None = None,
) -> Dispatcher:
    registry = CapabilityRegistry()
    registry.register(capability)
    return Dispatcher(registry, adapter_factory=adapter_factory)


def _error_value(error_code: Any) -> str:
    return error_code.value if isinstance(error_code, ErrorCode) else str(error_code)


def _dispatcher_result(invocation: Any) -> dict[str, Any]:
    succeeded = invocation.status == "succeeded"
    result: dict[str, Any] = {
        "success": succeeded,
        "data": invocation.model_output.get("safe_output", {}),
    }
    if invocation.error_code is not None:
        result["error_type"] = _error_value(invocation.error_code)
        result["error"] = "Tool execution failed"
    return result


def _drop_unset_none_values(
    arguments: dict[str, Any], schema: dict[str, Any]
) -> dict[str, Any]:
    """Drop Pydantic's ``None`` defaults for optional non-nullable fields."""
    properties = schema.get("properties", {})
    cleaned: dict[str, Any] = {}
    for key, value in arguments.items():
        if value is None:
            property_schema = properties.get(key)
            if isinstance(property_schema, dict):
                expected = property_schema.get("type")
                if isinstance(expected, str) and expected != "null":
                    continue
                if isinstance(expected, list) and "null" not in expected:
                    continue
                alternatives = property_schema.get("anyOf") or property_schema.get(
                    "oneOf"
                )
                if isinstance(alternatives, list):
                    types: list[str] = []
                    for alternative in alternatives:
                        if not isinstance(alternative, dict):
                            continue
                        alt_type = alternative.get("type")
                        if isinstance(alt_type, str):
                            types.append(alt_type)
                        elif isinstance(alt_type, list):
                            types.extend(
                                item for item in alt_type if isinstance(item, str)
                            )
                    if types and "null" not in types:
                        continue
        cleaned[key] = value
    return cleaned


def _build_runtime_tool(
    capability: BaseCapability,
    descriptor: ActionDescriptor,
    *,
    input_schema: dict[str, Any] | None = None,
    context: ExecutionContext | None = None,
    capability_adapter: CapabilityAdapter | None = None,
    dispatcher: Dispatcher | None = None,
) -> BaseTool:
    """Create a LangChain tool from a capability action descriptor.

    Execution always goes through ``Dispatcher`` except for legacy/synthetic
    descriptors whose required input includes runtime-owned fields; those fall
    back to the controlled ``CapabilityAdapter`` because the public arguments
    intentionally omit authority fields. Side effects still fail closed without
    a dispatcher.
    """

    if descriptor.public_name is None:
        raise ValueError(
            f"Action '{capability.name}.{descriptor.name}' has no public name"
        )
    public_name = descriptor.public_name

    @tool(public_name)
    async def _inner(**kwargs: Any) -> dict[str, Any]:
        """Auto-generated tool — see descriptor.description."""
        public_kwargs = {
            key: value
            for key, value in kwargs.items()
            if key not in RUNTIME_OWNED_FIELDS
        }
        if contains_runtime_owned_field(public_kwargs):
            return {
                "success": False,
                "error": "Runtime-owned fields are not accepted",
                "error_type": "identity_spoofing",
            }
        public_kwargs = _drop_unset_none_values(public_kwargs, descriptor.input_schema)

        if descriptor.is_side_effect and dispatcher is None:
            return {
                "success": False,
                "error": "A Dispatcher is required for side effects",
                "error_type": "dispatcher_required",
            }

        if descriptor.requires_auth and (
            context is None or context.principal_id is None
        ):
            return {
                "success": False,
                "error": "Authentication context is required",
                "error_type": "unauthorized",
            }

        required_runtime_fields = (
            set(descriptor.input_schema.get("required", ())) & RUNTIME_OWNED_FIELDS
        )
        if required_runtime_fields:
            # Legacy/synthetic descriptors that require authority fields cannot
            # pass Dispatcher input validation (public arguments omit those
            # fields). Fall back to the controlled adapter for compatibility;
            # real production actions do not require runtime-owned inputs.
            adapter = capability_adapter or CapabilityAdapter(capability)
            result = await adapter.execute(context, descriptor.name, public_kwargs)
            if isinstance(result, CapabilityResult):
                return result.to_safe_dict(
                    output_schema=descriptor.output_schema,
                    max_payload_bytes=descriptor.max_payload_bytes,
                )
            return result

        target = dispatcher or _single_capability_dispatcher(
            capability,
            adapter_factory=(
                (lambda _target: capability_adapter)
                if capability_adapter is not None
                else None
            ),
        )
        current = context
        if current is None:
            run_id = f"tool:{uuid4().hex}"
            current = ExecutionContext(
                principal_id=None,
                run_id=run_id,
                trace_id=run_id,
                capability_allowlist=frozenset(
                    {
                        capability.name,
                        descriptor.name,
                        public_name,
                    }
                ),
            )
        try:
            decision = AgentDecision(
                decision_id=uuid4().hex,
                run_id=current.run_id,
                action="invoke",
                capability=public_name,
                capability_version=descriptor.version,
                arguments=public_kwargs,
            )
        except ValueError:
            return {
                "success": False,
                "error": "Runtime-owned fields are not accepted",
                "error_type": "identity_spoofing",
            }
        invocation = await target.dispatch(decision, current)
        return _dispatcher_result(invocation)

    _inner.name = public_name
    _inner.description = descriptor.description

    # Build Pydantic args schema from the public input schema.
    public_input_schema = _public_schema(
        input_schema if input_schema is not None else descriptor.input_schema
    )
    if public_input_schema:
        try:
            from pydantic import Field, create_model

            props = public_input_schema.get("properties", {})
            required = set(public_input_schema.get("required", []) or [])
            fields: dict[str, Any] = {}
            for field_name, field_schema in props.items():
                field_type = _json_type_to_python(field_schema.get("type", "string"))
                default = ... if field_name in required else None
                fields[field_name] = (
                    field_type,
                    Field(
                        default=default,
                        description=field_schema.get("description", ""),
                    ),
                )
            if fields:
                schema = create_model(f"{descriptor.name}_args", **fields)
                _inner.args_schema = schema
        except Exception:
            logger.warning("schema_build_failed", extra={"action": descriptor.name})
            pass

    return _inner


def _public_schema(schema: dict[str, Any]) -> dict[str, Any]:
    """Copy a schema while removing every runtime-owned authority field."""
    copied = strip_runtime_owned_fields(deepcopy(schema))
    if not isinstance(copied, dict):
        return {"type": "object", "additionalProperties": True}
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
    dispatcher: Dispatcher | None = None,
) -> list[BaseTool]:
    """Derive read-only LangChain tools backed by the Dispatcher by default."""
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
                dispatcher=dispatcher,
            )
        )
    return tools

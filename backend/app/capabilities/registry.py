"""Capability registry for discovery and lookup.

Does NOT perform routing or dispatching — that belongs to the agent layer.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Dict, List

from app.capabilities.base import BaseCapability
from app.capabilities.types import (
    CONTRACT_VERSION,
    ActionDescriptor,
    CapabilityResult,
    PublicActionDefinition,
)


_AUTHORITY_FIELDS = {"user_id", "principal_id"}


def _public_schema(schema: dict) -> dict:
    """Copy a schema while removing model-owned identity fields."""
    copied = deepcopy(schema)
    if not isinstance(copied, dict):
        return {"type": "object", "additionalProperties": True}
    properties = copied.get("properties")
    if isinstance(properties, dict):
        for field_name in _AUTHORITY_FIELDS:
            properties.pop(field_name, None)
        for child in properties.values():
            if isinstance(child, dict):
                child.update(_public_schema(child))
    required = copied.get("required")
    if isinstance(required, list):
        copied["required"] = [name for name in required if name not in _AUTHORITY_FIELDS]
    for key in ("items", "additionalProperties", "not"):
        child = copied.get(key)
        if isinstance(child, dict):
            copied[key] = _public_schema(child)
    for key in ("oneOf", "anyOf", "allOf"):
        children = copied.get(key)
        if isinstance(children, list):
            copied[key] = [_public_schema(child) if isinstance(child, dict) else child for child in children]
    return copied


class CapabilityRegistry:
    """Stores named capabilities and provides lookup for agent discovery."""

    def __init__(self) -> None:
        self._capabilities: Dict[str, BaseCapability] = {}
        self._public_actions: dict[
            str, tuple[BaseCapability, ActionDescriptor]
        ] = {}

    def register(self, capability: BaseCapability) -> None:
        """Register a capability by its name.

        Fails fast on duplicate capability names and duplicate action names.
        """
        name = capability.name
        if name in self._capabilities:
            raise ValueError(f"Capability '{name}' is already registered")

        existing_actions: set[str] = set()
        for cap in self._capabilities.values():
            for action in cap.actions():
                existing_actions.add(action.name)

        actions = capability.actions()
        pending_public_names: set[str] = set()
        for action in actions:
            if action.name in existing_actions:
                raise ValueError(
                    f"Action '{action.name}' in capability '{name}' "
                    f"conflicts with an already-registered action name"
                )
            if action.public_name is None:
                continue
            if (
                action.public_name in self._public_actions
                or action.public_name in pending_public_names
            ):
                raise ValueError(
                    f"Public action name '{action.public_name}' in capability "
                    f"'{name}' conflicts with an already-registered public name"
                )
            pending_public_names.add(action.public_name)

        self._capabilities[name] = capability
        for action in actions:
            if action.public_name is not None:
                self._public_actions[action.public_name] = (capability, action)

    def get(self, name: str) -> BaseCapability:
        """Retrieve a registered capability by name."""
        if name not in self._capabilities:
            raise KeyError(f"Capability '{name}' not found in registry")
        return self._capabilities[name]

    def list_names(self) -> List[str]:
        """Return names of all registered capabilities."""
        return list(self._capabilities.keys())

    def find_action(self, public_name: str) -> tuple[BaseCapability, ActionDescriptor] | None:
        """Find the owning capability and action by explicit public name."""
        owner = self._public_actions.get(public_name)
        if owner is not None:
            return owner
        for capability in self._capabilities.values():
            for descriptor in capability.actions():
                if descriptor.name == public_name:
                    return capability, descriptor
        return None

    def list_actions(self) -> List[ActionDescriptor]:
        """Return all action descriptors from all registered capabilities."""
        actions: list[ActionDescriptor] = []
        for cap in self._capabilities.values():
            actions.extend(cap.actions())
        return actions

    def unregister(self, name: str) -> None:
        """Remove a capability from the registry."""
        if name not in self._capabilities:
            raise KeyError(f"Capability '{name}' not found in registry")
        capability = self._capabilities.pop(name)
        for action in capability.actions():
            if action.public_name is not None:
                self._public_actions.pop(action.public_name, None)

    def get_public_definition(
        self,
        name: str,
        version: str = CONTRACT_VERSION,
    ) -> PublicActionDefinition | None:
        """Return a dependency-free public action definition.

        ``name`` accepts either the explicit public name or the internal
        action name.  A version mismatch is a not-configured result rather
        than silently adapting an incompatible contract.
        """
        owner = self.find_action(name)
        if owner is None:
            return None
        capability, descriptor = owner
        if descriptor.version != version:
            return None
        public_name = descriptor.public_name or descriptor.name
        approval_required = descriptor.approval_required or descriptor.is_side_effect
        return PublicActionDefinition(
            capability_name=capability.name,
            name=descriptor.name,
            public_name=public_name,
            version=descriptor.version,
            description=descriptor.description,
            input_schema=_public_schema(descriptor.input_schema),
            output_schema=deepcopy(descriptor.output_schema),
            risk_level="high" if descriptor.is_side_effect else descriptor.risk_level,
            timeout_seconds=descriptor.timeout_seconds,
            retry_class=descriptor.retry_class,
            idempotency_mode=descriptor.idempotency_mode,
            approval_required=approval_required,
            requires_auth=descriptor.requires_auth,
            is_side_effect=descriptor.is_side_effect,
            max_payload_bytes=descriptor.max_payload_bytes,
        )

    def allowed_public_definitions(
        self,
        allowlist: set[str] | None = None,
        *,
        version: str = CONTRACT_VERSION,
    ) -> list[PublicActionDefinition]:
        """Return only read definitions, optionally narrowed by allowlist.

        An explicit allowlist cannot activate a side-effecting action in this
        batch; writes remain approval-gated and unavailable to tool derivation.
        """
        definitions: list[PublicActionDefinition] = []
        for capability in self._capabilities.values():
            for descriptor in capability.actions():
                public_name = descriptor.public_name or descriptor.name
                if allowlist is not None and not (
                    descriptor.name in allowlist or public_name in allowlist
                ):
                    continue
                definition = self.get_public_definition(public_name, version)
                if definition is None or definition.is_side_effect:
                    continue
                definitions.append(definition)
        return definitions

    def validate_public_output(
        self,
        name: str,
        data: dict,
        *,
        version: str = CONTRACT_VERSION,
        output_schema: dict | None = None,
        max_payload_bytes: int | None = None,
    ) -> dict:
        """Validate and bound a capability result for public adapters."""
        definition = self.get_public_definition(name, version)
        if definition is None:
            return CapabilityResult.fail(
                "Capability action is not configured",
                error_type="not_configured",
            ).to_safe_dict()
        result = CapabilityResult.ok(**data)
        return result.to_safe_dict(
            output_schema=output_schema or definition.output_schema,
            max_payload_bytes=(
                definition.max_payload_bytes
                if max_payload_bytes is None
                else max_payload_bytes
            ),
        )

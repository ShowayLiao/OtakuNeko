"""Capability registry for discovery and lookup.

Does NOT perform routing or dispatching — that belongs to the agent layer.
"""

from __future__ import annotations

from typing import Dict, List

from app.capabilities.base import BaseCapability
from app.capabilities.types import ActionDescriptor


class CapabilityRegistry:
    """Stores named capabilities and provides lookup for agent discovery."""

    def __init__(self) -> None:
        self._capabilities: Dict[str, BaseCapability] = {}

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

        for action in capability.actions():
            if action.name in existing_actions:
                raise ValueError(
                    f"Action '{action.name}' in capability '{name}' "
                    f"conflicts with an already-registered action name"
                )

        self._capabilities[name] = capability

    def get(self, name: str) -> BaseCapability:
        """Retrieve a registered capability by name."""
        if name not in self._capabilities:
            raise KeyError(f"Capability '{name}' not found in registry")
        return self._capabilities[name]

    def list_names(self) -> List[str]:
        """Return names of all registered capabilities."""
        return list(self._capabilities.keys())

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
        del self._capabilities[name]

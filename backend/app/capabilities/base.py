"""Capability base interface.

Every capability exposes a name, a description (for agent discovery),
a list of action descriptors, and an ``execute()`` method that returns
a typed ``CapabilityResult``.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from app.capabilities.types import ActionDescriptor


class BaseCapability(ABC):
    """Stable interface that all capabilities implement.

    Agents depend on this abstraction — not on concrete tools or services.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique capability identifier (e.g. 'anime', 'schedule')."""

    @property
    @abstractmethod
    def description(self) -> str:
        """Human-readable summary for agent discovery."""

    @abstractmethod
    def actions(self) -> list[ActionDescriptor]:
        """Return the action descriptors this capability supports.

        This is the single source of truth for what a capability can do.
        Agents and MCP servers derive their tool lists from these descriptors
        rather than maintaining hard-coded action maps.
        """

    @abstractmethod
    async def execute(self, action: str, **kwargs: Any) -> dict[str, Any]:
        """Execute a named action with the given parameters.

        Returns a structured result dict with at least a ``success`` key.
        """

    def _find_action(self, name: str) -> ActionDescriptor | None:
        """Find an action descriptor by name."""
        for action in self.actions():
            if action.name == name:
                return action
        return None

    def validate_action(self, name: str) -> bool:
        """Check whether a named action is supported."""
        return self._find_action(name) is not None

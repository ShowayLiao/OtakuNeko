"""Capability base interface.

Every capability exposes a name, a description (for agent discovery),
and an ``execute()`` method that returns a structured result.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


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
    async def execute(self, action: str, **kwargs: Any) -> dict[str, Any]:
        """Execute a named action with the given parameters.

        Returns a structured result dict with at least a ``success`` key.
        """

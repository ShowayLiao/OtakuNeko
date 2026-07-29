"""Capability base interface.

Every capability exposes a name, a description (for agent discovery),
a list of action descriptors, and an ``execute()`` method that returns
a typed ``CapabilityResult``.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from functools import wraps
from typing import Any

from app.capabilities.types import ActionDescriptor
from app.trace import TraceEventType
from app.trace.recorder import (
    current_trace_recorder,
    safe_argument_shape,
    trace_span,
)


class BaseCapability(ABC):
    """Stable interface that all capabilities implement.

    Agents depend on this abstraction — not on concrete tools or services.
    """

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        execute = cls.__dict__.get("execute")
        if execute is None or getattr(execute, "__trace_instrumented__", False):
            return

        @wraps(execute)
        async def traced_execute(self, action: str, **call_kwargs: Any):
            if current_trace_recorder() is None:
                return await execute(self, action, **call_kwargs)
            async with trace_span(
                TraceEventType.CAPABILITY_CALL,
                f"{self.name}.{action}",
                {"argument_shape": safe_argument_shape(call_kwargs)},
            ) as event:
                result = await execute(self, action, **call_kwargs)
                if (
                    event is not None
                    and isinstance(result, dict)
                    and result.get("success") is False
                ):
                    event.status = "failed"
                    event.data["error_category"] = str(
                        result.get("error_type", "capability_error")
                    )
                return result

        traced_execute.__trace_instrumented__ = True
        cls.execute = traced_execute

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

"""MCP authentication context.

Carries verified caller identity so tool dispatch can enforce ownership
and authorization separate from tool arguments.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, AsyncContextManager, Callable


DependencyProvider = Callable[[], AsyncContextManager[dict[str, Any]]]


@dataclass(frozen=True)
class MCPContext:
    """Verified caller context for MCP tool dispatch.

    ``user_id`` is ``None`` for unauthenticated (anonymous) callers.
    """

    user_id: int | None = None
    extra: dict[str, Any] = field(default_factory=dict)
    dependency_provider: DependencyProvider | None = field(
        default=None,
        repr=False,
        compare=False,
    )

    @property
    def is_authenticated(self) -> bool:
        return self.user_id is not None

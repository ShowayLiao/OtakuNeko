"""Side-effect policy for MCP tool dispatch.

Carries explicit enablement flags so write/delete operations can only be
invoked when the caller has opted into side effects.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class Policy:
    """Policy flags for capability action execution.

    ``allow_side_effects`` must be ``True`` to invoke actions marked
    ``is_side_effect=True`` in their descriptor. Each approved write also
    requires a caller-generated idempotency key.
    """

    allow_side_effects: bool = False
    idempotency_key: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)

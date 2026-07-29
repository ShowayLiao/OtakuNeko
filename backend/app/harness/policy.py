"""Policy enforcement for scheduled agent execution."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ProactivePolicy:
    allowed_capabilities: tuple[str, ...] = ()
    max_retries: int = 3
    timeout_seconds: int = 120
    max_model_calls: int = 3
    extra: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_json(cls, raw: str | dict[str, Any] | None) -> "ProactivePolicy":
        value = json.loads(raw or "{}") if isinstance(raw, str) else (raw or {})
        if not isinstance(value, dict):
            raise ValueError("policy must be an object")
        capabilities = value.get("allowed_capabilities", ())
        if not isinstance(capabilities, (list, tuple)):
            raise ValueError("allowed_capabilities must be a list")
        retries = int(value.get("max_retries", 3))
        timeout = int(value.get("timeout_seconds", 120))
        model_calls = int(value.get("max_model_calls", 3))
        if retries < 0 or retries > 10 or timeout <= 0 or model_calls < 0 or model_calls > 20:
            raise ValueError("invalid proactive policy limits")
        return cls(tuple(str(item) for item in capabilities), retries, timeout, model_calls, value)

    def allows(self, capability: str) -> bool:
        return capability in self.allowed_capabilities

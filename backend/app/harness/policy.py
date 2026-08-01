"""Policy enforcement for scheduled agent execution."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from app.capabilities.types import ActionDescriptor


@dataclass(frozen=True)
class Principal:
    """Trusted authenticated identity supplied by the Runtime."""

    principal_id: int
    roles: frozenset[str] = frozenset()

    @property
    def id(self) -> int:
        """Compatibility alias for policy integrations."""
        return self.principal_id


@dataclass(frozen=True)
class Approval:
    """Server-side approval state; never populated from model arguments."""

    approval_id: str
    approved: bool = True
    principal_id: int | None = None
    action: str | None = None


@dataclass(frozen=True)
class PolicyDecision:
    allowed: bool
    error_type: str | None = None
    reason: str | None = None

    def __bool__(self) -> bool:
        return self.allowed


class PolicyEngine:
    """Authorize a capability action before any domain service is called."""

    def __init__(self, *, allow_side_effects: bool = False) -> None:
        self.allow_side_effects = allow_side_effects

    def authorize(
        self,
        principal: Principal | None,
        descriptor: ActionDescriptor,
        approval: Approval | None,
        idempotency_key: str | None,
    ) -> PolicyDecision:
        if descriptor.requires_auth and (
            principal is None or principal.principal_id <= 0
        ):
            return PolicyDecision(False, "unauthorized", "Authenticated principal required")

        if descriptor.is_side_effect and (
            principal is None or principal.principal_id <= 0
        ):
            return PolicyDecision(False, "unauthorized", "Authenticated principal required")

        if not descriptor.is_side_effect:
            return PolicyDecision(True)

        if not self.allow_side_effects:
            return PolicyDecision(
                False,
                "policy_denied",
                "Side effects are disabled by policy",
            )

        if approval is None or not isinstance(approval, Approval) or not approval.approved:
            return PolicyDecision(
                False,
                "policy_denied",
                "Trusted approval is required",
            )
        if (
            principal is not None
            and approval.principal_id is not None
            and approval.principal_id != principal.principal_id
        ):
            return PolicyDecision(False, "policy_denied", "Approval principal mismatch")
        if approval.action is not None and approval.action != descriptor.name:
            return PolicyDecision(False, "policy_denied", "Approval action mismatch")

        if descriptor.is_side_effect and not (
            isinstance(idempotency_key, str) and idempotency_key.strip()
        ):
            return PolicyDecision(
                False,
                "idempotency_required",
                "An explicit idempotency key is required",
            )
        return PolicyDecision(True)


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

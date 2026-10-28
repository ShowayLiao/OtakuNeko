"""Trusted, bounded read-error recovery policy for Decision execution."""

from dataclasses import dataclass
from hashlib import sha256
import json

from app.harness.contracts import AgentDecision, InvocationResult


@dataclass(frozen=True)
class RecoveryPolicy:
    read_only_errors: bool = False
    max_repeated_failures: int = 1

    def __post_init__(self) -> None:
        if type(self.read_only_errors) is not bool:
            raise ValueError("read_only_errors must be boolean")
        if (
            type(self.max_repeated_failures) is not int
            or self.max_repeated_failures < 1
        ):
            raise ValueError("max_repeated_failures must be a positive integer")


def action_fingerprint(decision: AgentDecision) -> str:
    """Avoid persisting argument values in recovery counters."""
    value = [decision.capability, decision.capability_version, decision.arguments]
    return sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def recoverable_read_failure(
    invocation: InvocationResult, *, legacy: bool = False
) -> bool:
    # Adapter errors with auth/policy/unknown outcomes must remain fail-closed,
    # even if a downstream adapter accidentally labels them as `failed`.
    return (
        invocation.status == "failed"
        and invocation.error_code
        not in {
            "unauthorized",
            "policy_denied",
            "identity_spoofing",
            "not_configured",
            "idempotency_required",
            "idempotency_conflict",
            "attention_required",
            "cancelled",
            "timeout",
            "budget_exceeded",
        }
        and invocation.output.get("error_type")
        not in {
            "unauthorized",
            "policy_denied",
            "attention_required",
            "cancelled",
            "timeout",
        }
        and (
            legacy
            or invocation.error_code in {"read_failure", "transient", "rate_limited"}
        )
    )

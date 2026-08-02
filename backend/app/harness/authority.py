"""Single contract for fields owned by the trusted runtime."""

from __future__ import annotations

from typing import Any


RUNTIME_OWNED_FIELDS = frozenset(
    {
        "user_id",
        "principal_id",
        "tenant_id",
        "role",
        "scope",
        "db",
        "token",
        "approval_state",
    }
)


class AuthorityFieldError(ValueError):
    """Raised when untrusted input attempts to provide runtime authority."""


def contains_runtime_owned_field(value: Any) -> bool:
    if isinstance(value, dict):
        return any(
            key in RUNTIME_OWNED_FIELDS or contains_runtime_owned_field(child)
            for key, child in value.items()
        )
    if isinstance(value, list):
        return any(contains_runtime_owned_field(child) for child in value)
    return False


def reject_runtime_owned_fields(value: Any, *, label: str = "arguments") -> Any:
    if contains_runtime_owned_field(value):
        raise AuthorityFieldError(
            f"Runtime-owned authority fields are not accepted in {label}"
        )
    return value


def strip_runtime_owned_fields(value: Any) -> Any:
    """Return a copy suitable for public schemas or untrusted projections."""
    if isinstance(value, dict):
        copied = {
            key: strip_runtime_owned_fields(child)
            for key, child in value.items()
            if key not in RUNTIME_OWNED_FIELDS
        }
        required = value.get("required")
        if isinstance(required, list):
            copied["required"] = [
                name
                for name in required
                if name not in RUNTIME_OWNED_FIELDS
            ]
        return copied
    if isinstance(value, list):
        return [strip_runtime_owned_fields(child) for child in value]
    return value

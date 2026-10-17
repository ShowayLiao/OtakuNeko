from __future__ import annotations

from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.harness.authority import reject_runtime_owned_fields


CONTRACT_VERSION: Literal["v1"] = "v1"


class ErrorCode(str, Enum):
    INVALID_REQUEST = "invalid_request"
    UNAUTHORIZED = "unauthorized"
    POLICY_DENIED = "policy_denied"
    TIMEOUT = "timeout"
    CANCELLED = "cancelled"
    BUDGET_EXCEEDED = "budget_exceeded"
    PROVIDER_ERROR = "provider_error"
    TOOL_ERROR = "tool_error"
    TRANSIENT = "transient"
    PERMANENT = "permanent"


def _reject_model_owned_identity(arguments: dict[str, Any]) -> dict[str, Any]:
    try:
        return reject_runtime_owned_fields(arguments)
    except ValueError as exc:
        raise ValueError("authority fields are injected by the runtime") from exc


class ContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["v1"] = CONTRACT_VERSION


class RunRequest(ContractModel):
    run_id: str
    user_id: int | None = None
    goal: str
    messages: list[dict[str, Any]] = Field(default_factory=list)
    model: str


class ExecutionContext(ContractModel):
    principal_id: int | None
    run_id: str
    trace_id: str
    capability_allowlist: frozenset[str] = frozenset()
    tenant_id: int | str | None = None
    role: str | None = None
    scope: frozenset[str] = frozenset()
    thread_id: str | None = None


class AgentDecision(ContractModel):
    decision_id: str
    run_id: str
    action: Literal["invoke", "respond", "finish"]
    capability: str | None = None
    capability_version: str | None = None
    arguments: dict[str, Any] = Field(default_factory=dict)
    content: str | None = None

    _identity_guard = field_validator("arguments")(_reject_model_owned_identity)


class InvocationRequest(ContractModel):
    invocation_id: str
    run_id: str
    capability: str
    capability_version: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    idempotency_key: str | None = None

    _identity_guard = field_validator("arguments")(_reject_model_owned_identity)


class InvocationResult(ContractModel):
    invocation_id: str
    status: Literal["succeeded", "failed", "denied", "cancelled", "timeout"]
    output: dict[str, Any] = Field(default_factory=dict)
    # ``not_configured`` and adapter-specific safe categories are intentionally
    # represented as strings until the cross-batch error vocabulary is frozen.
    error_code: ErrorCode | str | None = None
    retryable: bool = False
    run_id: str | None = None
    decision_id: str | None = None
    trace_id: str | None = None
    sequence: int | None = Field(default=None, ge=1)
    capability: str | None = None
    capability_version: str | None = None
    artifacts: list[dict[str, Any]] = Field(default_factory=list)
    usage: dict[str, Any] = Field(default_factory=dict)
    latency_ms: int | None = Field(default=None, ge=0)
    provenance: dict[str, Any] = Field(default_factory=dict)
    model_output: dict[str, Any] = Field(default_factory=dict)


class RunEvent(ContractModel):
    run_id: str
    sequence: int = Field(ge=1)
    event_type: str
    invocation_id: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)


class RunResult(ContractModel):
    run_id: str
    status: Literal["completed", "failed", "cancelled", "timeout"]
    content: str | None = None
    error_code: ErrorCode | None = None

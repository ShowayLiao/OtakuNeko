from __future__ import annotations

from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


CONTRACT_VERSION = "v1"


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
    if "user_id" in arguments or "principal_id" in arguments:
        raise ValueError("identity fields are injected by the runtime")
    return arguments


class ContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[CONTRACT_VERSION] = CONTRACT_VERSION


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


class AgentDecision(ContractModel):
    decision_id: str
    run_id: str
    action: Literal["invoke", "respond", "finish"]
    capability: str | None = None
    arguments: dict[str, Any] = Field(default_factory=dict)

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
    status: Literal["succeeded", "failed", "denied", "cancelled"]
    output: dict[str, Any] = Field(default_factory=dict)
    error_code: ErrorCode | None = None
    retryable: bool = False


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

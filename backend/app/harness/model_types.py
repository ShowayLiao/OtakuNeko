"""Provider-neutral model call contracts used at the harness boundary."""

from __future__ import annotations

from decimal import Decimal
from typing import Any, AsyncIterator, Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field


ProviderErrorCode = Literal[
    "auth",
    "rate_limited",
    "timeout",
    "invalid_request",
    "transient",
    "permanent",
    "cancelled",
]
ModelCallStatus = Literal["completed", "degraded", "failed", "cancelled"]


class ModelUsage(BaseModel):
    """Usage known at the provider boundary; unknown token values stay None."""

    model_config = ConfigDict(extra="forbid")

    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_tokens: int | None = None
    latency_ms: int = Field(default=0, ge=0)
    estimated_cost_usd: Decimal | None = None


class ModelDelta(BaseModel):
    """Provider-neutral incremental model output."""

    model_config = ConfigDict(extra="forbid")

    kind: Literal["text", "reasoning", "tool_call", "error"]
    text: str | None = None
    tool_call: dict[str, Any] | None = None
    finish_reason: str | None = None
    error_code: ProviderErrorCode | None = None


class ModelCallResult(BaseModel):
    """Normalized result for both complete and streamed model calls."""

    model_config = ConfigDict(extra="forbid")

    provider: str
    model: str
    operation: str
    status: ModelCallStatus
    text: str = ""
    usage: ModelUsage = Field(default_factory=ModelUsage)
    finish_reason: str | None = None
    error_code: ProviderErrorCode | None = None
    retryable: bool = False


class ProviderModelAdapter(Protocol):
    """Provider-neutral adapter implemented by OpenAI-compatible clients."""

    async def complete(
        self,
        *,
        messages: list[dict[str, Any]],
        model: str,
        temperature: float = 0.6,
        **kwargs: Any,
    ) -> ModelCallResult:
        ...

    def stream(
        self,
        *,
        messages: list[dict[str, Any]],
        model: str,
        temperature: float = 0.6,
        **kwargs: Any,
    ) -> AsyncIterator[ModelDelta]:
        ...

"""In-memory run budgets and cooperative cancellation primitives."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from decimal import Decimal
from math import isfinite
from time import monotonic
from typing import Any

from app.harness.model_types import ModelUsage


class BudgetExceededError(RuntimeError):
    """Raised when a finite run budget has no remaining capacity."""

    def __init__(self, dimension: str) -> None:
        self.dimension = dimension
        super().__init__(f"run budget exceeded: {dimension}")


class DeadlineExceededError(TimeoutError):
    """Raised when the run deadline has elapsed."""


class RunCancellationError(asyncio.CancelledError):
    """Cancellation requested through the run token.

    This subclass lets the Coordinator distinguish cooperative run cancellation
    from cancellation of the asyncio task that is consuming the stream.
    """


@dataclass
class RunBudget:
    """Finite counters shared by model, tool and adapter execution.

    Provider usage may be unavailable. In that case the corresponding unknown
    counter is incremented explicitly; unknown usage never means unlimited
    budget and is never silently converted to a fabricated zero.
    """

    max_steps: int = 24
    max_tool_calls: int = 16
    max_model_calls: int = 8
    deadline_seconds: float = 120.0
    max_total_tokens: int = 100_000
    max_cost_usd: Decimal = field(default_factory=lambda: Decimal("10.00"))

    started_at: float = field(default_factory=monotonic, init=False, repr=False)
    steps_used: int = field(default=0, init=False)
    tool_calls_used: int = field(default=0, init=False)
    model_calls_used: int = field(default=0, init=False)
    total_tokens_used: int = field(default=0, init=False)
    total_cost_usd: Decimal = field(default_factory=lambda: Decimal("0"), init=False)
    unknown_token_calls: int = field(default=0, init=False)
    unknown_cost_calls: int = field(default=0, init=False)

    def __post_init__(self) -> None:
        for name in (
            "max_steps",
            "max_tool_calls",
            "max_model_calls",
            "max_total_tokens",
        ):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(f"{name} must be a finite non-negative integer")
        if (
            isinstance(self.deadline_seconds, bool)
            or not isinstance(self.deadline_seconds, (int, float))
            or not isfinite(float(self.deadline_seconds))
            or self.deadline_seconds <= 0
        ):
            raise ValueError("deadline_seconds must be finite and greater than zero")
        try:
            cost = Decimal(str(self.max_cost_usd))
        except Exception as exc:  # pragma: no cover - defensive validation
            raise ValueError("max_cost_usd must be a finite Decimal") from exc
        if not cost.is_finite() or cost < 0:
            raise ValueError("max_cost_usd must be finite and non-negative")
        self.max_cost_usd = cost

    @property
    def deadline_at(self) -> float:
        return self.started_at + float(self.deadline_seconds)

    def remaining_seconds(self) -> float:
        return max(0.0, self.deadline_at - monotonic())

    def check_deadline(self) -> None:
        if monotonic() >= self.deadline_at:
            raise DeadlineExceededError("run deadline exceeded")

    def consume_step(self) -> None:
        self._consume("steps", self.steps_used, self.max_steps)
        self.steps_used += 1

    def consume_tool_call(self) -> None:
        self._consume("tool_calls", self.tool_calls_used, self.max_tool_calls)
        self.tool_calls_used += 1

    def consume_model_call(self, usage: ModelUsage | None) -> None:
        self.reserve_model_call()
        self.record_model_usage(usage)

    def reserve_model_call(self) -> None:
        """Reserve a model call before crossing into a provider boundary."""
        self._consume("model_calls", self.model_calls_used, self.max_model_calls)
        self.model_calls_used += 1

    def record_model_usage(self, usage: ModelUsage | None) -> None:
        """Account for usage returned after a reserved model call."""
        if usage is None:
            self.unknown_token_calls += 1
            self.unknown_cost_calls += 1
            return

        total_tokens = usage.total_tokens
        if total_tokens is None:
            if usage.prompt_tokens is not None and usage.completion_tokens is not None:
                total_tokens = usage.prompt_tokens + usage.completion_tokens
            else:
                self.unknown_token_calls += 1
        if total_tokens is not None:
            next_total = self.total_tokens_used + total_tokens
            if next_total > self.max_total_tokens:
                raise BudgetExceededError("total_tokens")
            self.total_tokens_used = next_total

        if usage.estimated_cost_usd is None:
            self.unknown_cost_calls += 1
        else:
            cost = Decimal(str(usage.estimated_cost_usd))
            if not cost.is_finite() or cost < 0:
                self.unknown_cost_calls += 1
            elif self.total_cost_usd + cost > self.max_cost_usd:
                raise BudgetExceededError("cost_usd")
            else:
                self.total_cost_usd += cost

    def snapshot(self) -> dict[str, Any]:
        """Return a serializable budget snapshot for state/trace metadata."""
        return {
            "max_steps": self.max_steps,
            "max_tool_calls": self.max_tool_calls,
            "max_model_calls": self.max_model_calls,
            "deadline_seconds": float(self.deadline_seconds),
            "max_total_tokens": self.max_total_tokens,
            "max_cost_usd": self.max_cost_usd,
            "steps_used": self.steps_used,
            "tool_calls_used": self.tool_calls_used,
            "model_calls_used": self.model_calls_used,
            "total_tokens_used": self.total_tokens_used,
            "total_cost_usd": self.total_cost_usd,
            "unknown_token_calls": self.unknown_token_calls,
            "unknown_cost_calls": self.unknown_cost_calls,
        }

    @staticmethod
    def _consume(dimension: str, used: int, limit: int) -> None:
        if used >= limit:
            raise BudgetExceededError(dimension)


class CancellationToken:
    """Cooperative cancellation shared across adapter boundaries."""

    def __init__(self) -> None:
        self._event = asyncio.Event()

    def cancel(self) -> None:
        self._event.set()

    def is_cancelled(self) -> bool:
        return self._event.is_set()

    def raise_if_cancelled(self) -> None:
        if self.is_cancelled():
            raise RunCancellationError()

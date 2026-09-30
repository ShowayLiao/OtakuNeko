"""Strict data contracts for the EVAL-001 evaluation framework."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Category(str, Enum):
    ANIME_KNOWLEDGE = "anime_knowledge"
    RECOMMENDATION = "recommendation"
    COMPANION = "companion"
    ROUTING = "routing"
    SAFETY = "safety"
    RECOVERY = "recovery"


class ExpectedRoute(str, Enum):
    CHAT = "chat"
    RECOMMENDATION = "recommendation"
    SCHEDULE = "schedule"
    MEDIA = "media"
    REFUSAL = "refusal"


class UserFixture(StrictModel):
    user_id: int = Field(ge=1)
    attributes: dict[str, Any] = Field(default_factory=dict)


class MemoryFixture(StrictModel):
    kind: str
    content: str
    thread_id: str | None = None


class InputMessage(StrictModel):
    role: str = Field(min_length=1)
    content: str


class CaseAssertions(StrictModel):
    response_schema: str = "text"
    required_evidence: list[str] = Field(default_factory=list)
    require_recovery: bool = False
    max_latency_ms: float = Field(default=1000, gt=0)
    max_calls: int = Field(default=10, ge=0)


class ScriptEvent(StrictModel):
    type: Literal[
        "route",
        "tool_call_start",
        "tool_call_end",
        "message_chunk",
        "structured_response",
        "recovery",
        "provider_error",
        "policy_denied",
        "budget_exceeded",
        "timeout",
        "cancelled",
        "reconnect",
        "model_call",
    ]
    route: str | None = None
    name: str | None = None
    content: str | None = None
    output: dict[str, Any] | None = None
    arguments: dict[str, Any] | None = None
    provider: str | None = None
    model: str | None = None
    invocation_id: str | None = None
    usage: dict[str, Any] | None = None
    estimated_cost_usd: float | None = Field(default=None, ge=0)
    value: Any = None
    status: str | None = None
    duration_ms: float = Field(default=0, ge=0)
    code: str | None = None


class ExecutionFixture(StrictModel):
    events: list[ScriptEvent] = Field(min_length=1)


class ExecutionResult(StrictModel):
    """Normalized result derived from actual orchestration events."""

    route: str
    capabilities: list[str] = Field(default_factory=list)
    text: str = ""
    evidence: list[str] = Field(default_factory=list)
    schema_valid: bool = True
    recovered: bool = False
    latency_ms: float = Field(default=0, ge=0)
    call_count: int = Field(default=0, ge=0)
    run_id: str | None = None
    run_status: Literal["completed", "failed", "cancelled", "timeout"] = "completed"
    tool_call_count: int = Field(default=0, ge=0)
    tool_success_count: int = Field(default=0, ge=0)
    tool_failure_count: int = Field(default=0, ge=0)
    policy_denied_count: int = Field(default=0, ge=0)
    budget_exceeded_count: int = Field(default=0, ge=0)
    cancelled_count: int = Field(default=0, ge=0)
    reconnect_count: int = Field(default=0, ge=0)
    model_call_count: int = Field(default=0, ge=0)
    model_tokens: int | None = Field(default=None, ge=0)
    estimated_cost_usd: float | None = Field(default=None, ge=0)
    estimated_cost_unknown_count: int = Field(default=0, ge=0)
    tool_argument_keys: list[str] = Field(default_factory=list)
    providers: list[str] = Field(default_factory=list)
    models: list[str] = Field(default_factory=list)


class EvalCase(StrictModel):
    id: str = Field(min_length=1)
    category: Category
    input_messages: list[InputMessage] = Field(min_length=1)
    user_fixture: UserFixture
    memory_fixtures: list[MemoryFixture] = Field(default_factory=list)
    expected_route: ExpectedRoute | None = None
    required_capabilities: list[str] = Field(default_factory=list)
    forbidden_capabilities: list[str] = Field(default_factory=list)
    forbidden_phrases: list[str] = Field(default_factory=list)
    assertions: CaseAssertions
    fixtures: ExecutionFixture
    tags: list[str] = Field(default_factory=list)


class DatasetManifest(StrictModel):
    dataset_version: str = Field(min_length=1)
    schema_version: int = Field(ge=1)


class EvalDataset(StrictModel):
    dataset_version: str
    schema_version: int
    cases: list[EvalCase]


class MetricResult(StrictModel):
    metric: str
    value: float
    passed: bool
    detail: str = ""


class JudgeOutcome(StrictModel):
    status: str = "not_requested"
    model: str | None = None
    provider: str | None = None
    score: float | None = None
    dimensions: dict[str, float] = Field(default_factory=dict)
    explanation: str = ""
    error: str = ""
    cost_usd: float = Field(default=0, ge=0)


class CaseResult(StrictModel):
    case_id: str
    category: str
    passed: bool
    actual_route: str | None = None
    capabilities: list[str] = Field(default_factory=list)
    metrics: list[MetricResult] = Field(default_factory=list)
    judge: JudgeOutcome = Field(default_factory=JudgeOutcome)
    error: str | None = None
    run_id: str | None = None
    observability: dict[str, float] = Field(default_factory=dict)
    tool_argument_keys: list[str] = Field(default_factory=list)
    providers: list[str] = Field(default_factory=list)
    models: list[str] = Field(default_factory=list)


class AgentMetadata(StrictModel):
    name: str
    model: str = "offline"
    provider: str = "fixture"


class EvalReport(StrictModel):
    schema_version: int = 1
    task: str = "EVAL-001"
    dataset_version: str
    config_name: str
    code_revision: str
    agent: AgentMetadata
    started_at: datetime = Field(default_factory=utc_now)
    completed_at: datetime | None = None
    cases: list[CaseResult] = Field(default_factory=list)
    aggregates: dict[str, float] = Field(default_factory=dict)
    gate_failures: list[str] = Field(default_factory=list)
    baseline_failures: list[str] = Field(default_factory=list)
    evaluation_budget: dict[str, Any] = Field(default_factory=dict)

    @property
    def total(self) -> int:
        return len(self.cases)

    @property
    def passed_count(self) -> int:
        return sum(1 for case in self.cases if case.passed)

    @property
    def failed_count(self) -> int:
        return self.total - self.passed_count

    @property
    def pass_rate(self) -> float:
        return self.passed_count / self.total if self.total else 1.0

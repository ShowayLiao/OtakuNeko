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


class ToolErrorSample(StrictModel):
    """One failed tool invocation observed on the Runtime event path."""

    capability: str = "unknown"
    error_code: str | None = None
    status: str = "failed"


class ArgumentSample(StrictModel):
    """Ordered synthetic capability execution; no raw values are retained."""

    capability: str
    arguments_digest: str = Field(pattern=r"^[0-9a-f]{64}$")


class ExecutionResult(StrictModel):
    """Normalized result derived from actual orchestration events."""

    route: str
    route_agent: str | None = None
    route_observed: bool = False
    capabilities: list[str] = Field(default_factory=list)
    text: str = ""
    evidence: list[str] = Field(default_factory=list)
    schema_valid: bool = True
    recovered: bool = False
    latency_ms: float = Field(default=0, ge=0)
    call_count: int = Field(default=0, ge=0)
    run_id: str | None = None
    trace_id: str | None = None
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
    prompt_tokens: int | None = Field(default=None, ge=0)
    completion_tokens: int | None = Field(default=None, ge=0)
    estimated_cost_usd: float | None = Field(default=None, ge=0)
    estimated_cost_unknown_count: int = Field(default=0, ge=0)
    artifact_error: str | None = None
    tool_arguments: list[ArgumentSample] = Field(default_factory=list)
    tool_argument_keys: list[str] = Field(default_factory=list)
    providers: list[str] = Field(default_factory=list)
    models: list[str] = Field(default_factory=list)
    terminal_error_code: str | None = None
    termination_reason: str | None = None
    provider_failure: dict[str, Any] | None = None
    step_count: int = Field(default=0, ge=0)
    tool_errors: list[ToolErrorSample] = Field(default_factory=list)
    task_success: bool | None = None
    benchmark_status: (
        Literal["PASS", "FAIL", "ERROR", "SKIP", "UNSUPPORTED", "UNGRADED"] | None
    ) = None
    hard_checks: list[HardCheckResult] = Field(default_factory=list, exclude=True)


class ToolExpectation(StrictModel):
    required: list[str] = Field(default_factory=list)
    forbidden: list[str] = Field(default_factory=list)


class ArgumentExpectation(StrictModel):
    """Legacy key checks plus optional ordered synthetic execution digests."""

    invocations: list[ArgumentSample] | None = None

    required_keys: list[str] = Field(default_factory=list)
    forbidden_keys: list[str] = Field(default_factory=list)


class TerminationExpectation(StrictModel):
    status: Literal["completed", "failed", "cancelled", "timeout"] = "completed"
    error_code: str | None = None
    termination_reason: str | None = None


class EvidenceExpectation(StrictModel):
    required_citations: list[str] = Field(default_factory=list)
    required: list[str] = Field(default_factory=list)
    forbidden: list[str] = Field(default_factory=list)


class RecoveryExpectation(StrictModel):
    required: bool = False


class StepExpectation(StrictModel):
    min_steps: int = Field(default=0, ge=0)
    max_steps: int = Field(default=1000, ge=0)


class ToolErrorExpectation(StrictModel):
    max_failures: int = Field(default=0, ge=0)
    allowed_error_codes: list[str] = Field(default_factory=list)
    required_error_codes: list[str] = Field(default_factory=list)


class FinalAnswerExpectation(StrictModel):
    """Opt-in acceptance of the final response, independent of tool success."""

    required_text: list[str] = Field(default_factory=list)
    forbidden_text: list[str] = Field(default_factory=list)
    expected_json: dict[str, Any] | list[Any] | None = None


class DeterministicCaseSpec(StrictModel):
    """Versioned, deterministic expectation bound to one evaluation case."""

    schema_version: Literal[1] = 1
    final_answer: FinalAnswerExpectation | None = None
    tools: ToolExpectation = Field(default_factory=ToolExpectation)
    arguments: ArgumentExpectation = Field(default_factory=ArgumentExpectation)
    termination: TerminationExpectation = Field(default_factory=TerminationExpectation)
    evidence: EvidenceExpectation = Field(default_factory=EvidenceExpectation)
    recovery: RecoveryExpectation = Field(default_factory=RecoveryExpectation)
    steps: StepExpectation = Field(default_factory=StepExpectation)
    tool_errors: ToolErrorExpectation = Field(default_factory=ToolErrorExpectation)


class AnswerQualitySpec(StrictModel):
    """Non-deterministic answer rubric; a Judge scores it separately."""

    rubric: str = ""
    min_score: float = Field(default=0.0, ge=0, le=1)
    required: bool = False


class ApprovalFixture(StrictModel):
    """Trusted test approval; the principal always comes from the fixture user."""

    action: str = Field(min_length=1)


class EvalCase(StrictModel):
    id: str = Field(min_length=1)
    category: Category
    input_messages: list[InputMessage] = Field(min_length=1)
    user_fixture: UserFixture
    memory_fixtures: list[MemoryFixture] = Field(default_factory=list)
    expected_route: ExpectedRoute | None = None
    expected_agent: str | None = None
    required_capabilities: list[str] = Field(default_factory=list)
    forbidden_capabilities: list[str] = Field(default_factory=list)
    forbidden_phrases: list[str] = Field(default_factory=list)
    assertions: CaseAssertions
    fixtures: ExecutionFixture
    tags: list[str] = Field(default_factory=list)
    deterministic: DeterministicCaseSpec | None = None
    answer_quality: AnswerQualitySpec | None = None
    approvals: list[ApprovalFixture] = Field(default_factory=list)


class DatasetManifest(StrictModel):
    dataset_version: str = Field(min_length=1)
    schema_version: int = Field(ge=1)


class EvalDataset(StrictModel):
    dataset_version: str
    schema_version: int
    content_digest: str = ""
    cases: list[EvalCase]


class MetricResult(StrictModel):
    metric: str
    value: float
    passed: bool
    detail: str = ""


class HardCheckResult(StrictModel):
    """Safe, machine-readable result for one benchmark oracle check."""

    rule: str
    status: Literal["PASS", "FAIL", "UNSUPPORTED", "UNGRADED"]
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
    rubric_version: str | None = None
    rubric_digest: str | None = None
    quality_passed: bool | None = None


class HumanReview(StrictModel):
    """Human conclusion for one case; never feeds the functional gate."""

    schema_version: Literal[1] = 1
    reviewer: str = Field(min_length=1, max_length=100)
    verdict: Literal["accept", "reject", "needs_discussion"]
    rubric_version: str = Field(min_length=1)
    notes: str = Field(default="", max_length=2000)
    reviewed_at: datetime | None = None


class ReviewQueueEntry(StrictModel):
    """One disputed or unresolved case, pointing at its redacted transcript."""

    case_id: str
    run_id: str | None = None
    trace_id: str | None = None
    outcome: str | None = None
    judge_status: str = "not_requested"
    judge_score: float | None = None
    quality_passed: bool | None = None
    human_verdict: str | None = None
    reason: str
    transcript: str | None = None


class RunUsage(StrictModel):
    """Per-run usage facts, with unknown cost/tokens kept distinguishable."""

    model_calls: int = Field(default=0, ge=0)
    model_tokens: int | None = Field(default=None, ge=0)
    prompt_tokens: int | None = Field(default=None, ge=0)
    completion_tokens: int | None = Field(default=None, ge=0)
    latency_ms: float = Field(default=0, ge=0)
    estimated_cost_usd: float | None = Field(default=None, ge=0)
    estimated_cost_unknown_count: int = Field(default=0, ge=0)


class RunIndexEntry(StrictModel):
    """Report-level pointers to one persisted Run, Trace, and transcript."""

    case_id: str
    run_id: str | None = None
    trace_id: str | None = None
    trace_path: str | None = None
    transcript_path: str | None = None
    message_count: int = Field(default=0, ge=0)
    run_status: str | None = None
    outcome: str | None = None
    provider: str | None = None
    model: str | None = None
    usage: RunUsage = Field(default_factory=RunUsage)
    error: str | None = None


class DimensionScore(StrictModel):
    dimension: str
    passed: bool
    score: float = Field(ge=0, le=1)
    detail: str = ""


class DeterministicScore(StrictModel):
    """Deterministic verdict. Answer quality is never part of this result."""

    schema_version: Literal[1] = 1
    case_id: str
    task_success: bool
    dimensions: list[DimensionScore] = Field(default_factory=list)
    answer_quality_excluded: Literal[True] = True


L6Outcome = Literal[
    "passed",
    "functional_failure",
    "provider_error",
    "execution_error",
    "cancelled",
]


class L6CaseScore(StrictModel):
    """Functional correctness score derived from one normalized Runtime result.

    Provider and execution failures carry an outcome but no functional scores,
    so they never enter the functional denominator.
    """

    schema_version: Literal[1] = 1
    case_id: str
    outcome: L6Outcome
    terminal_error_code: str | None = None
    task_success: bool | None = None
    scores: dict[str, float] = Field(default_factory=dict)
    dimensions: list[DimensionScore] = Field(default_factory=list)


class CaseResult(StrictModel):
    case_id: str
    category: str
    passed: bool
    functional_passed: bool | None = None
    functional_status: (
        Literal["NOT_RUN", "EXECUTION_FAILED", "ASSERTION_FAILED", "PASSED"] | None
    ) = None
    quality_status: Literal["GRADED", "UNGRADED", "NOT_REQUESTED"] = "NOT_REQUESTED"
    benchmark_status: (
        Literal["PASS", "FAIL", "ERROR", "SKIP", "UNSUPPORTED", "UNGRADED"] | None
    ) = None
    hard_checks: list[HardCheckResult] = Field(default_factory=list)
    actual_route: str | None = None
    route_agent: str | None = None
    route_observed: bool = False
    router_expected_agent: str | None = None
    router_match: bool | None = None
    capabilities: list[str] = Field(default_factory=list)
    metrics: list[MetricResult] = Field(default_factory=list)
    judge: JudgeOutcome = Field(default_factory=JudgeOutcome)
    error: str | None = None
    run_id: str | None = None
    trace_id: str | None = None
    trace_path: str | None = None
    run_status: str | None = None
    terminal_error_code: str | None = None
    provider_failure: dict[str, Any] | None = None
    outcome: L6Outcome | None = None
    step_count: int | None = None
    tool_failure_count: int | None = None
    recovered: bool | None = None
    observability: dict[str, float | None] = Field(default_factory=dict)
    artifact_error: str | None = None
    tool_arguments: list[ArgumentSample] = Field(default_factory=list)
    tool_argument_keys: list[str] = Field(default_factory=list)
    providers: list[str] = Field(default_factory=list)
    models: list[str] = Field(default_factory=list)
    deterministic: DeterministicScore | None = None
    l6: L6CaseScore | None = None
    human_review: HumanReview | None = None
    usage: RunUsage = Field(default_factory=RunUsage)
    termination_reason: str | None = None
    transcript_path: str | None = None


class AgentMetadata(StrictModel):
    name: str
    model: str = "offline"
    provider: str = "fixture"


class EvalReport(StrictModel):
    schema_version: int = 1
    task: str = "EVAL-001"
    status: (
        Literal["PASS", "FAIL", "ERROR", "SKIP", "UNSUPPORTED", "UNGRADED", "NOT_RUN"]
        | None
    ) = None
    dataset_version: str
    dataset_digest: str = ""
    config_name: str
    code_revision: str
    agent: AgentMetadata
    started_at: datetime = Field(default_factory=utc_now)
    completed_at: datetime | None = None
    cases: list[CaseResult] = Field(default_factory=list)
    aggregates: dict[str, float | None] = Field(default_factory=dict)
    review_queue: list[ReviewQueueEntry] = Field(default_factory=list)
    run_index: list[RunIndexEntry] = Field(default_factory=list)
    prompt_version: str = ""
    environment: dict[str, str] = Field(default_factory=dict)
    gate_failures: list[str] = Field(default_factory=list)
    baseline_failures: list[str] = Field(default_factory=list)
    baseline_comparison: dict[str, Any] | None = None
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

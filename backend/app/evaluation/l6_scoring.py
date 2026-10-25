"""L6 functional-correctness scoring over the deterministic contract.

The L6 score is derived from the existing deterministic dimensions plus one
outcome classification. Provider and execution failures are recorded with an
outcome but no functional scores, so they never enter the functional
denominator. Answer quality remains a separate Judge contract.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Sequence

from app.evaluation.types import (
    CaseResult,
    DeterministicScore,
    EvalCase,
    ExecutionResult,
    L6CaseScore,
    L6Outcome,
)

L6_DIMENSIONS = (
    "task_success",
    "tool_selection",
    "arguments",
    "evidence",
    "termination",
    "recovery",
    "steps",
)

L6_METRICS = {
    "task_success": "l6_task_success_rate",
    "tool_selection": "l6_tool_selection_accuracy",
    "arguments": "l6_argument_accuracy",
    "evidence": "l6_evidence_accuracy",
    "termination": "l6_termination_accuracy",
    "recovery": "l6_recovery_accuracy",
    "steps": "l6_step_determinism_rate",
}

L6_COUNT_METRICS = (
    "l6_case_count",
    "l6_functional_case_count",
    "l6_provider_error_count",
    "l6_execution_error_count",
    "l6_cancelled_count",
    "l6_provider_error_rate",
    "l6_execution_error_rate",
    "l6_functional_pass_rate",
    *L6_METRICS.values(),
)

_PROVIDER_ERROR_CODES = frozenset({"provider_error"})
_EXECUTION_ERROR_CODES = frozenset({"permanent"})


def _empty_score(
    case_id: str,
    outcome: L6Outcome,
    *,
    terminal_error_code: str | None = None,
) -> L6CaseScore:
    return L6CaseScore(
        case_id=case_id,
        outcome=outcome,
        terminal_error_code=terminal_error_code,
    )


def _dimension_score(
    deterministic: DeterministicScore,
    names: Sequence[str],
) -> float:
    by_name = {dimension.dimension: dimension for dimension in deterministic.dimensions}
    selected = [by_name[name] for name in names if name in by_name]
    if not selected:
        return 0.0
    return sum(dimension.score for dimension in selected) / len(selected)


def _functional_scores(
    deterministic: DeterministicScore,
    *,
    functional_success: bool,
) -> dict[str, float]:
    by_name = {dimension.dimension: dimension for dimension in deterministic.dimensions}
    tool_selection = (
        1.0
        if (
            by_name.get("required_tools") is not None
            and by_name["required_tools"].passed
            and by_name.get("forbidden_tools") is not None
            and by_name["forbidden_tools"].passed
        )
        else 0.0
    )
    return {
        "task_success": 1.0 if functional_success else 0.0,
        "tool_selection": tool_selection,
        "arguments": _dimension_score(deterministic, ["arguments"]),
        "evidence": _dimension_score(deterministic, ["evidence"]),
        "termination": _dimension_score(deterministic, ["termination"]),
        "recovery": _dimension_score(deterministic, ["recovery"]),
        "steps": _dimension_score(deterministic, ["steps"]),
    }


def score_l6_case(
    case: EvalCase,
    result: ExecutionResult,
    deterministic: DeterministicScore | None,
    *,
    passed: bool,
) -> L6CaseScore:
    """Classify one result and score only functionally evaluated cases.

    A case that meets its deterministic contract is ``passed`` even when the
    contract expects a failed/cancelled terminal state. Provider errors are
    classified only after that check, so an expected provider failure can still
    satisfy its contract; unexpected provider failures never become functional
    failures.
    """
    if result.artifact_error:
        return _empty_score(case.id, "execution_error")
    functional_success = (
        deterministic.task_success if deterministic is not None else passed
    )
    if functional_success:
        return L6CaseScore(
            case_id=case.id,
            outcome="passed",
            task_success=True,
            scores=(
                _functional_scores(deterministic, functional_success=True)
                if deterministic is not None
                else {}
            ),
            dimensions=(
                list(deterministic.dimensions) if deterministic is not None else []
            ),
        )
    if result.run_status == "cancelled" or result.terminal_error_code == "cancelled":
        return _empty_score(
            case.id,
            "cancelled",
            terminal_error_code=result.terminal_error_code or "cancelled",
        )
    if (
        result.run_status == "timeout"
        or result.terminal_error_code in _PROVIDER_ERROR_CODES
    ):
        return _empty_score(
            case.id,
            "provider_error",
            terminal_error_code=result.terminal_error_code or "provider_error",
        )
    if result.terminal_error_code in _EXECUTION_ERROR_CODES:
        return _empty_score(
            case.id,
            "execution_error",
            terminal_error_code=result.terminal_error_code,
        )
    return L6CaseScore(
        case_id=case.id,
        outcome="functional_failure",
        task_success=False,
        scores=(
            _functional_scores(deterministic, functional_success=False)
            if deterministic is not None
            else {}
        ),
        dimensions=(
            list(deterministic.dimensions) if deterministic is not None else []
        ),
    )


def l6_execution_error(case_id: str) -> L6CaseScore:
    """Build the score for an exception or artifact failure."""
    return _empty_score(case_id, "execution_error")


def aggregate_l6_scores(cases: Sequence[CaseResult]) -> dict[str, float]:
    """Aggregate L6 metrics; provider/execution failures stay outside the denominator."""
    total = len(cases)
    outcomes = Counter(case.outcome for case in cases if case.outcome is not None)
    functional = [
        case for case in cases if case.outcome in {"passed", "functional_failure"}
    ]
    functional_passed = sum(1 for case in functional if case.outcome == "passed")
    aggregates: dict[str, float] = {
        "l6_case_count": float(total),
        "l6_functional_case_count": float(len(functional)),
        "l6_provider_error_count": float(outcomes["provider_error"]),
        "l6_execution_error_count": float(outcomes["execution_error"]),
        "l6_cancelled_count": float(outcomes["cancelled"]),
        "l6_provider_error_rate": (
            outcomes["provider_error"] / total if total else 0.0
        ),
        "l6_execution_error_rate": (
            outcomes["execution_error"] / total if total else 0.0
        ),
    }
    if not functional:
        return aggregates
    aggregates["l6_functional_pass_rate"] = functional_passed / len(functional)
    for dimension, metric in L6_METRICS.items():
        values = [
            case.l6.scores[dimension]
            for case in functional
            if case.l6 is not None and dimension in case.l6.scores
        ]
        if values:
            aggregates[metric] = sum(values) / len(values)
    return aggregates

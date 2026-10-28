"""L6 functional-correctness scoring and provider-error separation."""

from __future__ import annotations

from typing import Any

import pytest

from app.evaluation.l6_scoring import (
    aggregate_l6_scores,
    l6_execution_error,
    score_l6_case,
)
from app.evaluation.scoring import score_deterministic
from app.evaluation.types import CaseResult, EvalCase, ExecutionResult


def _case(
    case_id: str = "l6-case",
    *,
    required: tuple[str, ...] = ("tool",),
    termination: str = "completed",
    error_code: str | None = None,
    min_steps: int = 1,
    max_steps: int = 2,
) -> EvalCase:
    return EvalCase.model_validate(
        {
            "id": case_id,
            "category": "routing",
            "input_messages": [{"role": "user", "content": "run the case"}],
            "user_fixture": {"user_id": 980},
            "assertions": {"max_latency_ms": 1000, "max_calls": 2},
            "fixtures": {"events": [{"type": "message_chunk", "content": "fixture"}]},
            "deterministic": {
                "schema_version": 1,
                "tools": {"required": list(required), "forbidden": []},
                "termination": {
                    "status": termination,
                    "error_code": error_code,
                },
                "steps": {"min_steps": min_steps, "max_steps": max_steps},
                "tool_errors": {"max_failures": 0},
            },
        }
    )


def _result(**overrides: Any) -> ExecutionResult:
    values: dict[str, Any] = {
        "route": "chat",
        "capabilities": ["tool"],
        "text": "answer",
        "schema_valid": True,
        "run_status": "completed",
        "step_count": 2,
        "tool_call_count": 1,
        "tool_success_count": 1,
        "tool_failure_count": 0,
    }
    values.update(overrides)
    return ExecutionResult(**values)


def _score(case: EvalCase, result: ExecutionResult):
    deterministic = score_deterministic(case, result)
    passed = deterministic is not None and deterministic.task_success
    return score_l6_case(case, result, deterministic, passed=passed), deterministic


def test_passed_case_scores_every_dimension() -> None:
    case = _case()
    l6, deterministic = _score(case, _result())

    assert deterministic is not None and deterministic.task_success
    assert l6.outcome == "passed"
    assert l6.task_success is True
    assert l6.scores == {
        "task_success": 1.0,
        "tool_selection": 1.0,
        "arguments": 1.0,
        "evidence": 1.0,
        "termination": 1.0,
        "recovery": 1.0,
        "steps": 1.0,
    }
    assert l6.dimensions


def test_functional_failure_is_scored_not_misclassified() -> None:
    case = _case()
    l6, deterministic = _score(case, _result(capabilities=[]))

    assert deterministic is not None and not deterministic.task_success
    assert l6.outcome == "functional_failure"
    assert l6.task_success is False
    assert l6.scores["task_success"] == 0.0
    assert l6.scores["tool_selection"] == 0.0
    assert l6.scores["termination"] == 1.0
    assert l6.scores["steps"] == 1.0


def test_provider_error_has_no_functional_scores() -> None:
    case = _case()
    l6, _ = _score(
        case,
        _result(
            capabilities=[],
            run_status="failed",
            terminal_error_code="provider_error",
        ),
    )

    assert l6.outcome == "provider_error"
    assert l6.terminal_error_code == "provider_error"
    assert l6.task_success is None
    assert l6.scores == {}
    assert l6.dimensions == []


def test_unexpected_failed_runtime_is_an_execution_error() -> None:
    case = _case()
    l6, deterministic = _score(
        case,
        _result(
            capabilities=[],
            run_status="failed",
            terminal_error_code="tool_error",
        ),
    )

    assert deterministic is not None and not deterministic.task_success
    assert l6.outcome == "execution_error"
    assert l6.task_success is None
    assert l6.scores == {}


def test_timeout_is_provider_error() -> None:
    case = _case()
    l6, _ = _score(
        case,
        _result(run_status="timeout", terminal_error_code="timeout"),
    )

    assert l6.outcome == "provider_error"
    assert l6.terminal_error_code == "timeout"


def test_unexpected_cancellation_is_separate() -> None:
    case = _case()
    l6, _ = _score(
        case,
        _result(run_status="cancelled", terminal_error_code="cancelled"),
    )

    assert l6.outcome == "cancelled"
    assert l6.scores == {}


def test_expected_provider_failure_can_satisfy_the_contract() -> None:
    case = _case(required=(), termination="failed", error_code="provider_error")
    l6, deterministic = _score(
        case,
        _result(
            capabilities=[],
            run_status="failed",
            terminal_error_code="provider_error",
        ),
    )

    assert deterministic is not None and deterministic.task_success
    assert l6.outcome == "passed"
    assert l6.task_success is True


def test_artifact_error_is_execution_error() -> None:
    case = _case()
    l6, _ = _score(
        case,
        _result(artifact_error="transcript_export_failed"),
    )

    assert l6.outcome == "execution_error"
    assert l6.scores == {}


def test_execution_error_helper() -> None:
    l6 = l6_execution_error("broken")

    assert l6.outcome == "execution_error"
    assert l6.scores == {}
    assert l6.task_success is None


def test_provider_errors_are_excluded_from_functional_aggregates() -> None:
    functional_case = _case("functional")
    functional_result = _result(capabilities=[])
    functional_l6 = score_l6_case(
        functional_case,
        functional_result,
        score_deterministic(functional_case, functional_result),
        passed=False,
    )
    provider_case = _case("provider")
    provider_result = _result(
        run_status="failed",
        terminal_error_code="provider_error",
    )
    provider_l6 = score_l6_case(
        provider_case,
        provider_result,
        score_deterministic(provider_case, provider_result),
        passed=False,
    )
    cases = [
        CaseResult(
            case_id="functional",
            category="routing",
            passed=False,
            outcome=functional_l6.outcome,
            l6=functional_l6,
        ),
        CaseResult(
            case_id="provider",
            category="routing",
            passed=False,
            outcome=provider_l6.outcome,
            terminal_error_code="provider_error",
            l6=provider_l6,
        ),
    ]

    aggregates = aggregate_l6_scores(cases)

    assert aggregates["l6_case_count"] == 2
    assert aggregates["l6_functional_case_count"] == 1
    assert aggregates["l6_provider_error_count"] == 1
    assert aggregates["l6_provider_error_rate"] == 0.5
    assert aggregates["l6_functional_pass_rate"] == 0.0
    assert aggregates["l6_task_success_rate"] == 0.0
    assert aggregates["l6_termination_accuracy"] == 1.0
    assert "l6_provider_error_accuracy" not in aggregates


@pytest.mark.parametrize("run_status", ["failed", "timeout", "cancelled"])
def test_non_completed_status_never_enters_functional_denominator(
    run_status: str,
) -> None:
    case = _case()
    result = _result(
        capabilities=[],
        run_status=run_status,
        terminal_error_code=(
            "provider_error" if run_status == "failed" else run_status
        ),
    )
    l6, _ = _score(case, result)
    case_result = CaseResult(
        case_id=case.id,
        category="routing",
        passed=False,
        outcome=l6.outcome,
        l6=l6,
    )

    aggregates = aggregate_l6_scores([case_result])

    assert aggregates["l6_functional_case_count"] == 0
    assert "l6_functional_pass_rate" not in aggregates

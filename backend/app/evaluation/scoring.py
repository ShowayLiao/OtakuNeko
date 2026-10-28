"""Deterministic case scoring contract.

The deterministic verdict is a pure function of one ``EvalCase`` spec and one
normalized ``ExecutionResult``. It never reads a Judge, wall-clock time, random
state or provider payload. Answer quality is a separate contract: only
``answer_quality_passed`` consults a Judge outcome, and its result can never
change ``DeterministicScore.task_success``.
"""

from __future__ import annotations

import json
from typing import Any

from app.evaluation.types import (
    AnswerQualitySpec,
    DeterministicCaseSpec,
    DeterministicScore,
    DimensionScore,
    EvalCase,
    ExecutionResult,
    JudgeOutcome,
)

DETERMINISTIC_DIMENSIONS = (
    "termination",
    "required_tools",
    "forbidden_tools",
    "arguments",
    "evidence",
    "recovery",
    "steps",
    "tool_errors",
)


def _dimension(name: str, passed: bool, detail: str) -> DimensionScore:
    return DimensionScore(
        dimension=name,
        passed=passed,
        score=1.0 if passed else 0.0,
        detail=detail,
    )


def _score_termination(
    spec: DeterministicCaseSpec, result: ExecutionResult
) -> DimensionScore:
    expected = spec.termination
    failures: list[str] = []
    if result.run_status != expected.status:
        failures.append(f"status expected={expected.status} actual={result.run_status}")
    if expected.error_code is not None and result.terminal_error_code != (
        expected.error_code
    ):
        failures.append(
            f"error_code expected={expected.error_code} "
            f"actual={result.terminal_error_code}"
        )
    if expected.termination_reason is not None and result.termination_reason != (
        expected.termination_reason
    ):
        failures.append(
            f"termination_reason expected={expected.termination_reason} "
            f"actual={result.termination_reason}"
        )
    return _dimension(
        "termination",
        not failures,
        "; ".join(failures) or f"status={result.run_status}",
    )


def _score_required_tools(
    spec: DeterministicCaseSpec, result: ExecutionResult
) -> DimensionScore:
    required = spec.tools.required
    missing = sorted(set(required) - set(result.capabilities))
    return _dimension(
        "required_tools",
        not missing,
        f"required={required} missing={missing}",
    )


def _score_forbidden_tools(
    spec: DeterministicCaseSpec, result: ExecutionResult
) -> DimensionScore:
    forbidden = spec.tools.forbidden
    invoked = sorted(set(forbidden) & set(result.capabilities))
    return _dimension(
        "forbidden_tools",
        not invoked,
        f"forbidden={forbidden} invoked={invoked}",
    )


def _score_arguments(
    spec: DeterministicCaseSpec, result: ExecutionResult
) -> DimensionScore:
    expected = spec.arguments
    observed = set(result.tool_argument_keys)
    missing = sorted(set(expected.required_keys) - observed)
    forbidden = sorted(set(expected.forbidden_keys) & observed)
    invocation_failures: list[str] = []
    if expected.invocations is not None:
        actual = result.tool_arguments
        if len(actual) != len(expected.invocations):
            invocation_failures.append(
                f"execution count expected={len(expected.invocations)} actual={len(actual)}"
            )
        for index, (wanted, sample) in enumerate(zip(expected.invocations, actual)):
            if wanted.capability != sample.capability:
                invocation_failures.append(
                    f"execution {index + 1}: capability mismatch"
                )
            if wanted.arguments_digest != sample.arguments_digest:
                invocation_failures.append(
                    f"execution {index + 1}: argument values mismatch"
                )
    passed = not missing and not forbidden and not invocation_failures
    return _dimension(
        "arguments",
        passed,
        f"required={expected.required_keys} missing={missing} "
        f"forbidden={expected.forbidden_keys} observed={forbidden} "
        f"executions={invocation_failures}",
    )


def _score_evidence(
    spec: DeterministicCaseSpec, result: ExecutionResult
) -> DimensionScore:
    expected = spec.evidence
    observed = set(result.evidence)
    missing = sorted(set(expected.required) - observed)
    forbidden = sorted(set(expected.forbidden) & observed)
    # A marker in tool output proves retrieval; a bracketed marker in the
    # answer proves citation. Both are required for grounded citation coverage.
    missing_citations = [
        marker
        for marker in expected.required_citations
        if marker not in observed or f"[{marker}]" not in result.text
    ]
    passed = not missing and not forbidden and not missing_citations
    return _dimension(
        "evidence",
        passed,
        f"required={expected.required} missing={missing} "
        f"forbidden={expected.forbidden} observed={forbidden} "
        f"missing_citations={missing_citations}",
    )


def _score_recovery(
    spec: DeterministicCaseSpec, result: ExecutionResult
) -> DimensionScore:
    required = spec.recovery.required
    passed = not required or result.recovered
    return _dimension(
        "recovery",
        passed,
        f"required={required} recovered={result.recovered}",
    )


def _score_steps(
    spec: DeterministicCaseSpec, result: ExecutionResult
) -> DimensionScore:
    expected = spec.steps
    passed = expected.min_steps <= result.step_count <= expected.max_steps
    return _dimension(
        "steps",
        passed,
        f"actual={result.step_count} min={expected.min_steps} max={expected.max_steps}",
    )


def _score_tool_errors(
    spec: DeterministicCaseSpec, result: ExecutionResult
) -> DimensionScore:
    expected = spec.tool_errors
    observed = {
        error.error_code for error in result.tool_errors if error.error_code is not None
    }
    failures: list[str] = []
    if result.tool_failure_count > expected.max_failures:
        failures.append(
            f"failures={result.tool_failure_count} max={expected.max_failures}"
        )
    disallowed = sorted(observed - set(expected.allowed_error_codes))
    if disallowed:
        failures.append(f"disallowed={disallowed}")
    missing = sorted(set(expected.required_error_codes) - observed)
    if missing:
        failures.append(f"missing={missing}")
    return _dimension(
        "tool_errors",
        not failures,
        "; ".join(failures)
        or f"failures={result.tool_failure_count} observed={sorted(observed)}",
    )


_DIMENSION_SCORERS = {
    "termination": _score_termination,
    "required_tools": _score_required_tools,
    "forbidden_tools": _score_forbidden_tools,
    "arguments": _score_arguments,
    "evidence": _score_evidence,
    "recovery": _score_recovery,
    "steps": _score_steps,
    "tool_errors": _score_tool_errors,
}


def _unique_json_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise ValueError("duplicate JSON key")
        value[key] = item
    return value


def _score_final_answer(
    spec: DeterministicCaseSpec, result: ExecutionResult
) -> DimensionScore:
    expected = spec.final_answer
    assert expected is not None
    failures = []
    if any(text not in result.text for text in expected.required_text):
        failures.append("required final text missing")
    if any(text in result.text for text in expected.forbidden_text):
        failures.append("forbidden final text present")
    if expected.expected_json is not None:
        try:
            actual = json.loads(result.text, object_pairs_hook=_unique_json_object)
            # Canonical serialized equality keeps bool distinct from int and
            # rejects NaN/Infinity, without retaining the answer in diagnostics.
            actual_json = json.dumps(actual, sort_keys=True, allow_nan=False)
            expected_json = json.dumps(
                expected.expected_json, sort_keys=True, allow_nan=False
            )
            if actual_json != expected_json:
                failures.append("final JSON mismatch")
        except (ValueError, TypeError):
            failures.append("final answer is not valid JSON")
    return _dimension(
        "final_answer", not failures, "; ".join(failures) or "final answer accepted"
    )


def score_deterministic(
    case: EvalCase,
    result: ExecutionResult,
) -> DeterministicScore | None:
    """Score one normalized Runtime result against the case's contract.

    ``task_success`` is the rollup of every deterministic dimension. It is
    ``None`` for cases that do not declare a ``deterministic`` spec, which keeps
    existing published datasets valid without silently inventing expectations.
    """
    spec = case.deterministic
    if spec is None:
        return None
    dimensions = [
        _DIMENSION_SCORERS[name](spec, result) for name in DETERMINISTIC_DIMENSIONS
    ]
    if spec.final_answer is not None:
        dimensions.append(_score_final_answer(spec, result))
    return DeterministicScore(
        case_id=case.id,
        task_success=all(dimension.passed for dimension in dimensions),
        dimensions=dimensions,
    )


def answer_quality_passed(
    spec: AnswerQualitySpec | None,
    outcome: JudgeOutcome,
) -> bool | None:
    """Evaluate the separate answer-quality contract.

    Returns ``None`` when the case declares no quality spec. ``required`` only
    controls whether an unavailable Judge is a failure; an available score below
    ``min_score`` always fails. The result never feeds back into
    ``DeterministicScore``.
    """
    if spec is None:
        return None
    if outcome.status != "available" or outcome.score is None:
        return not spec.required
    return outcome.score >= spec.min_score

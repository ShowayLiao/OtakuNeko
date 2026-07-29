"""Deterministic metrics for EVAL-001."""

from __future__ import annotations

from collections import defaultdict

from app.evaluation.types import EvalCase, ExecutionResult, MetricResult


def _boolean(metric: str, passed: bool, detail: str) -> MetricResult:
    return MetricResult(
        metric=metric,
        value=1.0 if passed else 0.0,
        passed=passed,
        detail=detail,
    )


def compute_case_metrics(
    case: EvalCase,
    result: ExecutionResult,
) -> list[MetricResult]:
    expected_route = case.expected_route.value if case.expected_route else None
    routing_passed = expected_route is None or result.route == expected_route
    missing_capabilities = sorted(
        set(case.required_capabilities) - set(result.capabilities)
    )
    forbidden_capabilities = sorted(
        set(case.forbidden_capabilities) & set(result.capabilities)
    )
    response_lower = result.text.lower()
    forbidden_phrases = [
        phrase
        for phrase in case.forbidden_phrases
        if phrase.lower() in response_lower
    ]
    required_evidence = set(case.assertions.required_evidence)
    present_evidence = required_evidence & set(result.evidence)
    evidence_value = (
        len(present_evidence) / len(required_evidence)
        if required_evidence
        else 1.0
    )
    recovery_passed = (
        not case.assertions.require_recovery or result.recovered
    )
    latency_passed = result.latency_ms <= case.assertions.max_latency_ms
    calls_passed = result.call_count <= case.assertions.max_calls

    return [
        _boolean(
            "routing",
            routing_passed,
            f"expected={expected_route}, actual={result.route}",
        ),
        _boolean(
            "schema_validity",
            result.schema_valid,
            f"schema={case.assertions.response_schema}",
        ),
        _boolean(
            "required_capabilities",
            not missing_capabilities,
            f"missing={missing_capabilities}",
        ),
        _boolean(
            "forbidden_capabilities",
            not forbidden_capabilities,
            f"invoked={forbidden_capabilities}",
        ),
        _boolean(
            "forbidden_phrases",
            not forbidden_phrases,
            f"found={forbidden_phrases}",
        ),
        MetricResult(
            metric="evidence_coverage",
            value=evidence_value,
            passed=evidence_value == 1.0,
            detail=f"required={sorted(required_evidence)}",
        ),
        _boolean(
            "error_recovery",
            recovery_passed,
            f"required={case.assertions.require_recovery}",
        ),
        MetricResult(
            metric="latency",
            value=result.latency_ms,
            passed=latency_passed,
            detail=(
                f"actual_ms={result.latency_ms}, "
                f"max_ms={case.assertions.max_latency_ms}"
            ),
        ),
        MetricResult(
            metric="call_budget",
            value=float(result.call_count),
            passed=calls_passed,
            detail=(
                f"actual={result.call_count}, max={case.assertions.max_calls}"
            ),
        ),
    ]


def case_passed(metrics: list[MetricResult]) -> bool:
    return all(metric.passed for metric in metrics)


def failure_metrics(case: EvalCase) -> list[MetricResult]:
    """Represent an execution exception in every applicable aggregate."""
    metrics = compute_case_metrics(
        case,
        ExecutionResult(
            route="",
            capabilities=[],
            text="",
            evidence=[],
            schema_valid=False,
            recovered=False,
            latency_ms=0,
            call_count=0,
        ),
    )
    for metric in metrics:
        if metric.metric in {"latency", "call_budget"}:
            metric.passed = False
    return metrics


def aggregate_metrics(
    case_metrics: list[list[MetricResult]],
) -> dict[str, float]:
    if not case_metrics:
        return {"pass_rate": 1.0, "routing_accuracy": 1.0, "latency_ms": 0.0}

    values: dict[str, list[float]] = defaultdict(list)
    for metrics in case_metrics:
        for metric in metrics:
            values[metric.metric].append(metric.value)

    aggregates = {
        name: sum(metric_values) / len(metric_values)
        for name, metric_values in values.items()
    }
    aggregates["pass_rate"] = sum(
        1 for metrics in case_metrics if case_passed(metrics)
    ) / len(case_metrics)
    aggregates["routing_accuracy"] = aggregates.get("routing", 1.0)
    aggregates["latency_ms"] = aggregates.get("latency", 0.0)
    aggregates["call_count"] = aggregates.get("call_budget", 0.0)
    return aggregates

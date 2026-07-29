"""Boundary tests for deterministic EVAL-001 metrics."""

from app.evaluation.metrics import aggregate_metrics, compute_case_metrics
from app.evaluation.types import (
    CaseAssertions,
    Category,
    EvalCase,
    ExecutionFixture,
    ExecutionResult,
    ExpectedRoute,
    UserFixture,
)


def _case(**overrides):
    values = {
        "id": "metric-case",
        "category": Category.ANIME_KNOWLEDGE,
        "input_messages": [{"role": "user", "content": "test"}],
        "user_fixture": UserFixture(user_id=1),
        "expected_route": ExpectedRoute.CHAT,
        "required_capabilities": ["search"],
        "forbidden_capabilities": ["delete"],
        "forbidden_phrases": ["secret"],
        "assertions": CaseAssertions(
            response_schema="text",
            required_evidence=["anime:1"],
            require_recovery=True,
            max_latency_ms=100,
            max_calls=2,
        ),
        "fixtures": ExecutionFixture(
            events=[
                {"type": "route", "route": "chat"},
                {"type": "message_chunk", "content": "safe"},
            ],
        ),
        "tags": ["fast"],
    }
    values.update(overrides)
    return EvalCase(**values)


def _result(**overrides):
    values = {
        "route": "chat",
        "capabilities": ["search"],
        "text": "safe",
        "evidence": ["anime:1"],
        "schema_valid": True,
        "recovered": True,
        "latency_ms": 100,
        "call_count": 2,
    }
    values.update(overrides)
    return ExecutionResult(**values)


def test_all_deterministic_metrics_pass_at_budget_boundaries():
    metrics = compute_case_metrics(_case(), _result())

    assert {metric.metric for metric in metrics} == {
        "routing",
        "schema_validity",
        "required_capabilities",
        "forbidden_capabilities",
        "forbidden_phrases",
        "evidence_coverage",
        "error_recovery",
        "latency",
        "call_budget",
    }
    assert all(metric.passed for metric in metrics)


def test_latency_and_call_budget_fail_above_boundary():
    metrics = compute_case_metrics(
        _case(),
        _result(latency_ms=100.01, call_count=3),
    )
    by_name = {metric.metric: metric for metric in metrics}

    assert not by_name["latency"].passed
    assert not by_name["call_budget"].passed


def test_schema_evidence_and_recovery_fail_explicitly():
    metrics = compute_case_metrics(
        _case(),
        _result(schema_valid=False, evidence=[], recovered=False),
    )
    by_name = {metric.metric: metric for metric in metrics}

    assert not by_name["schema_validity"].passed
    assert not by_name["evidence_coverage"].passed
    assert not by_name["error_recovery"].passed


def test_aggregate_metrics_include_pass_rate_and_routing_accuracy():
    metrics = compute_case_metrics(_case(), _result())
    aggregates = aggregate_metrics([metrics])

    assert aggregates["pass_rate"] == 1.0
    assert aggregates["routing_accuracy"] == 1.0
    assert aggregates["latency_ms"] == 100.0

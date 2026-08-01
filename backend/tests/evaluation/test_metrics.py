"""Boundary tests for deterministic EVAL-001 metrics."""

from app.evaluation.metrics import (
    aggregate_metrics,
    aggregate_observability,
    compute_case_metrics,
)
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


def test_aggregate_observability_metrics_cover_run_tool_policy_budget_and_usage():
    results = [
        _result(
            run_status="completed",
            tool_call_count=2,
            tool_success_count=1,
            tool_failure_count=1,
            policy_denied_count=1,
            budget_exceeded_count=0,
            cancelled_count=0,
            reconnect_count=1,
            model_call_count=1,
            model_tokens=12,
            estimated_cost_usd=None,
            latency_ms=100,
        ),
        _result(
            run_status="cancelled",
            tool_call_count=1,
            tool_success_count=0,
            tool_failure_count=1,
            policy_denied_count=0,
            budget_exceeded_count=1,
            cancelled_count=1,
            reconnect_count=0,
            model_call_count=1,
            model_tokens=None,
            estimated_cost_usd=None,
            latency_ms=300,
        ),
    ]

    aggregates = aggregate_observability(results)

    assert aggregates["run_success_rate"] == 0.5
    assert aggregates["tool_success_rate"] == 1 / 3
    assert aggregates["policy_denied_count"] == 1.0
    assert aggregates["budget_exceeded_count"] == 1.0
    assert aggregates["cancelled_count"] == 1.0
    assert aggregates["reconnect_count"] == 1.0
    assert aggregates["model_tokens"] == 12.0
    assert aggregates["estimated_cost_unknown_count"] == 2.0
    assert aggregates["latency_ms"] == 200.0


def test_unknown_cost_counts_each_model_call():
    aggregates = aggregate_observability([
        _result(
            model_call_count=2,
            model_tokens=None,
            estimated_cost_usd=None,
        )
    ])

    assert aggregates["estimated_cost_unknown_count"] == 2.0

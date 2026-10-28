"""Multi-run trend baseline, variance, regression and cost history."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.evaluation import adapter, entrypoint, real_model, trend
from app.evaluation.config import load_config
from app.evaluation.dataset import load_dataset
from app.evaluation.runner import run_evaluation
from app.evaluation.scripted_llm import ScriptedLLM
from app.evaluation.types import (
    AgentMetadata,
    CaseResult,
    EvalReport,
    ExecutionFixture,
    JudgeOutcome,
    L6CaseScore,
    L6Outcome,
    RunUsage,
    ScriptEvent,
)


class _Gateway(ScriptedLLM):
    async def close(self) -> None:
        return None


def _case_result(
    case_id: str,
    *,
    outcome: L6Outcome = "passed",
    latency: float = 10,
    tokens: int | None = 4,
    cost: float | None = None,
    scores: dict[str, float] | None = None,
    step_count: int | None = 1,
    judge_status: str = "not_requested",
    quality_passed: bool | None = None,
    judge_score: float | None = None,
) -> CaseResult:
    return CaseResult(
        case_id=case_id,
        category="routing",
        passed=outcome == "passed",
        outcome=outcome,
        step_count=step_count,
        judge=JudgeOutcome(
            status=judge_status,
            quality_passed=quality_passed,
            score=judge_score,
        ),
        run_id=f"run-{case_id}",
        trace_id=f"trace-{case_id}",
        usage=RunUsage(
            model_calls=2,
            model_tokens=tokens,
            latency_ms=latency,
            estimated_cost_usd=cost,
        ),
        l6=L6CaseScore(
            case_id=case_id,
            outcome=outcome,
            task_success=(outcome == "passed"),
            scores=(
                scores
                if scores is not None
                else {"task_success": 1.0 if outcome == "passed" else 0.0}
            ),
        ),
    )


def _report(
    cases: list[CaseResult],
    *,
    environment: dict[str, str] | None = None,
    dataset_version: str = "v1-real-model",
    dataset_digest: str = "digest",
    code_revision: str = "revision",
    prompt_version: str = "decision-contract-v1",
) -> EvalReport:
    return EvalReport(
        dataset_version=dataset_version,
        dataset_digest=dataset_digest,
        config_name="trend",
        code_revision=code_revision,
        agent=AgentMetadata(
            name="trend",
            model="deepseek-flash",
            provider="deepseek",
        ),
        prompt_version=prompt_version,
        environment=environment or {},
        cases=cases,
    )


def test_expand_repeats_creates_independent_ids() -> None:
    dataset = load_dataset("evals/datasets/v1-real-model.jsonl")
    expanded = trend.expand_repeats(dataset, 2)

    ids = [case.id for case in expanded.cases]
    assert len(ids) == len(dataset.cases) * 2
    assert len(set(ids)) == len(ids)
    assert "real-model-tool-time__r1" in ids
    assert "real-model-tool-time__r2" in ids
    assert all("__r1" in case.id or "__r2" in case.id for case in expanded.cases)
    assert expanded.content_digest == dataset.content_digest


def test_baseline_records_variance_usage_and_provider_errors() -> None:
    results = [
        _case_result("case-a__r1", latency=10, tokens=4, cost=0.01),
        _case_result(
            "case-a__r2",
            outcome="functional_failure",
            latency=20,
            tokens=6,
            cost=0.03,
            scores={"task_success": 0.0},
        ),
        _case_result(
            "case-b__r1",
            outcome="provider_error",
            latency=30,
            tokens=None,
            scores={},
        ),
    ]

    baseline = trend.build_baseline(_report(results), repeats=2)

    case_a = baseline.cases["case-a"]
    assert case_a.runs == 2
    assert case_a.functional_runs == 2
    assert case_a.functional_pass_rate == 0.5
    assert case_a.pass_rate_variance == 0.25
    assert case_a.mean_latency_ms == 15
    assert case_a.mean_tokens == 5
    assert case_a.tokens_stddev == 1
    assert case_a.mean_cost_usd == 0.02
    assert case_a.provider_error_rate == 0
    case_b = baseline.cases["case-b"]
    assert case_b.functional_runs == 0
    assert case_b.functional_pass_rate is None
    assert case_b.pass_rate_variance is None
    assert case_b.provider_error_rate == 1
    assert baseline.totals.functional_pass_rate == 0.5
    assert baseline.totals.provider_error_rate == 1 / 3


def test_functional_rates_are_unknown_when_no_functional_cases_ran() -> None:
    baseline = trend.build_baseline(
        _report(
            [
                _case_result("case-a__r1", outcome="provider_error"),
                _case_result("case-b__r1", outcome="execution_error"),
            ]
        ),
        repeats=1,
    )

    assert baseline.totals.functional_runs == 0
    assert baseline.totals.functional_pass_rate is None
    assert baseline.totals.pass_rate_variance is None
    assert baseline.cases["case-a"].functional_pass_rate is None
    assert baseline.cases["case-a"].pass_rate_variance is None

    same_dataset = trend.build_baseline(
        _report(
            [
                _case_result("case-a__r1", outcome="provider_error"),
                _case_result("case-b__r1", outcome="execution_error"),
            ]
        ),
        repeats=1,
    )
    diff = trend.compare_baseline(
        baseline, same_dataset, tolerance=trend.TrendTolerance()
    )
    assert diff.cost_trend.delta_pass_rate is None
    assert not any("functional_pass_rate" in item for item in diff.regressions)
    assert not any("functional_pass_rate" in item for item in diff.improvements)


def test_failed_only_baseline_does_not_compare_performance_metrics() -> None:
    baseline = trend.build_baseline(
        _report(
            [
                _case_result(
                    "case-a__r1",
                    outcome="provider_error",
                    latency=1,
                    tokens=None,
                    step_count=0,
                )
            ],
            environment={"provider_network_reachability": "reachable"},
        ),
        repeats=1,
    )
    current = trend.build_baseline(
        _report(
            [_case_result("case-a__r1", latency=35, step_count=2)],
            environment={"provider_network_reachability": "reachable"},
        ),
        repeats=1,
    )

    diff = trend.compare_baseline(baseline, current, tolerance=trend.TrendTolerance())

    assert baseline.totals.functional_runs == 0
    assert baseline.totals.mean_steps is None
    assert not any("mean_steps" in item for item in diff.version_failures)
    assert not any("latency" in item for item in diff.regressions)
    assert not any("mean_steps" in item for item in diff.regressions)
    assert diff.cost_trend.delta_latency_pct is None
    assert any("loop_success_rate" in item for item in diff.improvements)
    assert diff.cost_trend.delta_provider_error_rate == -1.0


def test_unrun_report_has_unknown_provider_error_rate() -> None:
    baseline = trend.build_baseline(_report([]), repeats=1)

    assert baseline.totals.runs == 0
    assert baseline.totals.functional_runs == 0
    assert baseline.totals.functional_pass_rate is None
    assert baseline.totals.provider_error_rate is None


def test_environment_prompt_code_and_dataset_diffs_are_recorded() -> None:
    baseline = trend.build_baseline(
        _report(
            [_case_result("case-a__r1")],
            environment={
                "python": "3.11.9",
                "platform": "win32",
                "provider_network_reachability": "reachable",
                "api_key": "must-not-be-persisted",
            },
        ),
        repeats=1,
    )
    current = trend.build_baseline(
        _report(
            [_case_result("case-a__r1", outcome="functional_failure")],
            environment={
                "python": "3.12.1",
                "platform": "win32",
                "provider_network_reachability": "blocked",
            },
            dataset_version="v2-real-model",
            dataset_digest="digest-v2",
            code_revision="revision-v2",
            prompt_version="decision-contract-v2",
        ),
        repeats=1,
    )

    diff = trend.compare_baseline(baseline, current, tolerance=trend.TrendTolerance())

    assert baseline.environment == {
        "python": "3.11.9",
        "platform": "win32",
        "provider_network_reachability": "reachable",
    }
    assert current.environment == {
        "python": "3.12.1",
        "platform": "win32",
        "provider_network_reachability": "blocked",
    }
    assert any("environment.python" in item for item in diff.provenance_changes)
    assert any("prompt_version" in item for item in diff.provenance_changes)
    assert any("code_revision" in item for item in diff.provenance_changes)
    assert any("dataset_version" in item for item in diff.provenance_changes)
    assert any("dataset_digest" in item for item in diff.provenance_changes)
    assert any(
        "provider_network_reachability" in item for item in diff.provenance_changes
    )
    assert not diff.comparison_compatible
    assert diff.regressions == []
    assert diff.improvements == []


def test_auto_selector_uses_latest_executed_baseline_for_exact_dataset() -> None:
    current = trend.build_baseline(_report([_case_result("case-a__r1")]), repeats=1)
    older = current.model_copy(
        update={"created_at": current.created_at.replace(year=2025)}
    )
    newer = current.model_copy(
        update={"created_at": current.created_at.replace(year=2026)}
    )
    wrong_digest = current.model_copy(update={"dataset_digest": "other-digest"})
    wrong_version = current.model_copy(update={"dataset_version": "other-version"})
    no_execution = current.model_copy(update={"executed_runs": 0})

    selected = trend.select_compatible_baseline(
        [
            (Path("old.json"), older),
            (Path("new.json"), newer),
            (Path("wrong-digest.json"), wrong_digest),
            (Path("wrong-version.json"), wrong_version),
            (Path("not-executed.json"), no_execution),
        ],
        current,
    )

    assert selected == (Path("new.json"), newer)


def test_auto_selector_skips_provider_reachability_mismatch() -> None:
    current = trend.build_baseline(
        _report(
            [_case_result("case-a__r1")],
            environment={"provider_network_reachability": "reachable"},
        ),
        repeats=1,
    )
    blocked = current.model_copy(
        update={
            "created_at": current.created_at.replace(year=2026),
            "environment": {"provider_network_reachability": "blocked"},
        }
    )
    older_reachable = current.model_copy(
        update={
            "created_at": current.created_at.replace(year=2025),
        }
    )

    selected = trend.select_compatible_baseline(
        [(Path("blocked.json"), blocked), (Path("reachable.json"), older_reachable)],
        current,
    )

    assert selected == (Path("reachable.json"), older_reachable)


def test_compare_blocks_provider_reachability_mismatch() -> None:
    baseline = trend.build_baseline(
        _report(
            [
                _case_result(
                    "case-a__r1",
                    outcome="provider_error",
                    latency=1,
                    step_count=0,
                    tokens=None,
                )
            ],
            environment={"provider_network_reachability": "blocked"},
        ),
        repeats=1,
    )
    current = trend.build_baseline(
        _report(
            [_case_result("case-a__r1", latency=35, step_count=2)],
            environment={"provider_network_reachability": "reachable"},
        ),
        repeats=1,
    )

    diff = trend.compare_baseline(baseline, current, tolerance=trend.TrendTolerance())

    assert not diff.comparison_compatible
    assert any(
        "provider_network_reachability" in item for item in diff.provenance_changes
    )
    assert any(
        "provider_network_reachability" in item for item in diff.comparison_blockers
    )
    assert diff.regressions == []
    assert diff.improvements == []


def test_auto_selector_returns_none_without_compatible_history() -> None:
    current = trend.build_baseline(_report([_case_result("case-a__r1")]), repeats=1)
    incompatible = current.model_copy(update={"dataset_digest": "different"})

    assert (
        trend.select_compatible_baseline(
            [(Path("different-dataset.json"), incompatible)], current
        )
        is None
    )


def test_schema_two_baseline_is_parseable_but_never_reused() -> None:
    current = trend.build_baseline(_report([_case_result("case-a__r1")]), repeats=1)
    schema_two_payload = current.model_dump(mode="json")
    schema_two_payload["schema_version"] = 2
    schema_two_payload["totals"]["functional_runs"] = 0
    schema_two_payload["totals"]["functional_pass_rate"] = 0.0
    schema_two_payload["totals"]["pass_rate_variance"] = 0.0
    schema_two_payload["cases"]["case-a"]["functional_runs"] = 0
    schema_two_payload["cases"]["case-a"]["functional_pass_rate"] = 0.0
    schema_two_payload["cases"]["case-a"]["pass_rate_variance"] = 0.0

    schema_two = trend.TrendBaseline.model_validate(schema_two_payload)
    diff = trend.compare_baseline(schema_two, current, tolerance=trend.TrendTolerance())
    selected = trend.select_compatible_baseline(
        [(Path("schema-two.json"), schema_two)], current
    )

    assert schema_two.schema_version == 2
    assert not diff.comparison_compatible
    assert diff.regressions == []
    assert diff.improvements == []
    assert diff.cost_trend.delta_pass_rate is None
    assert any("schema_version=2" in failure for failure in diff.version_failures)
    assert selected is None


def test_baseline_records_loop_errors_steps_and_judge_quality_coverage() -> None:
    results = [
        _case_result(
            "case-a__r1",
            step_count=2,
            judge_status="available",
            quality_passed=True,
            judge_score=0.8,
        ),
        _case_result(
            "case-a__r2",
            outcome="functional_failure",
            step_count=4,
            judge_status="available",
            quality_passed=False,
            judge_score=0.4,
        ),
        _case_result("case-a__r3", outcome="execution_error", step_count=6),
        _case_result("case-a__r4", outcome="cancelled", step_count=None),
        _case_result("case-a__r5", outcome="provider_error", step_count=8),
    ]

    baseline = trend.build_baseline(_report(results), repeats=5)

    case = baseline.cases["case-a"]
    assert baseline.schema_version == 3
    assert case.successful_runs == 1
    assert case.loop_success_rate == 0.2
    assert case.loop_success_variance == pytest.approx(0.16)
    assert case.functional_pass_rate == 0.5
    assert case.provider_error_rate == 0.2
    assert case.execution_error_rate == 0.2
    assert case.cancelled_rate == 0.2
    assert case.mean_steps == 5
    assert case.steps_stddev == pytest.approx(2.2360679775)
    assert case.quality_runs == 2
    assert case.quality_pass_rate == 0.5
    assert case.mean_quality_score == pytest.approx(0.6)

    assert baseline.totals.successful_runs == 1
    assert baseline.totals.loop_success_rate == 0.2
    assert baseline.totals.loop_success_variance == pytest.approx(0.16)
    assert baseline.totals.execution_error_rate == 0.2
    assert baseline.totals.cancelled_rate == 0.2
    assert baseline.totals.mean_steps == 5
    assert baseline.totals.steps_stddev == pytest.approx(2.2360679775)
    assert baseline.totals.quality_runs == 2
    assert baseline.totals.quality_pass_rate == 0.5
    assert baseline.totals.mean_quality_score == pytest.approx(0.6)


def test_schema_one_baseline_keeps_new_metrics_unknown_and_requires_upgrade() -> None:
    current = trend.build_baseline(_report([_case_result("case-a__r1")]), repeats=1)
    legacy_payload = current.model_dump(mode="json")
    legacy_payload["schema_version"] = 1
    new_fields = {
        "successful_runs",
        "loop_success_rate",
        "loop_success_variance",
        "execution_error_rate",
        "cancelled_rate",
        "mean_steps",
        "steps_stddev",
        "quality_runs",
        "quality_pass_rate",
        "mean_quality_score",
        "router_version",
        "router_enabled",
    }
    for case in legacy_payload["cases"].values():
        for field in new_fields:
            case.pop(field, None)
    for field in new_fields | {"steps_stddev"}:
        legacy_payload["totals"].pop(field, None)
    legacy_payload.pop("router_version", None)
    legacy_payload.pop("router_enabled", None)

    legacy = trend.TrendBaseline.model_validate(legacy_payload)

    assert legacy.cases["case-a"].successful_runs is None
    assert legacy.cases["case-a"].loop_success_rate is None
    assert legacy.cases["case-a"].loop_success_variance is None
    assert legacy.cases["case-a"].execution_error_rate is None
    assert legacy.cases["case-a"].quality_runs is None
    assert legacy.router_version is None
    assert legacy.router_enabled is None
    diff = trend.compare_baseline(legacy, current, tolerance=trend.TrendTolerance())
    assert any("schema_version" in item for item in diff.version_failures)
    assert any("loop_success_rate" in item for item in diff.version_failures)
    assert any("execution_error_rate" in item for item in diff.version_failures)


def test_router_provenance_is_recorded_without_becoming_version_drift() -> None:
    baseline = trend.build_baseline(
        _report(
            [_case_result("case-a__r1")],
            environment={"router_version": "router-v1", "router_enabled": "true"},
        ),
        repeats=1,
    )
    current = trend.build_baseline(
        _report(
            [_case_result("case-a__r1")],
            environment={"router_version": "router-v2", "router_enabled": "false"},
        ),
        repeats=1,
    )

    diff = trend.compare_baseline(baseline, current, tolerance=trend.TrendTolerance())

    assert baseline.router_version == "router-v1"
    assert baseline.router_enabled is True
    assert current.router_version == "router-v2"
    assert current.router_enabled is False
    assert not any("router_version" in item for item in diff.version_failures)
    assert not any("router_enabled" in item for item in diff.version_failures)
    assert any("router_version" in item for item in diff.provenance_changes)


def test_compare_detects_loop_error_quality_and_step_regressions() -> None:
    baseline = trend.build_baseline(
        _report(
            [
                _case_result(
                    "case-a__r1",
                    step_count=2,
                    judge_status="available",
                    quality_passed=True,
                    judge_score=0.9,
                ),
                _case_result("case-a__r2", step_count=2),
                _case_result("case-a__r3", step_count=2),
                _case_result("case-a__r4", step_count=2),
            ]
        ),
        repeats=4,
    )
    current = trend.build_baseline(
        _report(
            [
                _case_result(
                    "case-a__r1",
                    step_count=4,
                    judge_status="available",
                    quality_passed=False,
                    judge_score=0.5,
                ),
                _case_result("case-a__r2", outcome="execution_error", step_count=4),
                _case_result("case-a__r3", outcome="cancelled", step_count=4),
                _case_result("case-a__r4", outcome="provider_error", step_count=4),
            ]
        ),
        repeats=4,
    )

    diff = trend.compare_baseline(baseline, current, tolerance=trend.TrendTolerance())

    assert current.cases["case-a"].functional_pass_rate == 1
    assert current.cases["case-a"].loop_success_rate == 0.25
    assert any("loop_success_rate" in item for item in diff.regressions)
    assert any("execution_error_rate" in item for item in diff.regressions)
    assert any("cancelled_rate" in item for item in diff.regressions)
    assert any("provider_error_rate" in item for item in diff.regressions)
    assert any("quality_pass_rate" in item for item in diff.regressions)
    assert any("mean_quality_score" in item for item in diff.regressions)
    assert any("mean_steps" in item for item in diff.regressions)
    assert any("totals: provider_error_rate" in item for item in diff.regressions)
    assert any("totals: execution_error_rate" in item for item in diff.regressions)
    assert any("totals: cancelled_rate" in item for item in diff.regressions)
    assert diff.quality_coverage["case-a"] == {
        "baseline_quality_runs": 1,
        "current_quality_runs": 1,
    }


def test_compare_detects_weighted_totals_loop_drop_below_each_case_tolerance() -> None:
    baseline_results = [_case_result(f"case-a__r{index}") for index in range(1, 10)] + [
        _case_result("case-b__r1", outcome="functional_failure")
    ]
    current_results = [
        _case_result(
            f"case-a__r{index}",
            outcome="functional_failure" if index == 20 else "passed",
        )
        for index in range(1, 21)
    ] + [
        _case_result(f"case-b__r{index}", outcome="functional_failure")
        for index in range(1, 91)
    ]
    baseline = trend.build_baseline(_report(baseline_results), repeats=1)
    current = trend.build_baseline(_report(current_results), repeats=1)

    diff = trend.compare_baseline(baseline, current, tolerance=trend.TrendTolerance())

    assert baseline.cases["case-a"].loop_success_rate == 1
    assert current.cases["case-a"].loop_success_rate == pytest.approx(0.95)
    assert current.cases["case-b"].loop_success_rate == 0
    assert not any(
        item.startswith("case-a: loop_success_rate") for item in diff.regressions
    )
    assert any("totals: loop_success_rate" in item for item in diff.regressions)


def test_compare_skips_quality_without_two_sided_coverage_and_reports_counts() -> None:
    baseline = trend.build_baseline(
        _report(
            [
                _case_result(
                    "case-a__r1",
                    judge_status="available",
                    quality_passed=True,
                    judge_score=1.0,
                )
            ]
        ),
        repeats=1,
    )
    current = trend.build_baseline(_report([_case_result("case-a__r1")]), repeats=1)

    diff = trend.compare_baseline(baseline, current, tolerance=trend.TrendTolerance())

    assert not diff.version_failures
    assert not any("quality_pass_rate" in item for item in diff.regressions)
    assert not any("mean_quality_score" in item for item in diff.regressions)
    assert diff.quality_coverage["case-a"] == {
        "baseline_quality_runs": 1,
        "current_quality_runs": 0,
    }


def test_step_increase_tolerance_defaults_to_fifty_percent() -> None:
    assert trend.TrendTolerance().max_step_increase_pct == 0.5


def test_compare_detects_regressions_and_version_drift() -> None:
    baseline = trend.build_baseline(
        _report(
            [
                _case_result(
                    "case-a__r1",
                    latency=10,
                    tokens=4,
                    cost=0.01,
                    scores={"task_success": 1.0},
                )
            ]
        ),
        repeats=1,
    )
    current = trend.build_baseline(
        _report(
            [
                _case_result(
                    "case-a__r1",
                    outcome="functional_failure",
                    latency=40,
                    tokens=10,
                    cost=0.05,
                    scores={"task_success": 0.5},
                )
            ]
        ),
        repeats=1,
    )

    diff = trend.compare_baseline(baseline, current, tolerance=trend.TrendTolerance())

    assert not diff.version_failures
    assert any("functional_pass_rate" in item for item in diff.regressions)
    assert any("latency" in item for item in diff.regressions)
    assert any("tokens" in item for item in diff.regressions)
    assert any("cost" in item for item in diff.regressions)

    drifted = current.model_copy(update={"repeats": 2, "model": "other"})
    version_diff = trend.compare_baseline(
        baseline, drifted, tolerance=trend.TrendTolerance()
    )
    assert any("repeats" in item for item in version_diff.provenance_changes)
    assert any("model" in item for item in version_diff.provenance_changes)


def test_compare_tracks_added_and_missing_cases() -> None:
    baseline = trend.build_baseline(_report([_case_result("case-a__r1")]), repeats=1)
    current = trend.build_baseline(_report([_case_result("case-b__r1")]), repeats=1)

    diff = trend.compare_baseline(baseline, current, tolerance=trend.TrendTolerance())

    assert diff.added == ["case-b"]
    assert diff.missing == ["case-a"]
    assert any("missing" in item for item in diff.regressions)


def test_history_and_cost_trend() -> None:
    baseline = trend.build_baseline(
        _report(
            [
                _case_result(
                    "case-a__r1",
                    latency=10,
                    tokens=4,
                    cost=0.01,
                )
            ]
        ),
        repeats=1,
    )
    record = trend._history_record("run-1", baseline)
    previous = {
        **record,
        "functional_pass_rate": 0.5,
        "mean_latency_ms": 5,
        "total_tokens": 2,
        "total_cost_usd": 0.005,
    }

    cost = trend.cost_trend(previous, baseline)

    assert cost.delta_pass_rate == 0.5
    assert cost.delta_latency_pct == 1.0
    assert cost.delta_tokens_pct == 1.0
    assert cost.delta_cost_pct == 1.0
    assert trend.cost_trend(None, baseline).delta_latency_pct is None


def _trend_history_pair() -> tuple[trend.TrendBaseline, trend.TrendBaseline]:
    baseline = trend.build_baseline(
        _report(
            [
                _case_result(
                    "case-a__r1",
                    step_count=2,
                    judge_status="available",
                    quality_passed=True,
                    judge_score=0.8,
                ),
                _case_result("case-a__r2", outcome="execution_error", step_count=4),
            ],
            environment={"router_version": "router-v1", "router_enabled": "true"},
        ),
        repeats=2,
    )
    current = trend.build_baseline(
        _report(
            [
                _case_result(
                    "case-a__r1",
                    step_count=4,
                    judge_status="available",
                    quality_passed=False,
                    judge_score=0.4,
                ),
                _case_result("case-a__r2", outcome="cancelled", step_count=2),
            ],
            environment={"router_version": "router-v2", "router_enabled": "false"},
        ),
        repeats=2,
    )
    return baseline, current


def test_schema_two_history_records_trend_metrics_and_provenance() -> None:
    baseline, _ = _trend_history_pair()

    record = trend._history_record("run-1", baseline)

    assert record["schema_version"] == 2
    assert record["successful_runs"] == 1
    assert record["loop_success_rate"] == 0.5
    assert record["loop_success_variance"] == 0.25
    assert record["functional_runs"] == 1
    assert record["functional_pass_rate"] == 1
    assert record["pass_rate_variance"] == 0
    assert record["provider_error_rate"] == 0
    assert record["execution_error_rate"] == 0.5
    assert record["cancelled_rate"] == 0
    assert record["quality_runs"] == 1
    assert record["quality_pass_rate"] == 1
    assert record["mean_quality_score"] == pytest.approx(0.8)
    assert record["mean_steps"] == 3
    assert record["steps_stddev"] == 1
    assert record["router_version"] == "router-v1"
    assert record["router_enabled"] is True
    assert record["dataset_version"] == "v1-real-model"
    assert record["dataset_digest"] == "digest"
    assert record["code_revision"] == "revision"
    assert record["model"] == "deepseek-flash"
    assert record["provider"] == "deepseek"

    no_judge_baseline = trend.build_baseline(
        _report([_case_result("case-b__r1")]),
        repeats=1,
    )
    no_judge_record = trend._history_record("run-2", no_judge_baseline)
    assert no_judge_record["quality_runs"] == 0
    assert no_judge_record["quality_pass_rate"] is None
    assert no_judge_record["mean_quality_score"] is None


def test_history_trend_reports_metrics_deltas_and_schema_one_unknowns(
    tmp_path: Path,
) -> None:
    baseline, current = _trend_history_pair()
    record = trend._history_record("previous", baseline)

    history = trend.cost_trend(record, current)

    assert history.previous_loop_success_rate == 0.5
    assert history.current_loop_success_rate == 0.5
    assert history.delta_loop_success_rate == 0
    assert history.previous_execution_error_rate == 0.5
    assert history.current_execution_error_rate == 0
    assert history.delta_execution_error_rate == -0.5
    assert history.previous_cancelled_rate == 0
    assert history.current_cancelled_rate == 0.5
    assert history.delta_cancelled_rate == 0.5
    assert history.previous_quality_runs == 1
    assert history.current_quality_runs == 1
    assert history.previous_quality_pass_rate == 1
    assert history.current_quality_pass_rate == 0
    assert history.delta_quality_pass_rate == -1
    assert history.previous_mean_quality_score == pytest.approx(0.8)
    assert history.current_mean_quality_score == pytest.approx(0.4)
    assert history.delta_mean_quality_score == pytest.approx(-0.4)
    assert history.previous_mean_steps == 3
    assert history.current_mean_steps == 3
    assert history.delta_mean_steps == 0
    assert history.previous_router_version == "router-v1"
    assert history.current_router_version == "router-v2"
    assert history.previous_router_enabled is True
    assert history.current_router_enabled is False

    legacy_path = tmp_path / "schema-one-history.jsonl"
    legacy_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "repeats": current.repeats,
                "functional_pass_rate": 0.75,
                "mean_latency_ms": 12,
                "total_tokens": 8,
                "total_cost_usd": 0.02,
            }
        )
        + "\n",
        encoding="utf-8",
    )
    legacy = trend.read_last_history(legacy_path)
    assert legacy is not None
    assert legacy["loop_success_rate"] is None
    assert legacy["execution_error_rate"] is None
    assert legacy["quality_runs"] is None
    assert legacy["mean_steps"] is None
    assert legacy["router_version"] is None
    legacy_trend = trend.cost_trend(legacy, current)
    assert legacy_trend.previous_loop_success_rate is None
    assert legacy_trend.previous_execution_error_rate is None
    assert legacy_trend.previous_quality_runs is None
    assert legacy_trend.previous_mean_steps is None
    assert legacy_trend.previous_router_version is None
    assert legacy_trend.delta_loop_success_rate is None


def test_history_trend_deltas_are_unknown_when_repeats_differ() -> None:
    baseline, current = _trend_history_pair()
    previous = trend._history_record("previous", baseline)
    previous["repeats"] = 1

    history = trend.cost_trend(previous, current)

    assert history.delta_pass_rate is None
    assert history.delta_pass_rate_variance is None
    assert history.delta_loop_success_rate is None
    assert history.delta_loop_success_variance is None
    assert history.delta_provider_error_rate is None
    assert history.delta_execution_error_rate is None
    assert history.delta_cancelled_rate is None
    assert history.delta_quality_pass_rate is None
    assert history.delta_mean_quality_score is None
    assert history.delta_mean_steps is None
    assert history.delta_steps_stddev is None
    assert history.delta_latency_pct is None
    assert history.delta_tokens_pct is None
    assert history.delta_cost_pct is None


def _expanded_live_dataset():
    dataset = load_dataset("evals/datasets/v1-real-model.jsonl")
    base = next(item for item in dataset.cases if item.id == "real-model-tool-time")
    events = [
        ScriptEvent(
            type="tool_call_start",
            name="get_current_time",
            arguments={},
        ),
        ScriptEvent(type="message_chunk", content="The current time is noon."),
    ]
    base = base.model_copy(update={"fixtures": ExecutionFixture(events=events)})
    return dataset.model_copy(update={"cases": [base]}), base


@pytest.mark.asyncio
async def test_repeated_runs_are_independent_through_live_target(
    monkeypatch, tmp_path: Path
) -> None:
    config = load_config("evals/config/real-model.yaml")
    config.transcript_dir = str(tmp_path)
    dataset, base = _expanded_live_dataset()

    def gateway_factory(**_kwargs):
        return _Gateway(
            ScriptedLLM.script_steps(base.fixtures.events),
            provider="scripted",
            model="scripted-v1",
        )

    monkeypatch.setattr(adapter, "OpenAIModelGateway", gateway_factory)
    target = real_model.build_real_model_target(
        config,
        base_url="https://api.openai.com/v1",
        api_key="synthetic-evaluation-key",
        transcript_dir=tmp_path,
    )
    expanded = trend.expand_repeats(
        dataset.model_copy(update={"cases": [base]}),
        2,
    )

    report = await run_evaluation(config, expanded, target)
    baseline = trend.build_baseline(report, repeats=2)

    assert {case.case_id for case in report.cases} == {
        "real-model-tool-time__r1",
        "real-model-tool-time__r2",
    }
    assert len({case.run_id for case in report.cases}) == 2
    assert all(
        case.transcript_path is not None and Path(case.transcript_path).is_file()
        for case in report.cases
    )
    case = baseline.cases["real-model-tool-time"]
    assert case.runs == 2
    assert case.functional_pass_rate == 1.0
    assert case.pass_rate_variance == 0.0
    assert case.mean_tokens == 4
    assert case.provider_error_rate == 0


def test_trend_cli_updates_baseline_and_writes_history(
    monkeypatch, tmp_path: Path, capsys
) -> None:
    dataset, base = _expanded_live_dataset()
    assert dataset.dataset_version
    monkeypatch.setenv("OPENAI_API_KEY", "synthetic-evaluation-key")
    monkeypatch.delenv("OPENAI_BASE_URL", raising=False)

    elapsed = 0.0

    def deterministic_perf_counter() -> float:
        nonlocal elapsed
        value = elapsed
        elapsed += 0.1
        return value

    monkeypatch.setattr(
        entrypoint,
        "time",
        SimpleNamespace(perf_counter=deterministic_perf_counter),
    )

    def gateway_factory(**_kwargs):
        return _Gateway(
            ScriptedLLM.script_steps(base.fixtures.events),
            provider="scripted",
            model="scripted-v1",
        )

    monkeypatch.setattr(adapter, "OpenAIModelGateway", gateway_factory)
    output = tmp_path / "run-1"
    baseline_path = tmp_path / "baseline.json"
    history = tmp_path / "history.jsonl"
    common = [
        "--config",
        "evals/config/real-model.yaml",
        "--base-url",
        "https://api.openai.com/v1",
        "--case",
        "real-model-tool-time",
        "--repeats",
        "2",
        "--history",
        str(history),
        "--output-dir",
        str(output),
        "--run-id",
        "run-1",
    ]

    assert (
        trend.main([*common, "--baseline", str(baseline_path), "--update-baseline"])
        == 0
    )
    assert (output / "report.json").is_file()
    assert (output / "current-baseline.json").is_file()
    assert (output / "trend-report.json").is_file()
    assert baseline_path.is_file()
    assert len(history.read_text(encoding="utf-8").splitlines()) == 1
    capsys.readouterr()

    output2 = tmp_path / "run-2"
    history_records = history.read_text(encoding="utf-8").splitlines()
    history_record = json.loads(history_records[-1])
    history_record["total_tokens"] = 900
    history.write_text(json.dumps(history_record) + "\n", encoding="utf-8")
    assert (
        trend.main(
            [
                *common[: common.index("--output-dir")],
                "--output-dir",
                str(output2),
                "--run-id",
                "run-2",
                "--baseline",
                str(baseline_path),
            ]
        )
        == 0
    )
    assert (output2 / "trend-diff.json").is_file()
    diff = json.loads((output2 / "trend-diff.json").read_text(encoding="utf-8"))
    assert diff["regressions"] == []
    baseline_payload = json.loads(baseline_path.read_text(encoding="utf-8"))
    assert (
        diff["cost_trend"]["previous_total_tokens"]
        == baseline_payload["totals"]["total_tokens"]
    )
    report = json.loads((output2 / "trend-report.json").read_text(encoding="utf-8"))
    assert report["history_trend"]["previous_total_tokens"] == 900
    assert len(history.read_text(encoding="utf-8").splitlines()) == 2
    output_text = capsys.readouterr().err
    assert "loop_success_rate=100.0%" in output_text
    assert "successful_runs=2/2" in output_text
    assert "functional_pass_rate=100.0%" in output_text
    assert " pass_rate=" not in output_text
    assert "execution_error_rate=0.0%" in output_text
    assert "mean_steps=" in output_text


def test_anime_baseline_excludes_unsupported_cases_and_tracks_router_reliability() -> (
    None
):
    cases = [
        CaseResult(
            case_id="ANIME-001__r1",
            category="recommendation",
            passed=True,
            functional_passed=True,
            benchmark_status="PASS",
            outcome="passed",
            step_count=2,
            router_expected_agent="recommendation",
            router_match=True,
            route_observed=True,
        ),
        CaseResult(
            case_id="ANIME-001__r2",
            category="recommendation",
            passed=False,
            functional_passed=None,
            benchmark_status="UNGRADED",
            step_count=4,
            router_expected_agent="recommendation",
            router_match=False,
            route_observed=True,
        ),
        CaseResult(
            case_id="ANIME-004__r1",
            category="planning",
            passed=False,
            functional_passed=None,
            benchmark_status="UNSUPPORTED",
        ),
        CaseResult(
            case_id="ANIME-002__r1",
            category="recommendation",
            passed=False,
            functional_passed=None,
            benchmark_status="SKIP",
        ),
    ]
    report = _report(
        cases,
        environment={"router_version": "keyword-v1", "router_enabled": "true"},
    )

    baseline = trend.build_baseline(report, repeats=2)

    assert baseline.totals.runs == 2
    assert baseline.totals.successful_runs == 1
    assert baseline.totals.loop_success_rate == 0.5
    assert baseline.totals.pass_at_1 == 1.0
    assert baseline.totals.all_repeats_success_rate == 0.0
    assert baseline.totals.router_cases == 2
    assert baseline.totals.router_accuracy == 0.5
    assert set(baseline.cases) == {"ANIME-001"}
    assert baseline.cases["ANIME-001"].pass_at_1 == 1.0
    assert baseline.cases["ANIME-001"].all_repeats_success_rate == 0.0

    changed_case = baseline.cases["ANIME-001"].model_copy(
        update={"router_accuracy": 0.0}
    )
    changed_router = baseline.model_copy(
        update={
            "router_version": "keyword-v2",
            "totals": baseline.totals.model_copy(update={"router_accuracy": 0.0}),
            "cases": {"ANIME-001": changed_case},
        }
    )
    diff = trend.compare_baseline(
        baseline,
        changed_router,
        tolerance=trend.TrendTolerance(max_router_accuracy_drop=0.1),
    )
    assert not diff.version_failures
    assert any("router_accuracy" in item for item in diff.regressions)


def test_trend_usage_totals_stay_unknown_when_any_model_usage_is_unknown() -> None:
    known = _case_result("case-a__r1", tokens=20, cost=0.01)
    unknown = _case_result("case-a__r2", tokens=None, cost=None)

    baseline = trend.build_baseline(_report([known, unknown]), repeats=2)

    assert baseline.totals.total_tokens is None
    assert baseline.totals.total_cost_usd is None


def test_trend_success_metrics_include_pass_at_one_and_all_repeats() -> None:
    results = [
        _case_result("case-a__r1"),
        _case_result("case-a__r2", outcome="execution_error"),
        _case_result("case-b__r1", outcome="execution_error"),
        _case_result("case-b__r2", outcome="execution_error"),
    ]

    baseline = trend.build_baseline(_report(results), repeats=2)

    assert baseline.totals.pass_at_1 == 0.5
    assert baseline.totals.all_repeats_success_rate == 0.0
    assert baseline.cases["case-a"].pass_at_1 == 1.0
    assert baseline.cases["case-a"].all_repeats_success_rate == 0.0

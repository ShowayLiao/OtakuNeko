"""Multi-run live trend baseline, variance, regression and cost tracking.

Each selected case is expanded into independent copies, so every repetition
gets its own isolated database, Run, Trace and transcript through the same
``ProductionRuntimeTarget`` used by the live entry. This module only aggregates
and compares those reports; it never executes a case itself.

The trend CLI is intentionally not part of the PR-required CI gates.
"""

from __future__ import annotations

import argparse
import asyncio
from collections import defaultdict
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import statistics
import sys
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from app.agents.provider_endpoint import ProviderEndpointError
from app.evaluation.adapter import ProviderCredentialsUnavailable
from app.evaluation.config import load_config
from app.evaluation.dataset import load_dataset
from app.evaluation.errors import safe_error
from app.evaluation.l6_scoring import L6_DIMENSIONS
from app.evaluation.real_model import (
    build_real_model_target,
    select_dataset,
)
from app.evaluation.reporting import write_report
from app.evaluation.runner import build_component, run_evaluation
from app.evaluation.types import CaseResult, EvalDataset, EvalReport

DEFAULT_CONFIG = "evals/config/real-model.yaml"
DEFAULT_REPEATS = 3
DEFAULT_HISTORY = ".runtime/evaluation/l6-trend/history.jsonl"
_REPEAT_PATTERN = re.compile(r"^(?P<base>.+)__r(?P<repeat>\d+)$")
_RUN_ID_PATTERN = re.compile(r"^[A-Za-z0-9._-]+$")
_TREND_ENVIRONMENT_FIELDS = frozenset(
    {
        "python",
        "platform",
        "runner",
        "decision_contract",
        "router_enabled",
        "router_version",
        "benchmark_suite",
        "execution_mode",
        "fixture_set",
        "database_isolation",
        "external_responses",
        "provider_network_reachability",
        "prompt_digest",
        "worktree_dirty",
        "worktree_digest",
    }
)


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class TrendCaseBaseline(_StrictModel):
    case_id: str
    runs: int = Field(ge=1)
    successful_runs: int | None = Field(default=None, ge=0)
    loop_success_rate: float | None = Field(default=None, ge=0, le=1)
    loop_success_variance: float | None = Field(default=None, ge=0, le=1)
    pass_at_1: float | None = Field(default=None, ge=0, le=1)
    all_repeats_success_rate: float | None = Field(default=None, ge=0, le=1)
    functional_runs: int = Field(ge=0)
    functional_pass_rate: float | None = Field(default=None, ge=0, le=1)
    pass_rate_variance: float | None = Field(default=None, ge=0, le=1)
    mean_scores: dict[str, float] = Field(default_factory=dict)
    score_stddev: dict[str, float] = Field(default_factory=dict)
    mean_latency_ms: float = Field(default=0, ge=0)
    latency_stddev_ms: float = Field(default=0, ge=0)
    mean_tokens: float | None = Field(default=None, ge=0)
    tokens_stddev: float | None = Field(default=None, ge=0)
    mean_cost_usd: float | None = Field(default=None, ge=0)
    cost_stddev: float | None = Field(default=None, ge=0)
    provider_error_rate: float = Field(default=0, ge=0, le=1)
    execution_error_rate: float | None = Field(default=None, ge=0, le=1)
    cancelled_rate: float | None = Field(default=None, ge=0, le=1)
    mean_steps: float | None = Field(default=None, ge=0)
    steps_stddev: float | None = Field(default=None, ge=0)
    quality_runs: int | None = Field(default=None, ge=0)
    quality_pass_rate: float | None = Field(default=None, ge=0, le=1)
    mean_quality_score: float | None = Field(default=None, ge=0, le=1)
    router_cases: int = Field(default=0, ge=0)
    router_accuracy: float | None = Field(default=None, ge=0, le=1)


class TrendTotals(_StrictModel):
    cases: int = Field(ge=0)
    runs: int = Field(ge=0)
    successful_runs: int | None = Field(default=None, ge=0)
    loop_success_rate: float | None = Field(default=None, ge=0, le=1)
    loop_success_variance: float | None = Field(default=None, ge=0, le=1)
    pass_at_1: float | None = Field(default=None, ge=0, le=1)
    all_repeats_success_rate: float | None = Field(default=None, ge=0, le=1)
    functional_runs: int = Field(ge=0)
    functional_pass_rate: float | None = Field(default=None, ge=0, le=1)
    pass_rate_variance: float | None = Field(default=None, ge=0, le=1)
    mean_latency_ms: float = Field(default=0, ge=0)
    total_tokens: float | None = Field(default=None, ge=0)
    total_cost_usd: float | None = Field(default=None, ge=0)
    provider_error_rate: float | None = Field(default=None, ge=0, le=1)
    execution_error_rate: float | None = Field(default=None, ge=0, le=1)
    cancelled_rate: float | None = Field(default=None, ge=0, le=1)
    mean_steps: float | None = Field(default=None, ge=0)
    steps_stddev: float | None = Field(default=None, ge=0)
    quality_runs: int | None = Field(default=None, ge=0)
    quality_pass_rate: float | None = Field(default=None, ge=0, le=1)
    mean_quality_score: float | None = Field(default=None, ge=0, le=1)
    router_cases: int = Field(default=0, ge=0)
    router_accuracy: float | None = Field(default=None, ge=0, le=1)


class TrendBaseline(_StrictModel):
    schema_version: int = 3
    dataset_version: str
    dataset_digest: str
    repeats: int = Field(ge=1)
    model: str
    provider: str
    prompt_version: str
    code_revision: str
    worktree_digest: str | None = None
    created_at: datetime
    router_version: str | None = None
    router_enabled: bool | None = None
    environment: dict[str, str] = Field(default_factory=dict)
    executed_runs: int = Field(default=0, ge=0)
    cases: dict[str, TrendCaseBaseline] = Field(default_factory=dict)
    totals: TrendTotals


class TrendTolerance(_StrictModel):
    max_pass_rate_drop: float = Field(default=0.1, ge=0, le=1)
    max_score_drop: float = Field(default=0.1, ge=0, le=1)
    max_latency_increase_pct: float = Field(default=0.5, ge=0)
    max_token_increase_pct: float = Field(default=0.5, ge=0)
    max_cost_increase_pct: float = Field(default=0.5, ge=0)
    max_provider_error_increase: float = Field(default=0.1, ge=0, le=1)
    max_step_increase_pct: float = Field(default=0.5, ge=0)
    max_router_accuracy_drop: float = Field(default=0.1, ge=0, le=1)


class CostTrend(_StrictModel):
    previous_repeats: int | None = None
    current_repeats: int = Field(ge=1)
    previous_successful_runs: int | None = None
    current_successful_runs: int | None = None
    previous_loop_success_rate: float | None = None
    current_loop_success_rate: float | None = None
    previous_loop_success_variance: float | None = None
    current_loop_success_variance: float | None = None
    previous_pass_at_1: float | None = None
    current_pass_at_1: float | None = None
    previous_all_repeats_success_rate: float | None = None
    current_all_repeats_success_rate: float | None = None
    previous_functional_runs: int | None = None
    current_functional_runs: int | None = None
    previous_functional_pass_rate: float | None = None
    current_functional_pass_rate: float | None = Field(default=None, ge=0, le=1)
    previous_pass_rate_variance: float | None = None
    current_pass_rate_variance: float | None = None
    previous_provider_error_rate: float | None = None
    current_provider_error_rate: float | None = None
    previous_execution_error_rate: float | None = None
    current_execution_error_rate: float | None = None
    previous_cancelled_rate: float | None = None
    current_cancelled_rate: float | None = None
    previous_quality_runs: int | None = None
    current_quality_runs: int | None = None
    previous_quality_pass_rate: float | None = None
    current_quality_pass_rate: float | None = None
    previous_mean_quality_score: float | None = None
    current_mean_quality_score: float | None = None
    previous_mean_steps: float | None = None
    current_mean_steps: float | None = None
    previous_steps_stddev: float | None = None
    current_steps_stddev: float | None = None
    previous_router_version: str | None = None
    current_router_version: str | None = None
    previous_router_enabled: bool | None = None
    current_router_enabled: bool | None = None
    previous_router_cases: int | None = None
    current_router_cases: int = 0
    previous_router_accuracy: float | None = None
    current_router_accuracy: float | None = None
    previous_dataset_version: str | None = None
    current_dataset_version: str | None = None
    previous_dataset_digest: str | None = None
    current_dataset_digest: str | None = None
    previous_code_revision: str | None = None
    current_code_revision: str | None = None
    previous_worktree_digest: str | None = None
    current_worktree_digest: str | None = None
    previous_model: str | None = None
    current_model: str | None = None
    previous_provider: str | None = None
    current_provider: str | None = None
    previous_prompt_version: str | None = None
    current_prompt_version: str | None = None
    previous_mean_latency_ms: float | None = None
    current_mean_latency_ms: float = Field(default=0, ge=0)
    previous_total_tokens: float | None = None
    current_total_tokens: float | None = None
    previous_total_cost_usd: float | None = None
    current_total_cost_usd: float | None = None
    delta_pass_rate: float | None = None
    delta_pass_rate_variance: float | None = None
    delta_loop_success_rate: float | None = None
    delta_loop_success_variance: float | None = None
    delta_provider_error_rate: float | None = None
    delta_execution_error_rate: float | None = None
    delta_router_accuracy: float | None = None
    delta_cancelled_rate: float | None = None
    delta_quality_pass_rate: float | None = None
    delta_mean_quality_score: float | None = None
    delta_mean_steps: float | None = None
    delta_steps_stddev: float | None = None
    delta_latency_pct: float | None = None
    delta_tokens_pct: float | None = None
    delta_cost_pct: float | None = None


class TrendDiff(_StrictModel):
    schema_version: int = 1
    baseline: str | None = None
    comparison_compatible: bool = True
    comparison_blockers: list[str] = Field(default_factory=list)
    version_failures: list[str] = Field(default_factory=list)
    provenance_changes: list[str] = Field(default_factory=list)
    regressions: list[str] = Field(default_factory=list)
    improvements: list[str] = Field(default_factory=list)
    added: list[str] = Field(default_factory=list)
    missing: list[str] = Field(default_factory=list)
    quality_coverage: dict[str, dict[str, int | None]] = Field(default_factory=dict)
    cost_trend: CostTrend


def expand_repeats(dataset: EvalDataset, repeats: int) -> EvalDataset:
    """Create independent case ids so every repetition has its own Run/Trace."""
    if repeats < 1:
        raise ValueError("repeats must be positive")
    cases = []
    for case in dataset.cases:
        if _REPEAT_PATTERN.match(case.id):
            raise ValueError("case id already contains the repeat suffix")
        for index in range(1, repeats + 1):
            cases.append(case.model_copy(update={"id": f"{case.id}__r{index}"}))
    return dataset.model_copy(update={"cases": cases})


def _mean_std(values: list[float]) -> tuple[float, float]:
    if not values:
        return 0.0, 0.0
    return statistics.mean(values), statistics.pstdev(values)


def _step_metrics(results: list[CaseResult]) -> tuple[float | None, float | None]:
    values = [
        float(result.step_count)
        for result in results
        if result.step_count is not None
        and not (
            result.step_count == 0
            and result.outcome in {"provider_error", "execution_error", "cancelled"}
        )
    ]
    return _mean_std(values) if values else (None, None)


def _quality_metrics(
    results: list[CaseResult],
) -> tuple[int, float | None, float | None]:
    eligible = [
        result
        for result in results
        if result.judge.status == "available"
        and result.judge.quality_passed is not None
    ]
    if not eligible:
        return 0, None, None
    quality_pass_rate = sum(
        1 for result in eligible if result.judge.quality_passed
    ) / len(eligible)
    scores = [
        result.judge.score for result in eligible if result.judge.score is not None
    ]
    return (
        len(eligible),
        quality_pass_rate,
        statistics.mean(scores) if scores else None,
    )


def _outcome_rate(results: list[CaseResult], outcome: str) -> float | None:
    if not results:
        return None
    return sum(1 for result in results if result.outcome == outcome) / len(results)


def _successful_run(result: CaseResult) -> bool:
    return (
        result.benchmark_status == "PASS"
        if result.benchmark_status is not None
        else result.passed
    )


def _repeat_index(result: CaseResult) -> int:
    match = _REPEAT_PATTERN.match(result.case_id)
    return int(match.group("repeat")) if match else 1


def _router_metrics(results: list[CaseResult]) -> tuple[int, float | None]:
    eligible = [
        result for result in results if result.router_expected_agent is not None
    ]
    if not eligible:
        return 0, None
    return (
        len(eligible),
        sum(bool(result.router_match) for result in eligible) / len(eligible),
    )


def _environment_bool(environment: dict[str, str], key: str) -> bool | None:
    value = environment.get(key)
    if value is None:
        return None
    if value.casefold() == "true":
        return True
    if value.casefold() == "false":
        return False
    return None


def _case_baseline(case_id: str, results: list[CaseResult]) -> TrendCaseBaseline:
    ordered_results = sorted(results, key=_repeat_index)
    functional = [
        result
        for result in results
        if result.outcome in {"passed", "functional_failure"}
    ]
    passed = [1.0 if result.outcome == "passed" else 0.0 for result in functional]
    pass_rate = statistics.mean(passed) if passed else None
    variance = pass_rate * (1 - pass_rate) if pass_rate is not None else None

    score_values: dict[str, list[float]] = defaultdict(list)
    for result in functional:
        if result.l6 is None:
            continue
        for dimension in L6_DIMENSIONS:
            value = result.l6.scores.get(dimension)
            if value is not None:
                score_values[dimension].append(value)
    mean_scores = {
        dimension: statistics.mean(values) for dimension, values in score_values.items()
    }
    score_stddev = {
        dimension: statistics.pstdev(values)
        for dimension, values in score_values.items()
    }

    latency_mean, latency_stddev = _mean_std(
        [result.usage.latency_ms for result in results]
    )
    token_unknown = any(
        result.usage.model_calls > 0 and result.usage.model_tokens is None
        for result in results
    )
    token_values = [
        float(result.usage.model_tokens)
        for result in results
        if result.usage.model_tokens is not None
    ]
    cost_unknown = any(
        result.usage.model_calls > 0
        and (
            result.usage.estimated_cost_usd is None
            or result.usage.estimated_cost_unknown_count > 0
        )
        for result in results
    )
    cost_values = [
        result.usage.estimated_cost_usd
        for result in results
        if result.usage.estimated_cost_usd is not None
    ]
    token_mean, token_stddev = (
        _mean_std(token_values)
        if token_values and not token_unknown
        else (0.0, 0.0)
        if not token_unknown and not token_values
        else (None, None)
    )
    cost_mean, cost_stddev = (
        _mean_std(cost_values)
        if cost_values and not cost_unknown
        else (0.0, 0.0)
        if not any(result.usage.model_calls > 0 for result in results)
        else (None, None)
    )
    provider_errors = sum(1 for result in results if result.outcome == "provider_error")
    successful_runs = sum(1 for result in results if _successful_run(result))
    pass_at_1 = float(_successful_run(ordered_results[0]))
    all_repeats_success_rate = float(all(_successful_run(item) for item in results))
    mean_steps, steps_stddev = _step_metrics(results)
    quality_runs, quality_pass_rate, mean_quality_score = _quality_metrics(results)
    router_cases, router_accuracy = _router_metrics(results)
    return TrendCaseBaseline(
        case_id=case_id,
        runs=len(results),
        successful_runs=successful_runs,
        loop_success_rate=successful_runs / len(results),
        loop_success_variance=(successful_runs / len(results))
        * (1 - successful_runs / len(results)),
        pass_at_1=pass_at_1,
        all_repeats_success_rate=all_repeats_success_rate,
        functional_runs=len(functional),
        functional_pass_rate=pass_rate,
        pass_rate_variance=variance,
        mean_scores=mean_scores,
        score_stddev=score_stddev,
        mean_latency_ms=latency_mean,
        latency_stddev_ms=latency_stddev,
        mean_tokens=token_mean,
        tokens_stddev=token_stddev,
        mean_cost_usd=cost_mean,
        cost_stddev=cost_stddev,
        provider_error_rate=provider_errors / len(results),
        execution_error_rate=_outcome_rate(results, "execution_error"),
        cancelled_rate=_outcome_rate(results, "cancelled"),
        mean_steps=mean_steps,
        steps_stddev=steps_stddev,
        quality_runs=quality_runs,
        quality_pass_rate=quality_pass_rate,
        mean_quality_score=mean_quality_score,
        router_cases=router_cases,
        router_accuracy=router_accuracy,
    )


def build_baseline(report: EvalReport, *, repeats: int) -> TrendBaseline:
    groups: dict[str, list[CaseResult]] = defaultdict(list)
    evaluable = [
        result
        for result in report.cases
        if result.benchmark_status not in {"SKIP", "UNSUPPORTED"}
    ]
    for result in evaluable:
        match = _REPEAT_PATTERN.match(result.case_id)
        base = match.group("base") if match else result.case_id
        groups[base].append(result)
    cases = {
        case_id: _case_baseline(case_id, results)
        for case_id, results in sorted(groups.items())
    }
    all_results = evaluable
    functional = [
        result
        for result in all_results
        if result.outcome in {"passed", "functional_failure"}
    ]
    pass_rate = (
        sum(1 for result in functional if result.outcome == "passed") / len(functional)
        if functional
        else None
    )
    latency_mean, _ = _mean_std([result.usage.latency_ms for result in all_results])
    successful_runs = sum(1 for result in all_results if _successful_run(result))
    pass_at_1_values = [
        float(_successful_run(sorted(group, key=_repeat_index)[0]))
        for group in groups.values()
    ]
    all_repeats_values = [
        float(all(_successful_run(item) for item in group)) for group in groups.values()
    ]
    mean_steps, steps_stddev = _step_metrics(all_results)
    quality_runs, quality_pass_rate, mean_quality_score = _quality_metrics(all_results)
    router_cases, router_accuracy = _router_metrics(all_results)
    token_unknown = any(
        result.usage.model_calls > 0 and result.usage.model_tokens is None
        for result in all_results
    )
    token_values = [
        float(result.usage.model_tokens)
        for result in all_results
        if result.usage.model_tokens is not None
    ]
    cost_unknown = any(
        result.usage.model_calls > 0
        and (
            result.usage.estimated_cost_usd is None
            or result.usage.estimated_cost_unknown_count > 0
        )
        for result in all_results
    )
    cost_values = [
        result.usage.estimated_cost_usd
        for result in all_results
        if result.usage.estimated_cost_usd is not None
    ]
    return TrendBaseline(
        dataset_version=report.dataset_version,
        dataset_digest=report.dataset_digest,
        repeats=repeats,
        model=report.agent.model,
        provider=report.agent.provider,
        prompt_version=report.prompt_version,
        code_revision=report.code_revision,
        worktree_digest=report.environment.get("worktree_digest") or None,
        created_at=datetime.now(timezone.utc),
        router_version=report.environment.get("router_version") or None,
        router_enabled=_environment_bool(report.environment, "router_enabled"),
        environment={
            key: value[:256]
            for key, value in report.environment.items()
            if key in _TREND_ENVIRONMENT_FIELDS
            and isinstance(value, str)
            and len(value) <= 256
            and "\n" not in value
            and "\r" not in value
        },
        executed_runs=sum(1 for result in all_results if result.run_id is not None),
        cases=cases,
        totals=TrendTotals(
            cases=len(cases),
            runs=len(all_results),
            successful_runs=successful_runs,
            loop_success_rate=(
                successful_runs / len(all_results) if all_results else None
            ),
            loop_success_variance=(
                (successful_runs / len(all_results))
                * (1 - successful_runs / len(all_results))
                if all_results
                else None
            ),
            pass_at_1=(statistics.mean(pass_at_1_values) if pass_at_1_values else None),
            all_repeats_success_rate=(
                statistics.mean(all_repeats_values) if all_repeats_values else None
            ),
            functional_runs=len(functional),
            functional_pass_rate=pass_rate,
            pass_rate_variance=(
                pass_rate * (1 - pass_rate) if pass_rate is not None else None
            ),
            mean_latency_ms=latency_mean,
            total_tokens=(
                sum(token_values)
                if token_values and not token_unknown
                else 0.0
                if not token_unknown
                else None
            ),
            total_cost_usd=(
                sum(cost_values)
                if cost_values and not cost_unknown
                else 0.0
                if all(result.usage.model_calls == 0 for result in all_results)
                else None
            ),
            provider_error_rate=(
                sum(1 for result in all_results if result.outcome == "provider_error")
                / len(all_results)
                if all_results
                else None
            ),
            execution_error_rate=_outcome_rate(all_results, "execution_error"),
            cancelled_rate=_outcome_rate(all_results, "cancelled"),
            mean_steps=mean_steps,
            steps_stddev=steps_stddev,
            quality_runs=quality_runs,
            quality_pass_rate=quality_pass_rate,
            mean_quality_score=mean_quality_score,
            router_cases=router_cases,
            router_accuracy=router_accuracy,
        ),
    )


def select_compatible_baseline(
    candidates: list[tuple[Path, TrendBaseline]],
    current: TrendBaseline,
) -> tuple[Path, TrendBaseline] | None:
    """Choose the newest executed baseline for the exact dataset and network state.

    A baseline is comparable only when both schema versions are current and
    both dataset version and digest and provider network reachability match.
    Runs without persisted Run IDs are excluded so a placeholder or not-run
    report cannot become historical truth. Prompt, code, other environment,
    provider, model and router changes remain comparable provenance and are
    surfaced by ``compare_baseline``.
    """
    if current.schema_version != 3:
        return None
    compatible = [
        (path, baseline)
        for path, baseline in candidates
        if baseline.schema_version == current.schema_version
        and baseline.dataset_version == current.dataset_version
        and baseline.dataset_digest == current.dataset_digest
        and baseline.environment.get("provider_network_reachability")
        == current.environment.get("provider_network_reachability")
        and baseline.totals.runs > 0
        and baseline.executed_runs > 0
        and bool(baseline.cases)
    ]
    if not compatible:
        return None
    return max(compatible, key=lambda item: item[1].created_at)


def _pct_increase(current: float, previous: float) -> float | None:
    if previous <= 0:
        return None
    return (current - previous) / previous


def compare_baseline(
    baseline: TrendBaseline,
    current: TrendBaseline,
    *,
    tolerance: TrendTolerance,
    baseline_path: str | None = None,
) -> TrendDiff:
    version_failures: list[str] = []
    for side, candidate in (("baseline", baseline), ("current", current)):
        if candidate.schema_version != 3:
            version_failures.append(
                f"{side} schema_version={candidate.schema_version}; "
                "create a schema_version=3 trend baseline"
            )
        required_fields = (
            "successful_runs",
            "loop_success_rate",
            "loop_success_variance",
            "execution_error_rate",
            "cancelled_rate",
        )
        for field in required_fields:
            if getattr(candidate.totals, field) is None:
                version_failures.append(f"{side} totals missing {field}")
        for case_id, case in sorted(candidate.cases.items()):
            for field in required_fields:
                if getattr(case, field) is None:
                    version_failures.append(f"{side} case {case_id} missing {field}")

    provenance_changes: list[str] = []
    for field in (
        "dataset_version",
        "dataset_digest",
        "repeats",
        "model",
        "provider",
        "prompt_version",
        "code_revision",
        "worktree_digest",
        "router_version",
        "router_enabled",
    ):
        previous = getattr(baseline, field)
        actual = getattr(current, field)
        if previous != actual:
            provenance_changes.append(f"{field}: baseline={previous} current={actual}")

    for field in sorted(set(baseline.environment) | set(current.environment)):
        previous = baseline.environment.get(field)
        actual = current.environment.get(field)
        if previous != actual:
            provenance_changes.append(
                f"environment.{field}: baseline={previous} current={actual}"
            )

    comparison_blockers: list[str] = []
    if baseline.schema_version != 3 or current.schema_version != 3:
        comparison_blockers.append(
            "baseline schema is not compatible with trend schema_version=3"
        )
    if baseline.dataset_version != current.dataset_version:
        comparison_blockers.append(
            "dataset_version differs; metric comparison requires the same dataset"
        )
    if baseline.dataset_digest != current.dataset_digest:
        comparison_blockers.append(
            "dataset_digest differs; metric comparison requires the same dataset"
        )
    if baseline.environment.get(
        "provider_network_reachability"
    ) != current.environment.get("provider_network_reachability"):
        comparison_blockers.append(
            "provider_network_reachability differs; metric comparison requires "
            "the same provider network state"
        )
    if comparison_blockers:
        return TrendDiff(
            baseline=baseline_path,
            version_failures=version_failures,
            provenance_changes=provenance_changes,
            comparison_compatible=False,
            comparison_blockers=comparison_blockers,
            cost_trend=cost_trend(None, current),
        )

    regressions: list[str] = []
    improvements: list[str] = []
    missing: list[str] = []
    added: list[str] = []
    quality_coverage: dict[str, dict[str, int | None]] = {}
    if (
        baseline.totals.loop_success_rate is not None
        and current.totals.loop_success_rate is not None
    ):
        loop_drop = baseline.totals.loop_success_rate - current.totals.loop_success_rate
        if loop_drop > tolerance.max_pass_rate_drop:
            regressions.append(
                "totals: loop_success_rate "
                f"{current.totals.loop_success_rate} drops {loop_drop} "
                f"from {baseline.totals.loop_success_rate}"
            )
        elif -loop_drop > tolerance.max_pass_rate_drop:
            improvements.append(
                "totals: loop_success_rate "
                f"{current.totals.loop_success_rate} improves {-loop_drop}"
            )
    for field in ("pass_at_1", "all_repeats_success_rate"):
        previous_rate = getattr(baseline.totals, field)
        actual_rate = getattr(current.totals, field)
        if previous_rate is None or actual_rate is None:
            continue
        drop = previous_rate - actual_rate
        if drop > tolerance.max_pass_rate_drop:
            regressions.append(f"totals: {field} drops {drop:.1%}")
        elif -drop > tolerance.max_pass_rate_drop:
            improvements.append(f"totals: {field} improves {-drop:.1%}")
    for field in (
        "provider_error_rate",
        "execution_error_rate",
        "cancelled_rate",
    ):
        previous_rate = getattr(baseline.totals, field)
        actual_rate = getattr(current.totals, field)
        if previous_rate is None or actual_rate is None:
            continue
        increase = actual_rate - previous_rate
        if increase > tolerance.max_provider_error_increase:
            regressions.append(f"totals: {field} +{increase:.1%}")
    if (
        baseline.totals.router_accuracy is not None
        and current.totals.router_accuracy is not None
    ):
        router_drop = baseline.totals.router_accuracy - current.totals.router_accuracy
        if router_drop > tolerance.max_router_accuracy_drop:
            regressions.append(
                "totals: router_accuracy "
                f"{current.totals.router_accuracy} drops {router_drop} "
                f"from {baseline.totals.router_accuracy}"
            )
        elif -router_drop > tolerance.max_router_accuracy_drop:
            improvements.append(
                "totals: router_accuracy "
                f"{current.totals.router_accuracy} improves {-router_drop}"
            )
    for case_id, previous in sorted(baseline.cases.items()):
        actual = current.cases.get(case_id)
        if actual is None:
            missing.append(case_id)
            regressions.append(f"{case_id}: missing from current run")
            continue
        quality_coverage[case_id] = {
            "baseline_quality_runs": previous.quality_runs,
            "current_quality_runs": actual.quality_runs,
        }
        if (
            previous.functional_pass_rate is not None
            and actual.functional_pass_rate is not None
        ):
            drop = previous.functional_pass_rate - actual.functional_pass_rate
            if drop > tolerance.max_pass_rate_drop:
                regressions.append(
                    f"{case_id}: functional_pass_rate {actual.functional_pass_rate} "
                    f"drops {drop} from {previous.functional_pass_rate}"
                )
            elif -drop > tolerance.max_pass_rate_drop:
                improvements.append(
                    f"{case_id}: functional_pass_rate {actual.functional_pass_rate} "
                    f"improves {-drop}"
                )
        if (
            previous.loop_success_rate is not None
            and actual.loop_success_rate is not None
        ):
            loop_drop = previous.loop_success_rate - actual.loop_success_rate
            if loop_drop > tolerance.max_pass_rate_drop:
                regressions.append(
                    f"{case_id}: loop_success_rate {actual.loop_success_rate} "
                    f"drops {loop_drop} from {previous.loop_success_rate}"
                )
            elif -loop_drop > tolerance.max_pass_rate_drop:
                improvements.append(
                    f"{case_id}: loop_success_rate {actual.loop_success_rate} "
                    f"improves {-loop_drop}"
                )
        for field in ("pass_at_1", "all_repeats_success_rate"):
            previous_rate = getattr(previous, field)
            actual_rate = getattr(actual, field)
            if previous_rate is None or actual_rate is None:
                continue
            repeat_drop = previous_rate - actual_rate
            if repeat_drop > tolerance.max_pass_rate_drop:
                regressions.append(f"{case_id}: {field} drops {repeat_drop:.1%}")
            elif -repeat_drop > tolerance.max_pass_rate_drop:
                improvements.append(f"{case_id}: {field} improves {-repeat_drop:.1%}")
        if previous.router_accuracy is not None and actual.router_accuracy is not None:
            router_drop = previous.router_accuracy - actual.router_accuracy
            if router_drop > tolerance.max_router_accuracy_drop:
                regressions.append(
                    f"{case_id}: router_accuracy {actual.router_accuracy} "
                    f"drops {router_drop} from {previous.router_accuracy}"
                )
            elif -router_drop > tolerance.max_router_accuracy_drop:
                improvements.append(
                    f"{case_id}: router_accuracy {actual.router_accuracy} "
                    f"improves {-router_drop}"
                )
        for dimension, previous_score in previous.mean_scores.items():
            actual_score = actual.mean_scores.get(dimension)
            if actual_score is None:
                continue
            score_drop = previous_score - actual_score
            if score_drop > tolerance.max_score_drop:
                regressions.append(
                    f"{case_id}: {dimension} {actual_score} drops {score_drop}"
                )
            elif -score_drop > tolerance.max_score_drop:
                improvements.append(
                    f"{case_id}: {dimension} {actual_score} improves {-score_drop}"
                )
        has_functional_observations = (
            previous.functional_runs > 0 and actual.functional_runs > 0
        )
        if has_functional_observations:
            latency_pct = _pct_increase(
                actual.mean_latency_ms, previous.mean_latency_ms
            )
            if (
                latency_pct is not None
                and latency_pct > tolerance.max_latency_increase_pct
            ):
                regressions.append(f"{case_id}: latency +{latency_pct:.1%}")
        if previous.mean_tokens is not None and actual.mean_tokens is not None:
            token_pct = _pct_increase(actual.mean_tokens, previous.mean_tokens)
            if token_pct is not None and token_pct > tolerance.max_token_increase_pct:
                regressions.append(f"{case_id}: tokens +{token_pct:.1%}")
        if previous.mean_cost_usd is not None and actual.mean_cost_usd is not None:
            cost_pct = _pct_increase(actual.mean_cost_usd, previous.mean_cost_usd)
            if cost_pct is not None and cost_pct > tolerance.max_cost_increase_pct:
                regressions.append(f"{case_id}: cost +{cost_pct:.1%}")
        error_increase = actual.provider_error_rate - previous.provider_error_rate
        if error_increase > tolerance.max_provider_error_increase:
            regressions.append(f"{case_id}: provider_error_rate +{error_increase:.1%}")
        for field in ("execution_error_rate", "cancelled_rate"):
            previous_rate = getattr(previous, field)
            actual_rate = getattr(actual, field)
            if previous_rate is None or actual_rate is None:
                continue
            increase = actual_rate - previous_rate
            if increase > tolerance.max_provider_error_increase:
                regressions.append(f"{case_id}: {field} +{increase:.1%}")
        if (
            has_functional_observations
            and previous.mean_steps is not None
            and actual.mean_steps is not None
        ):
            step_increase = _pct_increase(actual.mean_steps, previous.mean_steps)
            if (
                step_increase is not None
                and step_increase > tolerance.max_step_increase_pct
            ):
                regressions.append(f"{case_id}: mean_steps +{step_increase:.1%}")
            elif previous.mean_steps == 0 and actual.mean_steps > 0:
                regressions.append(
                    f"{case_id}: mean_steps increased from 0 to {actual.mean_steps}"
                )
        if (
            previous.quality_runs is not None
            and previous.quality_runs > 0
            and actual.quality_runs is not None
            and actual.quality_runs > 0
        ):
            if (
                previous.quality_pass_rate is not None
                and actual.quality_pass_rate is not None
            ):
                quality_pass_drop = (
                    previous.quality_pass_rate - actual.quality_pass_rate
                )
                if quality_pass_drop > tolerance.max_pass_rate_drop:
                    regressions.append(
                        f"{case_id}: quality_pass_rate {actual.quality_pass_rate} "
                        f"drops {quality_pass_drop} from {previous.quality_pass_rate}"
                    )
                elif -quality_pass_drop > tolerance.max_pass_rate_drop:
                    improvements.append(
                        f"{case_id}: quality_pass_rate {actual.quality_pass_rate} "
                        f"improves {-quality_pass_drop}"
                    )
            if (
                previous.mean_quality_score is not None
                and actual.mean_quality_score is not None
            ):
                quality_score_drop = (
                    previous.mean_quality_score - actual.mean_quality_score
                )
                if quality_score_drop > tolerance.max_score_drop:
                    regressions.append(
                        f"{case_id}: mean_quality_score {actual.mean_quality_score} "
                        f"drops {quality_score_drop} from {previous.mean_quality_score}"
                    )
                elif -quality_score_drop > tolerance.max_score_drop:
                    improvements.append(
                        f"{case_id}: mean_quality_score {actual.mean_quality_score} "
                        f"improves {-quality_score_drop}"
                    )
    for case_id in sorted(current.cases):
        if case_id not in baseline.cases:
            added.append(case_id)
    return TrendDiff(
        baseline=baseline_path,
        comparison_compatible=True,
        comparison_blockers=[],
        version_failures=version_failures,
        provenance_changes=provenance_changes,
        regressions=regressions,
        improvements=improvements,
        added=added,
        missing=missing,
        quality_coverage=quality_coverage,
        cost_trend=cost_trend(_history_record("baseline", baseline), current),
    )


def read_last_history(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    last: dict[str, Any] | None = None
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(record, dict):
            if record.get("schema_version", 1) == 1:
                record = dict(record)
                for field in (
                    "successful_runs",
                    "loop_success_rate",
                    "loop_success_variance",
                    "pass_at_1",
                    "all_repeats_success_rate",
                    "functional_runs",
                    "execution_error_rate",
                    "cancelled_rate",
                    "quality_runs",
                    "quality_pass_rate",
                    "mean_quality_score",
                    "mean_steps",
                    "steps_stddev",
                    "router_version",
                    "router_enabled",
                ):
                    record.setdefault(field, None)
            last = record
    return last


def cost_trend(
    previous: dict[str, Any] | None,
    current: TrendBaseline,
) -> CostTrend:
    previous_record = previous or {}
    previous_repeats_value = previous_record.get("repeats")
    previous_repeats = (
        previous_repeats_value
        if isinstance(previous_repeats_value, int)
        and not isinstance(previous_repeats_value, bool)
        else None
    )
    comparable = previous is not None and previous_repeats == current.repeats

    def number(field: str) -> float | None:
        value = previous_record.get(field)
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            return None
        return float(value)

    def count(field: str) -> int | None:
        value = previous_record.get(field)
        if not isinstance(value, int) or isinstance(value, bool):
            return None
        return value

    def string(field: str) -> str | None:
        value = previous_record.get(field)
        return value if isinstance(value, str) else None

    def boolean(field: str) -> bool | None:
        value = previous_record.get(field)
        return value if isinstance(value, bool) else None

    performance_comparable = (
        comparable
        and (count("functional_runs") or 0) > 0
        and current.totals.functional_runs > 0
    )

    def delta(
        current_value: float | None,
        previous_value: float | None,
        *,
        performance_metric: bool = False,
    ) -> float | None:
        is_comparable = performance_comparable if performance_metric else comparable
        if not is_comparable or current_value is None or previous_value is None:
            return None
        return current_value - previous_value

    def delta_pct(
        current_value: float | None,
        previous_value: float | None,
        *,
        performance_metric: bool = False,
    ) -> float | None:
        is_comparable = performance_comparable if performance_metric else comparable
        if not is_comparable or current_value is None or previous_value is None:
            return None
        if previous_value <= 0:
            return None
        return (current_value - previous_value) / previous_value

    return CostTrend(
        previous_repeats=previous_repeats,
        current_repeats=current.repeats,
        previous_successful_runs=count("successful_runs"),
        current_successful_runs=current.totals.successful_runs,
        previous_loop_success_rate=number("loop_success_rate"),
        current_loop_success_rate=current.totals.loop_success_rate,
        previous_loop_success_variance=number("loop_success_variance"),
        current_loop_success_variance=current.totals.loop_success_variance,
        previous_pass_at_1=number("pass_at_1"),
        current_pass_at_1=current.totals.pass_at_1,
        previous_all_repeats_success_rate=number("all_repeats_success_rate"),
        current_all_repeats_success_rate=current.totals.all_repeats_success_rate,
        previous_functional_runs=count("functional_runs"),
        current_functional_runs=current.totals.functional_runs,
        previous_functional_pass_rate=number("functional_pass_rate"),
        current_functional_pass_rate=current.totals.functional_pass_rate,
        previous_pass_rate_variance=number("pass_rate_variance"),
        current_pass_rate_variance=current.totals.pass_rate_variance,
        previous_provider_error_rate=number("provider_error_rate"),
        current_provider_error_rate=current.totals.provider_error_rate,
        previous_execution_error_rate=number("execution_error_rate"),
        current_execution_error_rate=current.totals.execution_error_rate,
        previous_cancelled_rate=number("cancelled_rate"),
        current_cancelled_rate=current.totals.cancelled_rate,
        previous_quality_runs=count("quality_runs"),
        current_quality_runs=current.totals.quality_runs,
        previous_quality_pass_rate=number("quality_pass_rate"),
        current_quality_pass_rate=current.totals.quality_pass_rate,
        previous_mean_quality_score=number("mean_quality_score"),
        current_mean_quality_score=current.totals.mean_quality_score,
        previous_mean_steps=number("mean_steps"),
        current_mean_steps=current.totals.mean_steps,
        previous_steps_stddev=number("steps_stddev"),
        current_steps_stddev=current.totals.steps_stddev,
        previous_router_version=string("router_version"),
        current_router_version=current.router_version,
        previous_router_enabled=boolean("router_enabled"),
        current_router_enabled=current.router_enabled,
        previous_router_cases=count("router_cases"),
        current_router_cases=current.totals.router_cases,
        previous_router_accuracy=number("router_accuracy"),
        current_router_accuracy=current.totals.router_accuracy,
        previous_dataset_version=string("dataset_version"),
        current_dataset_version=current.dataset_version,
        previous_dataset_digest=string("dataset_digest"),
        current_dataset_digest=current.dataset_digest,
        previous_code_revision=string("code_revision"),
        current_code_revision=current.code_revision,
        previous_worktree_digest=string("worktree_digest"),
        current_worktree_digest=current.worktree_digest,
        previous_model=string("model"),
        current_model=current.model,
        previous_provider=string("provider"),
        current_provider=current.provider,
        previous_prompt_version=string("prompt_version"),
        current_prompt_version=current.prompt_version,
        previous_mean_latency_ms=number("mean_latency_ms"),
        current_mean_latency_ms=current.totals.mean_latency_ms,
        previous_total_tokens=number("total_tokens"),
        current_total_tokens=current.totals.total_tokens,
        previous_total_cost_usd=number("total_cost_usd"),
        current_total_cost_usd=current.totals.total_cost_usd,
        delta_pass_rate=delta(
            current.totals.functional_pass_rate,
            number("functional_pass_rate"),
        ),
        delta_pass_rate_variance=delta(
            current.totals.pass_rate_variance,
            number("pass_rate_variance"),
        ),
        delta_loop_success_rate=delta(
            current.totals.loop_success_rate,
            number("loop_success_rate"),
        ),
        delta_loop_success_variance=delta(
            current.totals.loop_success_variance,
            number("loop_success_variance"),
        ),
        delta_provider_error_rate=delta(
            current.totals.provider_error_rate,
            number("provider_error_rate"),
        ),
        delta_execution_error_rate=delta(
            current.totals.execution_error_rate,
            number("execution_error_rate"),
        ),
        delta_router_accuracy=delta(
            current.totals.router_accuracy,
            number("router_accuracy"),
        ),
        delta_cancelled_rate=delta(
            current.totals.cancelled_rate,
            number("cancelled_rate"),
        ),
        delta_quality_pass_rate=delta(
            current.totals.quality_pass_rate,
            number("quality_pass_rate"),
        ),
        delta_mean_quality_score=delta(
            current.totals.mean_quality_score,
            number("mean_quality_score"),
        ),
        delta_mean_steps=delta(
            current.totals.mean_steps,
            number("mean_steps"),
            performance_metric=True,
        ),
        delta_steps_stddev=delta(
            current.totals.steps_stddev,
            number("steps_stddev"),
            performance_metric=True,
        ),
        delta_latency_pct=delta_pct(
            current.totals.mean_latency_ms,
            number("mean_latency_ms"),
            performance_metric=True,
        ),
        delta_tokens_pct=delta_pct(
            current.totals.total_tokens,
            number("total_tokens"),
        ),
        delta_cost_pct=delta_pct(
            current.totals.total_cost_usd,
            number("total_cost_usd"),
        ),
    )


def append_history(path: Path, record: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")


def _default_baseline_path(model: str) -> Path:
    slug = re.sub(r"[^A-Za-z0-9._-]", "_", model) or "model"
    return Path("evals/baselines") / f"l6-trend-{slug}.json"


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    temporary.replace(path)


def _history_record(
    run_id: str,
    current: TrendBaseline,
) -> dict[str, Any]:
    return {
        "schema_version": 2,
        "run_id": run_id,
        "recorded_at": datetime.now(timezone.utc).isoformat(),
        "dataset_version": current.dataset_version,
        "dataset_digest": current.dataset_digest,
        "repeats": current.repeats,
        "model": current.model,
        "provider": current.provider,
        "prompt_version": current.prompt_version,
        "code_revision": current.code_revision,
        "worktree_digest": current.worktree_digest,
        "successful_runs": current.totals.successful_runs,
        "loop_success_rate": current.totals.loop_success_rate,
        "loop_success_variance": current.totals.loop_success_variance,
        "pass_at_1": current.totals.pass_at_1,
        "all_repeats_success_rate": current.totals.all_repeats_success_rate,
        "functional_runs": current.totals.functional_runs,
        "functional_pass_rate": current.totals.functional_pass_rate,
        "pass_rate_variance": current.totals.pass_rate_variance,
        "provider_error_rate": current.totals.provider_error_rate,
        "execution_error_rate": current.totals.execution_error_rate,
        "cancelled_rate": current.totals.cancelled_rate,
        "quality_runs": current.totals.quality_runs,
        "quality_pass_rate": current.totals.quality_pass_rate,
        "mean_quality_score": current.totals.mean_quality_score,
        "mean_steps": current.totals.mean_steps,
        "steps_stddev": current.totals.steps_stddev,
        "router_version": current.router_version,
        "router_enabled": current.router_enabled,
        "router_cases": current.totals.router_cases,
        "router_accuracy": current.totals.router_accuracy,
        "mean_latency_ms": current.totals.mean_latency_ms,
        "total_tokens": current.totals.total_tokens,
        "total_cost_usd": current.totals.total_cost_usd,
    }


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the live model repeatedly and compare a trend baseline",
    )
    parser.add_argument("--config", default=DEFAULT_CONFIG)
    parser.add_argument("--dataset", help="Override configured dataset path")
    parser.add_argument("--model", help="Override the configured model name")
    parser.add_argument("--base-url", help="Override provider endpoint")
    parser.add_argument(
        "--case",
        action="append",
        dest="case_ids",
        help="Run only this case id (repeatable)",
    )
    parser.add_argument("--limit", type=int, help="Limit base cases")
    parser.add_argument("--tags", nargs="*", help="Override configured tags")
    parser.add_argument("--repeats", type=int, default=DEFAULT_REPEATS)
    parser.add_argument("--baseline", help="Baseline JSON path to compare or update")
    parser.add_argument(
        "--update-baseline",
        action="store_true",
        help="Write the current run as the new baseline",
    )
    parser.add_argument("--force", action="store_true", help="Overwrite baseline")
    parser.add_argument("--history", default=DEFAULT_HISTORY)
    parser.add_argument("--output-dir", help="Run artifact directory")
    parser.add_argument("--run-id", help="Run id for the artifact directory")
    parser.add_argument("--human-reviews", help="Versioned human review JSON")
    parser.add_argument("--temperature", type=float, default=0)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv if argv is not None else sys.argv[1:])
    try:
        config = load_config(args.config)
        if args.dataset:
            config.dataset = args.dataset
        if args.tags is not None:
            config.tags = args.tags
        if args.model:
            config.agent = config.agent.model_copy(update={"model": args.model})
        if args.human_reviews:
            config.human_reviews = args.human_reviews
        run_id = (
            args.run_id
            or datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            + "-"
            + uuid4().hex[:8]
        )
        if not _RUN_ID_PATTERN.fullmatch(run_id) or run_id in {".", ".."}:
            raise ValueError("run id must match [A-Za-z0-9._-]+")
        output_dir = (
            Path(args.output_dir)
            if args.output_dir
            else Path(config.report_path).parent / "l6-trend" / run_id
        )
        if output_dir.exists():
            raise ValueError("trend output directory already exists")
        transcript_dir = output_dir / "transcripts"
        config.transcript_dir = str(transcript_dir)
        base_dataset = select_dataset(
            load_dataset(config.dataset),
            case_ids=args.case_ids,
            limit=args.limit,
        )
        dataset = expand_repeats(base_dataset, args.repeats)
        target = build_real_model_target(
            config,
            model=args.model,
            base_url=args.base_url,
            transcript_dir=transcript_dir,
            temperature=args.temperature,
            deepseek_options=(
                config.deepseek.model_dump(mode="json")
                if config.deepseek is not None
                else None
            ),
        )
        if args.base_url:
            os.environ["OPENAI_BASE_URL"] = args.base_url
        judge = (
            build_component(config.judge_factory, config)
            if config.judge_factory
            else None
        )
        print(
            "l6-trend: "
            f"model={config.agent.model} repeats={args.repeats} "
            f"base_cases={len(base_dataset.cases)} runs={len(dataset.cases)} "
            f"output={output_dir}",
            file=sys.stderr,
        )
        report = asyncio.run(run_evaluation(config, dataset, target, judge=judge))
        write_report(report, output_dir / "report.json")
        current = build_baseline(report, repeats=args.repeats)
        _write_json(
            output_dir / "current-baseline.json", current.model_dump(mode="json")
        )
        gate_failures = report.gate_failures + report.baseline_failures

        baseline_path = (
            Path(args.baseline)
            if args.baseline
            else _default_baseline_path(current.model)
        )
        diff: TrendDiff | None = None
        if args.update_baseline:
            if gate_failures:
                print(
                    "l6-trend: refusing to update baseline while gates fail: "
                    + "; ".join(gate_failures),
                    file=sys.stderr,
                )
            else:
                if baseline_path.exists() and not args.force:
                    raise ValueError("baseline already exists; pass --force to replace")
                _write_json(baseline_path, current.model_dump(mode="json"))
        elif args.baseline:
            if not baseline_path.is_file():
                raise ValueError("baseline missing")
            baseline = TrendBaseline.model_validate_json(
                baseline_path.read_text(encoding="utf-8")
            )
            diff = compare_baseline(
                baseline,
                current,
                tolerance=TrendTolerance(),
                baseline_path=str(baseline_path),
            )

        history_path = Path(args.history)
        previous = read_last_history(history_path)
        trend = cost_trend(previous, current)
        append_history(history_path, _history_record(run_id, current))
        verdict = (
            "gate_failed"
            if gate_failures
            else (
                "baseline_updated"
                if args.update_baseline
                else (
                    "regression"
                    if diff and (diff.regressions or diff.version_failures)
                    else "baseline_incompatible"
                    if diff and not diff.comparison_compatible
                    else "pass"
                    if diff
                    else "baseline_missing"
                )
            )
        )
        _write_json(
            output_dir / "trend-report.json",
            {
                "schema_version": 1,
                "run_id": run_id,
                "verdict": verdict,
                "report": str(output_dir / "report.json"),
                "current_baseline": str(output_dir / "current-baseline.json"),
                "baseline": str(baseline_path) if baseline_path else None,
                "diff": diff.model_dump(mode="json") if diff is not None else None,
                "history_trend": trend.model_dump(mode="json"),
                "gate_failures": gate_failures,
                "totals": current.totals.model_dump(mode="json"),
                "history": str(history_path),
            },
        )
        if diff is not None:
            _write_json(output_dir / "trend-diff.json", diff.model_dump(mode="json"))
        loop_success_rate = (
            f"{current.totals.loop_success_rate:.1%}"
            if current.totals.loop_success_rate is not None
            else "unknown"
        )
        loop_success_variance = (
            f"{current.totals.loop_success_variance:.3f}"
            if current.totals.loop_success_variance is not None
            else "unknown"
        )
        pass_at_1 = (
            f"{current.totals.pass_at_1:.1%}"
            if current.totals.pass_at_1 is not None
            else "unknown"
        )
        all_repeats_success_rate = (
            f"{current.totals.all_repeats_success_rate:.1%}"
            if current.totals.all_repeats_success_rate is not None
            else "unknown"
        )
        execution_error_rate = (
            f"{current.totals.execution_error_rate:.1%}"
            if current.totals.execution_error_rate is not None
            else "unknown"
        )
        cancelled_rate = (
            f"{current.totals.cancelled_rate:.1%}"
            if current.totals.cancelled_rate is not None
            else "unknown"
        )
        mean_steps = (
            f"{current.totals.mean_steps:.1f}"
            if current.totals.mean_steps is not None
            else "unknown"
        )
        successful_runs = (
            str(current.totals.successful_runs)
            if current.totals.successful_runs is not None
            else "unknown"
        )
        router_accuracy = (
            f"{current.totals.router_accuracy:.1%}"
            if current.totals.router_accuracy is not None
            else "unknown"
        )
        functional_pass_rate = (
            f"{current.totals.functional_pass_rate:.1%}"
            if current.totals.functional_pass_rate is not None
            else "not_run"
        )
        functional_pass_variance = (
            f"{current.totals.pass_rate_variance:.3f}"
            if current.totals.pass_rate_variance is not None
            else "not_run"
        )
        provider_error_rate = (
            f"{current.totals.provider_error_rate:.1%}"
            if current.totals.provider_error_rate is not None
            else "not_run"
        )
        print(
            "l6-trend result: "
            f"verdict={verdict} "
            f"loop_success_rate={loop_success_rate} "
            f"pass_at_1={pass_at_1} "
            f"all_repeats_success_rate={all_repeats_success_rate} "
            f"successful_runs={successful_runs}/{current.totals.runs} "
            f"router_accuracy={router_accuracy} "
            f"loop_success_variance={loop_success_variance} "
            f"functional_pass_rate={functional_pass_rate} "
            f"functional_pass_variance={functional_pass_variance} "
            f"provider_error_rate={provider_error_rate} "
            f"execution_error_rate={execution_error_rate} "
            f"cancelled_rate={cancelled_rate} "
            f"mean_steps={mean_steps} "
            f"latency_ms={current.totals.mean_latency_ms:.1f} "
            f"tokens={current.totals.total_tokens} "
            f"cost={current.totals.total_cost_usd} "
            f"regressions={len(diff.regressions) if diff else 0}",
            file=sys.stderr,
        )
        return (
            1
            if gate_failures
            or (
                diff is not None
                and (
                    diff.regressions
                    or diff.version_failures
                    or not diff.comparison_compatible
                )
            )
            else 0
        )
    except ProviderCredentialsUnavailable:
        print(
            "l6-trend requires OPENAI_API_KEY or a local endpoint",
            file=sys.stderr,
        )
        return 2
    except ProviderEndpointError as exc:
        print(
            f"provider endpoint rejected: {exc.provider_error_code}",
            file=sys.stderr,
        )
        return 2
    except Exception as exc:
        print(safe_error(exc, "configuration_invalid"), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

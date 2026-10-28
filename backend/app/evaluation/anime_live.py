"""Real-provider CLI and report assembly for Anime Agent Benchmark v1."""

from __future__ import annotations

import argparse
import asyncio
from collections import defaultdict
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from typing import Any
from uuid import uuid4

from app.agents.provider_endpoint import ProviderEndpointError
from app.evaluation.adapter import ProviderCredentialsUnavailable
from app.evaluation.anime_benchmark import (
    SUPPORTED_SCENARIO_IDS,
    UNSUPPORTED_SCENARIO_REASONS,
    AnimeBenchmarkScenario,
    AnimeBenchmarkSuite,
    expected_router_agent,
    load_anime_benchmark_suite,
    scenario_to_eval_case,
)
from app.evaluation.config import EvaluationConfig, load_config
from app.evaluation.errors import safe_error
from app.evaluation.real_model import build_real_model_target
from app.evaluation.reporting import write_report
from app.evaluation.runner import build_component, evaluate_gate, run_evaluation
from app.evaluation.trend import (
    TrendBaseline,
    TrendDiff,
    TrendTolerance,
    build_baseline,
    compare_baseline,
    expand_repeats,
    select_compatible_baseline,
)
from app.evaluation.types import (
    CaseResult,
    EvalDataset,
    EvalReport,
    HardCheckResult,
    JudgeOutcome,
    utc_now,
)

DEFAULT_CONFIG = "evals/config/anime-agent-benchmark-v1.yaml"
DEFAULT_PACKAGE = "../otakuneko-benchmark-v1"
SMOKE_CASE_IDS = frozenset(
    {"ANIME-001", "ANIME-003", "ANIME-005", "ANIME-007", "ANIME-009", "ANIME-011"}
)
_RUN_ID_PATTERN = re.compile(r"^[A-Za-z0-9._-]+$")
_REPEAT_PATTERN = re.compile(r"^(?P<base>.+)__r(?P<repeat>[1-9][0-9]*)$")
_REPO_ROOT = Path(__file__).resolve().parents[3]
_PROMPT_SOURCE_PATHS = (
    "backend/app/harness/runtime.py",
    "backend/app/harness/model_gateway.py",
    "backend/app/harness/context_manager.py",
    "backend/app/harness/execution.py",
    "backend/app/agents/router.py",
    "backend/app/agents/recommendation_agent.py",
)


def _base_case_id(case_id: str) -> str:
    match = _REPEAT_PATTERN.fullmatch(case_id)
    return match.group("base") if match else case_id


def _prompt_digest() -> str:
    digest = hashlib.sha256()
    for relative in _PROMPT_SOURCE_PATHS:
        path = _REPO_ROOT / relative
        digest.update(relative.encode("utf-8"))
        digest.update(path.read_bytes())
    return digest.hexdigest()


def _worktree_digest() -> tuple[str, bool]:
    diff = subprocess.run(
        [
            "git",
            "diff",
            "--binary",
            "HEAD",
            "--",
            "backend/app",
            "backend/evals/config",
        ],
        cwd=_REPO_ROOT,
        check=False,
        capture_output=True,
    )
    if diff.returncode != 0:
        raise RuntimeError("could not calculate benchmark worktree digest")
    digest = hashlib.sha256(diff.stdout)
    dirty = bool(diff.stdout)
    untracked = subprocess.run(
        ["git", "ls-files", "--others", "--exclude-standard"],
        cwd=_REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    if untracked.returncode != 0:
        raise RuntimeError("could not enumerate untracked benchmark source files")
    for relative in sorted(untracked.stdout.splitlines()):
        if not relative.startswith(("backend/app/", "backend/evals/config/")):
            continue
        path = _REPO_ROOT / relative
        if not path.is_file() or path.suffix not in {".py", ".yaml", ".yml"}:
            continue
        digest.update(relative.encode("utf-8"))
        digest.update(path.read_bytes())
        dirty = True
    return digest.hexdigest(), dirty


def _provider_network_reachability(cases: list[CaseResult]) -> str:
    observations: set[str] = set()
    for case in cases:
        failure = case.provider_failure
        if isinstance(failure, dict):
            if failure.get("category") == "network_blocked":
                observations.add("blocked")
            elif failure.get("http_status") is not None:
                observations.add("reachable")
            else:
                observations.add("unknown")
        elif case.usage.model_calls > 0:
            observations.add("reachable")
    if not observations:
        return "not_observed"
    if len(observations) == 1:
        return next(iter(observations))
    return "mixed"


def select_scenarios(
    suite: AnimeBenchmarkSuite,
    *,
    suite_name: str,
    case_ids: list[str] | None = None,
) -> tuple[set[str], EvalDataset]:
    if case_ids:
        selected = set(case_ids)
        missing = sorted(selected - {case.id for case in suite.cases})
        if missing:
            raise ValueError("unknown anime benchmark case: " + ", ".join(missing))
    elif suite_name == "smoke":
        selected = set(SMOKE_CASE_IDS)
    else:
        selected = {case.id for case in suite.cases}

    supported = [
        scenario
        for scenario in suite.cases
        if scenario.id in selected
        and scenario.id in SUPPORTED_SCENARIO_IDS
        and scenario.id not in UNSUPPORTED_SCENARIO_REASONS
        and len(scenario.turns) == 1
        and not scenario.requires_confirmation
    ]
    dataset_digest = hashlib.sha256(
        (suite.content_digest + "\n" + "\n".join(sorted(selected))).encode("utf-8")
    ).hexdigest()
    dataset = EvalDataset(
        dataset_version=f"{suite.dataset_version}/{suite_name}",
        schema_version=1,
        content_digest=dataset_digest,
        cases=[scenario_to_eval_case(scenario, user_id=9001) for scenario in supported],
    )
    return selected, dataset


def _non_run_case(
    scenario: AnimeBenchmarkScenario,
    *,
    case_id: str,
    status: str,
    reason: str,
) -> CaseResult:
    hard_checks = [
        HardCheckResult(
            rule=check.rule,
            status="UNSUPPORTED" if status == "UNSUPPORTED" else "UNGRADED",
            detail=reason,
        )
        for check in scenario.hard_checks
    ]
    return CaseResult(
        case_id=case_id,
        category=scenario.group,
        passed=False,
        functional_passed=None,
        functional_status=("EXECUTION_FAILED" if status == "ERROR" else "NOT_RUN"),
        quality_status="NOT_REQUESTED",
        benchmark_status=status,  # type: ignore[arg-type]
        hard_checks=hard_checks,
        judge=JudgeOutcome(status="not_requested"),
        outcome="execution_error" if status == "ERROR" else None,
        error=reason,
    )


def assemble_anime_report(
    run_report: EvalReport,
    suite: AnimeBenchmarkSuite,
    *,
    selected_ids: set[str],
    suite_name: str,
    repeats: int,
    run_id: str,
) -> EvalReport:
    actual_by_id = {case.case_id: case for case in run_report.cases}
    result_cases: list[CaseResult] = []

    for repeat in range(1, repeats + 1):
        for scenario in suite.cases:
            expected_case_id = (
                scenario.id if repeats == 1 else f"{scenario.id}__r{repeat}"
            )
            if scenario.id not in selected_ids:
                result_cases.append(
                    _non_run_case(
                        scenario,
                        case_id=expected_case_id,
                        status="SKIP",
                        reason=f"not selected by {suite_name} suite",
                    )
                )
                continue
            if scenario.id not in SUPPORTED_SCENARIO_IDS:
                result_cases.append(
                    _non_run_case(
                        scenario,
                        case_id=expected_case_id,
                        status="UNSUPPORTED",
                        reason=UNSUPPORTED_SCENARIO_REASONS.get(
                            scenario.id,
                            "No isolated evaluator is implemented for this scenario.",
                        ),
                    )
                )
                continue

            actual = actual_by_id.get(expected_case_id)
            if actual is None:
                result_cases.append(
                    _non_run_case(
                        scenario,
                        case_id=expected_case_id,
                        status="ERROR",
                        reason="selected live case did not produce a result",
                    )
                )
                continue
            expected_agent = expected_router_agent(scenario)
            actual.router_expected_agent = expected_agent
            actual.router_match = (
                actual.route_observed and actual.route_agent == expected_agent
            )
            if (
                actual.outcome
                in {
                    "provider_error",
                    "execution_error",
                    "cancelled",
                }
                or actual.benchmark_status == "ERROR"
            ):
                actual.functional_status = "EXECUTION_FAILED"
                actual.functional_passed = None
            elif actual.functional_passed is None:
                actual.functional_status = "NOT_RUN"
            elif actual.functional_passed:
                actual.functional_status = "PASSED"
            else:
                actual.functional_status = "ASSERTION_FAILED"
            result_cases.append(actual)

    run_report.task = "ANIME-AGENT-BENCHMARK-V1"
    run_report.dataset_version = f"{suite.dataset_version}/{suite_name}"
    run_report.dataset_digest = hashlib.sha256(
        (suite.content_digest + "\n" + "\n".join(sorted(selected_ids))).encode("utf-8")
    ).hexdigest()
    prompt_hash = _prompt_digest()
    worktree_hash, worktree_dirty = _worktree_digest()
    run_report.prompt_version = f"{run_report.prompt_version}+sha256:{prompt_hash[:16]}"
    run_report.cases = result_cases
    run_report.environment.update(
        {
            "benchmark_suite": suite_name,
            "benchmark_run_id": run_id,
            "execution_mode": "real-provider-runtime",
            "fixture_set": "synthetic_v1",
            "database_isolation": "fresh-in-memory-sqlite-per-case-and-repeat",
            "external_responses": "controlled-fixtures-only",
            "provider_network_reachability": _provider_network_reachability(
                result_cases
            ),
            "prompt_digest": prompt_hash,
            "worktree_dirty": str(worktree_dirty).lower(),
            "worktree_digest": worktree_hash,
        }
    )
    run_report.evaluation_budget.update(
        {
            "repeats": repeats,
            "selected_scenarios": len(selected_ids),
            "max_tools_per_case": max(
                (
                    case.max_tool_calls
                    for case in suite.cases
                    if case.id in selected_ids
                ),
                default=0,
            ),
        }
    )

    attempted = [
        case
        for case in result_cases
        if case.benchmark_status in {"PASS", "FAIL", "ERROR", "UNGRADED"}
    ]
    repeat_groups: dict[str, list[CaseResult]] = defaultdict(list)
    for case in attempted:
        repeat_groups[_base_case_id(case.case_id)].append(case)
    ordered_groups = {
        case_id: sorted(
            cases,
            key=lambda item: (
                int(_REPEAT_PATTERN.fullmatch(item.case_id).group("repeat"))
                if _REPEAT_PATTERN.fullmatch(item.case_id)
                else 1
            ),
        )
        for case_id, cases in repeat_groups.items()
    }
    pass_at_1 = (
        sum(
            case_group[0].benchmark_status == "PASS"
            for case_group in ordered_groups.values()
        )
        / len(ordered_groups)
        if ordered_groups
        else None
    )
    all_repeats_success_rate = (
        sum(
            all(case.benchmark_status == "PASS" for case in group)
            for group in ordered_groups.values()
        )
        / len(ordered_groups)
        if ordered_groups
        else None
    )
    successful = sum(case.benchmark_status == "PASS" for case in attempted)
    functional = [
        case
        for case in attempted
        if case.functional_status in {"PASSED", "ASSERTION_FAILED"}
    ]
    route_observed = [case for case in attempted if case.route_observed]
    quality = [case for case in attempted if case.judge.status == "available"]
    provider_errors = sum(case.outcome == "provider_error" for case in attempted)
    execution_errors = sum(
        case.outcome == "execution_error"
        or (case.benchmark_status == "ERROR" and case.outcome is None)
        for case in attempted
    )
    step_values = [case.step_count for case in attempted if case.step_count is not None]
    token_unknown_runs = sum(
        case.usage.model_calls > 0 and case.usage.model_tokens is None
        for case in attempted
    )
    token_values = [
        case.usage.model_tokens
        for case in attempted
        if case.usage.model_tokens is not None
    ]
    known_costs = [
        case.usage.estimated_cost_usd
        for case in attempted
        if case.usage.estimated_cost_usd is not None
    ]
    total_model_calls = sum(case.usage.model_calls for case in attempted)
    mean_latency_ms = (
        sum(case.usage.latency_ms for case in attempted) / len(attempted)
        if attempted
        else None
    )
    run_report.aggregates.update(
        {
            "loop_run_count": float(len(attempted)),
            "loop_success_count": float(successful),
            "loop_success_rate": successful / len(attempted) if attempted else None,
            "pass_at_1": pass_at_1,
            "all_repeats_success_rate": all_repeats_success_rate,
            "benchmark_supported_case_count": float(len(attempted)),
            "benchmark_unsupported_case_count": float(
                sum(case.benchmark_status == "UNSUPPORTED" for case in result_cases)
            ),
            "benchmark_ungraded_case_count": float(
                sum(case.benchmark_status == "UNGRADED" for case in result_cases)
            ),
            "benchmark_skipped_case_count": float(
                sum(case.benchmark_status == "SKIP" for case in result_cases)
            ),
            "functional_pass_rate": (
                sum(bool(case.functional_passed) for case in functional)
                / len(functional)
                if functional
                else None
            ),
            "functional_pass_count": float(
                sum(case.functional_status == "PASSED" for case in result_cases)
            ),
            "functional_assertion_failure_count": float(
                sum(
                    case.functional_status == "ASSERTION_FAILED"
                    for case in result_cases
                )
            ),
            "functional_execution_failure_count": float(
                sum(
                    case.functional_status == "EXECUTION_FAILED"
                    for case in result_cases
                )
            ),
            "functional_not_run_count": float(
                sum(case.functional_status == "NOT_RUN" for case in result_cases)
            ),
            "router_accuracy": (
                sum(bool(case.router_match) for case in route_observed)
                / len(route_observed)
                if route_observed
                else None
            ),
            "router_decision_count": float(len(route_observed)),
            "provider_error_rate": (
                provider_errors / len(attempted) if attempted else None
            ),
            "execution_error_rate": (
                execution_errors / len(attempted) if attempted else None
            ),
            "mean_latency_ms": mean_latency_ms,
            "latency_ms": mean_latency_ms,
            "total_model_calls": float(total_model_calls),
            "live_model_case_count": float(
                sum(case.usage.model_calls > 0 for case in attempted)
            ),
            "live_model_call_count": float(total_model_calls),
            "mean_steps": (
                sum(step_values) / len(step_values) if step_values else None
            ),
            "model_tokens": (
                float(sum(token_values))
                if token_unknown_runs == 0 and token_values
                else 0.0
                if not token_unknown_runs and not token_values
                else None
            ),
            "total_tokens": (
                float(sum(token_values))
                if token_unknown_runs == 0 and token_values
                else 0.0
                if not token_unknown_runs and not token_values
                else None
            ),
            "token_unknown_runs": float(token_unknown_runs),
            "total_cost_usd": (
                sum(known_costs)
                if known_costs
                and not any(
                    case.usage.model_calls > 0
                    and (
                        case.usage.estimated_cost_usd is None
                        or case.usage.estimated_cost_unknown_count > 0
                    )
                    for case in attempted
                )
                else 0.0
                if not any(case.usage.model_calls > 0 for case in attempted)
                else None
            ),
            "cost_unknown_runs": float(
                sum(case.usage.estimated_cost_unknown_count > 0 for case in attempted)
            ),
            "quality_run_count": float(len(quality)),
            "quality_pass_rate": (
                sum(bool(case.judge.quality_passed) for case in quality) / len(quality)
                if quality
                else None
            ),
        }
    )
    statuses = {case.benchmark_status for case in result_cases if case.benchmark_status}
    if not attempted:
        run_report.status = "NOT_RUN"
    elif "ERROR" in statuses:
        run_report.status = "ERROR"
    elif "FAIL" in statuses:
        run_report.status = "FAIL"
    elif "UNGRADED" in statuses:
        run_report.status = "UNGRADED"
    elif "UNSUPPORTED" in statuses:
        run_report.status = "UNSUPPORTED"
    elif "PASS" in statuses:
        run_report.status = "PASS"
    else:
        run_report.status = "SKIP"
    return run_report


def _not_run_report(
    config: EvaluationConfig,
    suite: AnimeBenchmarkSuite,
    *,
    selected_ids: set[str],
    suite_name: str,
    reason: str,
    run_id: str,
) -> EvalReport:
    cases = []
    for scenario in suite.cases:
        selected = scenario.id in selected_ids
        unsupported = scenario.id not in SUPPORTED_SCENARIO_IDS
        cases.append(
            _non_run_case(
                scenario,
                case_id=scenario.id,
                status=("UNSUPPORTED" if selected and unsupported else "SKIP"),
                reason=(
                    UNSUPPORTED_SCENARIO_REASONS.get(
                        scenario.id,
                        "No isolated evaluator is implemented for this scenario.",
                    )
                    if selected and unsupported
                    else reason
                    if selected
                    else "not selected"
                ),
            )
        )
    return EvalReport(
        task="ANIME-AGENT-BENCHMARK-V1",
        dataset_version=f"{suite.dataset_version}/{suite_name}",
        dataset_digest=suite.content_digest,
        config_name=config.name,
        code_revision="not-run",
        agent=config.agent,
        completed_at=utc_now(),
        cases=cases,
        aggregates={},
        prompt_version="not-run",
        environment={
            "benchmark_suite": suite_name,
            "benchmark_run_id": run_id,
            "execution_mode": "real-provider-runtime",
            "status_reason": reason,
            "router_enabled": str(config.routing.enabled).lower(),
            "router_version": config.routing.version,
            "fixture_set": "synthetic_v1",
        },
        evaluation_budget={"repeats": 0, "provider_calls": 0},
        status="NOT_RUN",
    )


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    temporary.replace(path)


def _verified_run_count(run_dir: Path) -> int:
    """Count persisted Run IDs that prove an older baseline was executed."""
    run_ids: set[str] = set()
    for filename in ("run-manifest.json", "report.json"):
        path = run_dir / filename
        if not path.is_file():
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(payload, dict):
            continue
        run_index = payload.get("run_index")
        if not isinstance(run_index, list):
            continue
        for entry in run_index:
            if not isinstance(entry, dict):
                continue
            run_id = entry.get("run_id")
            case_id = entry.get("case_id")
            if isinstance(run_id, str) and run_id.strip() and isinstance(case_id, str):
                run_ids.add(run_id)
    return len(run_ids)


def _auto_select_baseline(
    runs_dir: Path,
    current: TrendBaseline,
    *,
    exclude_run_dir: Path,
) -> tuple[Path, TrendBaseline] | None:
    """Find the newest compatible, executed historical run in this suite."""
    candidates: list[tuple[Path, TrendBaseline]] = []
    if current.executed_runs == 0 or not runs_dir.is_dir():
        return None
    for run_dir in runs_dir.iterdir():
        if not run_dir.is_dir() or run_dir.resolve() == exclude_run_dir.resolve():
            continue
        baseline_path = run_dir / "current-baseline.json"
        if not baseline_path.is_file():
            continue
        try:
            baseline = TrendBaseline.model_validate_json(
                baseline_path.read_text(encoding="utf-8")
            )
        except (OSError, ValueError):
            continue
        if baseline.executed_runs == 0:
            verified_runs = _verified_run_count(run_dir)
            if verified_runs:
                baseline = baseline.model_copy(update={"executed_runs": verified_runs})
        candidates.append((baseline_path, baseline))
    return select_compatible_baseline(candidates, current)


def _markdown_cell(value: Any) -> str:
    return (
        str(value if value is not None else "unknown")
        .replace("|", "\\|")
        .replace("\n", " ")
    )


def _artifact_markdown_link(path: str | None, report_dir: Path) -> str:
    if not path:
        return "-"
    relative = Path(os.path.relpath(path, start=report_dir)).as_posix()
    return f"[open]({relative})"


def write_anime_markdown_report(report: EvalReport, path: str | Path) -> Path:
    """Write a readable, credential-free summary with direct case artifacts."""
    report_path = Path(path)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    rows = [
        "# Anime Agent Benchmark v1",
        "",
        f"- Status: **{report.status or 'unknown'}**",
        "- JSON report: [`report.json`](report.json)",
        f"- Provider / model: `{report.agent.provider}` / `{report.agent.model}`",
        f"- Dataset: `{report.dataset_version}` (`{report.dataset_digest}`)",
        f"- Code revision: `{report.code_revision}`",
        f"- Prompt version: `{report.prompt_version}`",
        f"- Router: `{report.environment.get('router_version', 'unknown')}` "
        f"(enabled={report.environment.get('router_enabled', 'unknown')})",
        "",
        "## Run metrics",
        "",
        "| Metric | Value |",
        "| --- | ---: |",
    ]
    metrics = (
        "loop_success_rate",
        "pass_at_1",
        "all_repeats_success_rate",
        "functional_pass_rate",
        "functional_pass_count",
        "functional_assertion_failure_count",
        "functional_execution_failure_count",
        "functional_not_run_count",
        "router_accuracy",
        "quality_pass_rate",
        "provider_error_rate",
        "execution_error_rate",
        "mean_steps",
        "mean_latency_ms",
        "total_model_calls",
        "total_tokens",
        "total_cost_usd",
    )
    rows.extend(
        f"| `{name}` | {_markdown_cell(report.aggregates.get(name))} |"
        for name in metrics
    )
    baseline = report.baseline_comparison or {}
    rows.extend(
        [
            "",
            "## Baseline comparison",
            "",
            f"- Status: `{_markdown_cell(baseline.get('status'))}`",
            f"- Baseline: {_artifact_markdown_link(baseline.get('path'), report_path.parent)}",
        ]
    )
    if baseline.get("reason"):
        rows.append(f"- Note: {_markdown_cell(baseline['reason'])}")
    provenance_changes = baseline.get("provenance_changes") or []
    if provenance_changes:
        rows.extend(["", "### Provenance changes", ""])
        rows.extend(f"- {_markdown_cell(change)}" for change in provenance_changes)
    blockers = baseline.get("comparison_blockers") or []
    if blockers:
        rows.extend(["", "### Comparison blockers", ""])
        rows.extend(f"- {_markdown_cell(blocker)}" for blocker in blockers)
    regressions = baseline.get("regressions") or []
    if regressions:
        rows.extend(["", "### Regressions", ""])
        rows.extend(f"- {_markdown_cell(item)}" for item in regressions)
    improvements = baseline.get("improvements") or []
    if improvements:
        rows.extend(["", "### Improvements", ""])
        rows.extend(f"- {_markdown_cell(item)}" for item in improvements)
    rows.extend(
        [
            "",
            "## Cases",
            "",
            "| Case | Status | Functional | Quality | Router | Provider error | Transcript | Trace |",
            "| --- | --- | --- | --- | --- | --- | --- | --- |",
        ]
    )
    for case in report.cases:
        rows.append(
            "| `{case_id}` | {status} | {functional} | {quality} | {router} | "
            "{provider_error} | {transcript} | {trace} |".format(
                case_id=_markdown_cell(case.case_id),
                status=_markdown_cell(case.benchmark_status),
                functional=_markdown_cell(case.functional_status),
                quality=_markdown_cell(case.quality_status),
                router=(
                    _markdown_cell(case.router_match)
                    if case.router_expected_agent is not None
                    else "-"
                ),
                provider_error=_markdown_cell(
                    _provider_failure_summary(case.provider_failure)
                ),
                transcript=_artifact_markdown_link(
                    case.transcript_path, report_path.parent
                ),
                trace=_artifact_markdown_link(case.trace_path, report_path.parent),
            )
        )
        for check in case.hard_checks:
            rows.append(
                f"\n  - `{_markdown_cell(check.rule)}`: "
                f"**{_markdown_cell(check.status)}** — {_markdown_cell(check.detail)}"
            )
        if case.error:
            rows.append(f"\n  - Error: {_markdown_cell(case.error)}")
    for heading, failures in (
        ("Gate failures", report.gate_failures),
        ("Baseline findings", report.baseline_failures),
    ):
        if failures:
            rows.extend(["", f"## {heading}", ""])
            rows.extend(f"- {_markdown_cell(item)}" for item in failures)
    rows.append("")
    temporary = report_path.with_suffix(report_path.suffix + ".tmp")
    temporary.write_text("\n".join(rows), encoding="utf-8")
    temporary.replace(report_path)
    return report_path


def _provider_failure_summary(failure: dict[str, Any] | None) -> str | None:
    if not failure:
        return None
    fields = [
        failure.get("category"),
        failure.get("exception_type"),
        f"HTTP {failure['http_status']}" if failure.get("http_status") else None,
        f"stage={failure.get('call_stage')}" if failure.get("call_stage") else None,
    ]
    response_detail = failure.get("response_detail")
    if isinstance(response_detail, dict):
        fields.extend(
            f"{key}={value}"
            for key, value in sorted(response_detail.items())
            if key in {"code", "type", "param"} and isinstance(value, str)
        )
    return "; ".join(str(value) for value in fields if value)


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run OtakuNeko Anime Agent Benchmark v1 with a real Provider"
    )
    parser.add_argument("--provider", choices=["real"], required=True)
    parser.add_argument("--isolated", action="store_true", required=True)
    parser.add_argument("--suite", choices=["smoke", "regression"], default="smoke")
    parser.add_argument("--config", default=DEFAULT_CONFIG)
    parser.add_argument("--package-dir", default=DEFAULT_PACKAGE)
    parser.add_argument("--case", action="append", dest="case_ids")
    parser.add_argument("--repeats", type=int, default=1)
    parser.add_argument("--baseline")
    parser.add_argument("--update-baseline", action="store_true")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--model")
    parser.add_argument("--base-url")
    parser.add_argument("--temperature", type=float, default=0)
    parser.add_argument("--human-reviews")
    parser.add_argument("--output-dir")
    parser.add_argument("--run-id")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv if argv is not None else sys.argv[1:])
    try:
        if args.repeats < 1:
            raise ValueError("--repeats must be positive")
        if args.update_baseline and not args.baseline:
            raise ValueError("--update-baseline requires --baseline")
        config = load_config(args.config)
        if args.model:
            config.agent = config.agent.model_copy(update={"model": args.model})
        if args.human_reviews:
            config.human_reviews = args.human_reviews
        suite = load_anime_benchmark_suite(args.package_dir)
        selected_ids, base_dataset = select_scenarios(
            suite,
            suite_name=args.suite,
            case_ids=args.case_ids,
        )
        dataset = (
            base_dataset
            if args.repeats == 1
            else expand_repeats(base_dataset, args.repeats)
        )
        baseline_path = Path(args.baseline) if args.baseline else None
        baseline: TrendBaseline | None = None
        if baseline_path is not None:
            if baseline_path.exists() and baseline_path.is_dir():
                raise ValueError("baseline path must be a file")
            if args.update_baseline:
                if baseline_path.exists() and not args.force:
                    raise ValueError("baseline already exists; pass --force to replace")
            else:
                if not baseline_path.is_file():
                    raise ValueError("baseline missing")
                baseline = TrendBaseline.model_validate_json(
                    baseline_path.read_text(encoding="utf-8")
                )

        run_id = (
            args.run_id
            or datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            + "-"
            + uuid4().hex[:8]
        )
        if not _RUN_ID_PATTERN.fullmatch(run_id) or run_id in {".", ".."}:
            raise ValueError("run id must match [A-Za-z0-9._-]+")
        base_dir = (
            Path(args.output_dir)
            if args.output_dir
            else Path(config.report_path).parent / config.name / "runs"
        )
        run_dir = base_dir / run_id
        if run_dir.exists():
            raise ValueError("run directory already exists")
        run_dir.mkdir(parents=True)
        transcript_dir = run_dir / "transcripts"
        config.transcript_dir = str(transcript_dir)
        report_path = run_dir / "report.json"

        try:
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
                anime_benchmark_suite=suite,
            )
        except ProviderCredentialsUnavailable:
            report = _not_run_report(
                config,
                suite,
                selected_ids=selected_ids,
                suite_name=args.suite,
                reason="real Provider credentials are not configured",
                run_id=run_id,
            )
            write_report(report, report_path)
            markdown_report_path = write_anime_markdown_report(
                report, run_dir / "report.md"
            )
            _write_json(
                run_dir / "run-manifest.json",
                {
                    "run_id": run_id,
                    "status": "NOT_RUN",
                    "provider_calls": 0,
                    "report": str(report_path),
                    "markdown_report": str(markdown_report_path),
                    "reason": "real Provider credentials are not configured",
                },
            )
            print(
                f"anime benchmark NOT_RUN: real Provider credentials unavailable; report={report_path}",
                file=sys.stderr,
            )
            return 2

        if args.base_url:
            os.environ["OPENAI_BASE_URL"] = args.base_url
        judge = (
            build_component(config.judge_factory, config)
            if config.judge_factory
            else None
        )
        thresholds = config.thresholds
        config.thresholds = {}
        try:
            run_report = asyncio.run(
                run_evaluation(config, dataset, target, judge=judge)
            )
        finally:
            config.thresholds = thresholds
        report = assemble_anime_report(
            run_report,
            suite,
            selected_ids=selected_ids,
            suite_name=args.suite,
            repeats=args.repeats,
            run_id=run_id,
        )
        if config.runtime_budget is not None:
            report.evaluation_budget.update(
                {
                    "max_model_calls_per_case": config.runtime_budget.max_model_calls,
                    "deadline_seconds_per_case": config.runtime_budget.deadline_seconds,
                    "max_total_tokens_per_case": config.runtime_budget.max_total_tokens,
                    "max_cost_usd_per_case": config.runtime_budget.max_cost_usd,
                }
            )
        report.gate_failures = evaluate_gate(config, report.aggregates)

        current = build_baseline(report, repeats=args.repeats)
        _write_json(run_dir / "current-baseline.json", current.model_dump(mode="json"))
        diff: TrendDiff | None = None
        baseline_status = "unavailable"
        baseline_reason = "no compatible executed historical baseline was found"
        if args.update_baseline:
            if (
                report.gate_failures
                or report.status not in {"PASS", "UNSUPPORTED"}
                or not report.aggregates.get("loop_run_count")
            ):
                baseline_status = "refused"
                baseline_reason = (
                    "baseline update requires an attempted passing benchmark"
                )
                report.baseline_failures = [
                    "baseline update refused without an attempted, passing benchmark"
                ]
            elif baseline_path is not None:
                _write_json(baseline_path, current.model_dump(mode="json"))
                baseline_status = "updated"
                baseline_reason = "baseline file updated; no trend comparison was run"
        else:
            if baseline_path is None:
                selected_baseline = _auto_select_baseline(
                    base_dir,
                    current,
                    exclude_run_dir=run_dir,
                )
                if selected_baseline is not None:
                    baseline_path, baseline = selected_baseline
            if (
                baseline_path is not None
                and baseline is not None
                and current.executed_runs > 0
            ):
                baseline_reason = "compatible baseline comparison completed"
                baseline_status = "compared"
            if (
                baseline_path is not None
                and baseline is not None
                and current.executed_runs > 0
            ):
                diff = compare_baseline(
                    baseline,
                    current,
                    tolerance=TrendTolerance(),
                    baseline_path=str(baseline_path),
                )
                if diff.comparison_compatible:
                    report.baseline_failures = diff.version_failures + diff.regressions
                else:
                    baseline_status = "incompatible"
                    baseline_reason = (
                        "baseline provenance is incompatible; no trend claim was made"
                    )
            elif baseline_path is not None and current.executed_runs == 0:
                baseline_status = "unavailable"
                baseline_reason = "current run has no persisted Runtime Run to compare"
            elif baseline_path is not None:
                baseline_status = "unavailable"
                baseline_reason = "selected baseline could not be loaded"

        report.baseline_comparison = {
            "status": baseline_status,
            "reason": baseline_reason,
            "path": str(baseline_path) if baseline_path else None,
            "comparison_compatible": (
                diff.comparison_compatible if diff is not None else None
            ),
            "comparison_blockers": (
                diff.comparison_blockers if diff is not None else []
            ),
            "provenance_changes": (diff.provenance_changes if diff is not None else []),
            "regressions": (
                diff.regressions
                if diff is not None and diff.comparison_compatible
                else []
            ),
            "improvements": (
                diff.improvements
                if diff is not None and diff.comparison_compatible
                else []
            ),
        }

        if report.gate_failures or report.baseline_failures:
            report.status = "FAIL"

        write_report(report, report_path)
        markdown_report_path = write_anime_markdown_report(
            report, run_dir / "report.md"
        )
        trend_payload = {
            "schema_version": 1,
            "run_id": run_id,
            "status": report.status,
            "report": str(report_path),
            "markdown_report": str(markdown_report_path),
            "current_baseline": str(run_dir / "current-baseline.json"),
            "baseline": str(baseline_path) if baseline_path else None,
            "baseline_status": baseline_status,
            "baseline_reason": baseline_reason,
            "baseline_comparison": report.baseline_comparison,
            "diff": diff.model_dump(mode="json") if diff is not None else None,
            "gate_failures": report.gate_failures,
            "baseline_failures": report.baseline_failures,
            "aggregates": report.aggregates,
        }
        _write_json(run_dir / "trend-report.json", trend_payload)
        _write_json(
            run_dir / "run-manifest.json",
            {
                "run_id": run_id,
                "status": report.status,
                "dataset_version": report.dataset_version,
                "dataset_digest": report.dataset_digest,
                "model": report.agent.model,
                "provider": report.agent.provider,
                "provider_calls": int(
                    report.aggregates.get("live_model_call_count") or 0
                ),
                "report": str(report_path),
                "markdown_report": str(markdown_report_path),
                "transcripts": str(transcript_dir),
                "run_index": [
                    entry.model_dump(mode="json") for entry in report.run_index
                ],
                "aggregates": report.aggregates,
            },
        )
        print(
            "Anime Agent Benchmark v1: "
            f"status={report.status} cases={report.total} "
            f"loop_success_rate={report.aggregates.get('loop_success_rate')} "
            f"router_accuracy={report.aggregates.get('router_accuracy')} "
            f"provider_errors={report.aggregates.get('provider_error_rate')} "
            f"report={report_path}",
            file=sys.stderr,
        )
        return 1 if report.status in {"FAIL", "ERROR", "UNGRADED", "UNSUPPORTED"} else 0
    except ProviderEndpointError as exc:
        print(f"provider endpoint rejected: {exc.provider_error_code}", file=sys.stderr)
        return 2
    except Exception as exc:
        print(safe_error(exc, "anime_benchmark_failed"), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

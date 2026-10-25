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


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class TrendCaseBaseline(_StrictModel):
    case_id: str
    runs: int = Field(ge=1)
    functional_runs: int = Field(ge=0)
    functional_pass_rate: float = Field(ge=0, le=1)
    pass_rate_variance: float = Field(ge=0, le=1)
    mean_scores: dict[str, float] = Field(default_factory=dict)
    score_stddev: dict[str, float] = Field(default_factory=dict)
    mean_latency_ms: float = Field(default=0, ge=0)
    latency_stddev_ms: float = Field(default=0, ge=0)
    mean_tokens: float | None = Field(default=None, ge=0)
    tokens_stddev: float | None = Field(default=None, ge=0)
    mean_cost_usd: float | None = Field(default=None, ge=0)
    cost_stddev: float | None = Field(default=None, ge=0)
    provider_error_rate: float = Field(default=0, ge=0, le=1)


class TrendTotals(_StrictModel):
    cases: int = Field(ge=0)
    runs: int = Field(ge=0)
    functional_runs: int = Field(ge=0)
    functional_pass_rate: float = Field(ge=0, le=1)
    pass_rate_variance: float = Field(ge=0, le=1)
    mean_latency_ms: float = Field(default=0, ge=0)
    total_tokens: float | None = Field(default=None, ge=0)
    total_cost_usd: float | None = Field(default=None, ge=0)
    provider_error_rate: float = Field(default=0, ge=0, le=1)


class TrendBaseline(_StrictModel):
    schema_version: int = 1
    dataset_version: str
    dataset_digest: str
    repeats: int = Field(ge=1)
    model: str
    provider: str
    prompt_version: str
    code_revision: str
    created_at: datetime
    cases: dict[str, TrendCaseBaseline] = Field(default_factory=dict)
    totals: TrendTotals


class TrendTolerance(_StrictModel):
    max_pass_rate_drop: float = Field(default=0.1, ge=0, le=1)
    max_score_drop: float = Field(default=0.1, ge=0, le=1)
    max_latency_increase_pct: float = Field(default=0.5, ge=0)
    max_token_increase_pct: float = Field(default=0.5, ge=0)
    max_cost_increase_pct: float = Field(default=0.5, ge=0)
    max_provider_error_increase: float = Field(default=0.1, ge=0, le=1)


class CostTrend(_StrictModel):
    previous_repeats: int | None = None
    current_repeats: int = Field(ge=1)
    previous_functional_pass_rate: float | None = None
    current_functional_pass_rate: float = Field(ge=0, le=1)
    previous_mean_latency_ms: float | None = None
    current_mean_latency_ms: float = Field(default=0, ge=0)
    previous_total_tokens: float | None = None
    current_total_tokens: float | None = None
    previous_total_cost_usd: float | None = None
    current_total_cost_usd: float | None = None
    delta_pass_rate: float | None = None
    delta_latency_pct: float | None = None
    delta_tokens_pct: float | None = None
    delta_cost_pct: float | None = None


class TrendDiff(_StrictModel):
    schema_version: int = 1
    baseline: str | None = None
    version_failures: list[str] = Field(default_factory=list)
    regressions: list[str] = Field(default_factory=list)
    improvements: list[str] = Field(default_factory=list)
    added: list[str] = Field(default_factory=list)
    missing: list[str] = Field(default_factory=list)
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


def _case_baseline(case_id: str, results: list[CaseResult]) -> TrendCaseBaseline:
    functional = [
        result
        for result in results
        if result.outcome in {"passed", "functional_failure"}
    ]
    passed = [1.0 if result.outcome == "passed" else 0.0 for result in functional]
    pass_rate = statistics.mean(passed) if passed else 0.0
    variance = pass_rate * (1 - pass_rate)

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
    token_values = [
        float(result.usage.model_tokens)
        for result in results
        if result.usage.model_tokens is not None
    ]
    cost_values = [
        result.usage.estimated_cost_usd
        for result in results
        if result.usage.estimated_cost_usd is not None
    ]
    token_mean, token_stddev = _mean_std(token_values) if token_values else (None, None)
    cost_mean, cost_stddev = _mean_std(cost_values) if cost_values else (None, None)
    provider_errors = sum(1 for result in results if result.outcome == "provider_error")
    return TrendCaseBaseline(
        case_id=case_id,
        runs=len(results),
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
    )


def build_baseline(report: EvalReport, *, repeats: int) -> TrendBaseline:
    groups: dict[str, list[CaseResult]] = defaultdict(list)
    for result in report.cases:
        match = _REPEAT_PATTERN.match(result.case_id)
        base = match.group("base") if match else result.case_id
        groups[base].append(result)
    cases = {
        case_id: _case_baseline(case_id, results)
        for case_id, results in sorted(groups.items())
    }
    all_results = report.cases
    functional = [
        result
        for result in all_results
        if result.outcome in {"passed", "functional_failure"}
    ]
    pass_rate = (
        sum(1 for result in functional if result.outcome == "passed") / len(functional)
        if functional
        else 0.0
    )
    latency_mean, _ = _mean_std([result.usage.latency_ms for result in all_results])
    token_values = [
        float(result.usage.model_tokens)
        for result in all_results
        if result.usage.model_tokens is not None
    ]
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
        created_at=datetime.now(timezone.utc),
        cases=cases,
        totals=TrendTotals(
            cases=len(cases),
            runs=len(all_results),
            functional_runs=len(functional),
            functional_pass_rate=pass_rate,
            pass_rate_variance=pass_rate * (1 - pass_rate),
            mean_latency_ms=latency_mean,
            total_tokens=sum(token_values) if token_values else None,
            total_cost_usd=sum(cost_values) if cost_values else None,
            provider_error_rate=(
                sum(1 for result in all_results if result.outcome == "provider_error")
                / len(all_results)
                if all_results
                else 0.0
            ),
        ),
    )


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
    for field in (
        "dataset_version",
        "dataset_digest",
        "repeats",
        "model",
        "provider",
        "prompt_version",
    ):
        previous = getattr(baseline, field)
        actual = getattr(current, field)
        if previous != actual:
            version_failures.append(f"{field}: baseline={previous} current={actual}")

    regressions: list[str] = []
    improvements: list[str] = []
    missing: list[str] = []
    added: list[str] = []
    for case_id, previous in sorted(baseline.cases.items()):
        actual = current.cases.get(case_id)
        if actual is None:
            missing.append(case_id)
            regressions.append(f"{case_id}: missing from current run")
            continue
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
        latency_pct = _pct_increase(actual.mean_latency_ms, previous.mean_latency_ms)
        if latency_pct is not None and latency_pct > tolerance.max_latency_increase_pct:
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
    for case_id in sorted(current.cases):
        if case_id not in baseline.cases:
            added.append(case_id)
    return TrendDiff(
        baseline=baseline_path,
        version_failures=version_failures,
        regressions=regressions,
        improvements=improvements,
        added=added,
        missing=missing,
        cost_trend=CostTrend(
            current_repeats=current.repeats,
            current_functional_pass_rate=current.totals.functional_pass_rate,
            current_mean_latency_ms=current.totals.mean_latency_ms,
            current_total_tokens=current.totals.total_tokens,
            current_total_cost_usd=current.totals.total_cost_usd,
        ),
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
            last = record
    return last


def cost_trend(
    previous: dict[str, Any] | None,
    current: TrendBaseline,
) -> CostTrend:
    if previous is None:
        return CostTrend(
            current_repeats=current.repeats,
            current_functional_pass_rate=current.totals.functional_pass_rate,
            current_mean_latency_ms=current.totals.mean_latency_ms,
            current_total_tokens=current.totals.total_tokens,
            current_total_cost_usd=current.totals.total_cost_usd,
        )
    previous_repeats = previous.get("repeats")
    comparable = previous_repeats == current.repeats
    previous_pass = previous.get("functional_pass_rate")
    previous_latency = previous.get("mean_latency_ms")
    previous_tokens = previous.get("total_tokens")
    previous_cost = previous.get("total_cost_usd")

    def delta_pct(current_value: float | None, previous_value: Any) -> float | None:
        if not comparable or current_value is None:
            return None
        if not isinstance(previous_value, (int, float)) or previous_value <= 0:
            return None
        return (current_value - float(previous_value)) / float(previous_value)

    return CostTrend(
        previous_repeats=previous_repeats
        if isinstance(previous_repeats, int)
        else None,
        current_repeats=current.repeats,
        previous_functional_pass_rate=(
            float(previous_pass) if isinstance(previous_pass, (int, float)) else None
        ),
        current_functional_pass_rate=current.totals.functional_pass_rate,
        previous_mean_latency_ms=(
            float(previous_latency)
            if isinstance(previous_latency, (int, float))
            else None
        ),
        current_mean_latency_ms=current.totals.mean_latency_ms,
        previous_total_tokens=(
            float(previous_tokens)
            if isinstance(previous_tokens, (int, float))
            else None
        ),
        current_total_tokens=current.totals.total_tokens,
        previous_total_cost_usd=(
            float(previous_cost) if isinstance(previous_cost, (int, float)) else None
        ),
        current_total_cost_usd=current.totals.total_cost_usd,
        delta_pass_rate=(
            (current.totals.functional_pass_rate - float(previous_pass))
            if isinstance(previous_pass, (int, float))
            else None
        ),
        delta_latency_pct=delta_pct(current.totals.mean_latency_ms, previous_latency),
        delta_tokens_pct=delta_pct(current.totals.total_tokens, previous_tokens),
        delta_cost_pct=delta_pct(current.totals.total_cost_usd, previous_cost),
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
        "schema_version": 1,
        "run_id": run_id,
        "recorded_at": datetime.now(timezone.utc).isoformat(),
        "dataset_version": current.dataset_version,
        "dataset_digest": current.dataset_digest,
        "repeats": current.repeats,
        "model": current.model,
        "provider": current.provider,
        "prompt_version": current.prompt_version,
        "code_revision": current.code_revision,
        "functional_pass_rate": current.totals.functional_pass_rate,
        "pass_rate_variance": current.totals.pass_rate_variance,
        "mean_latency_ms": current.totals.mean_latency_ms,
        "total_tokens": current.totals.total_tokens,
        "total_cost_usd": current.totals.total_cost_usd,
        "provider_error_rate": current.totals.provider_error_rate,
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
        if diff is not None:
            diff = diff.model_copy(update={"cost_trend": trend})
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
                "gate_failures": gate_failures,
                "totals": current.totals.model_dump(mode="json"),
                "history": str(history_path),
            },
        )
        if diff is not None:
            _write_json(output_dir / "trend-diff.json", diff.model_dump(mode="json"))
        print(
            "l6-trend result: "
            f"verdict={verdict} "
            f"pass_rate={current.totals.functional_pass_rate:.1%} "
            f"variance={current.totals.pass_rate_variance:.3f} "
            f"provider_errors={current.totals.provider_error_rate:.1%} "
            f"latency_ms={current.totals.mean_latency_ms:.1f} "
            f"tokens={current.totals.total_tokens} "
            f"cost={current.totals.total_cost_usd} "
            f"regressions={len(diff.regressions) if diff else 0}",
            file=sys.stderr,
        )
        return (
            1
            if gate_failures
            or (diff is not None and (diff.regressions or diff.version_failures))
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

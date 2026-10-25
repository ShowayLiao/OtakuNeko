"""Configuration-driven EVAL-001 runner and CLI."""

from __future__ import annotations

import argparse
import asyncio
import importlib
import platform
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from app.evaluation.adapter import (
    EvaluationTarget,
    RuntimeEvaluationTarget,
)
from app.evaluation.config import EvaluationConfig, load_config
from app.evaluation.dataset import load_dataset
from app.evaluation.errors import safe_error
from app.evaluation.human_review import load_human_reviews
from app.evaluation.judge import (
    Judge,
    JudgeCache,
    JudgeRequest,
    evaluate_judge,
    load_baseline,
    rubric_digest,
)
from app.evaluation.l6_scoring import (
    aggregate_l6_scores,
    l6_execution_error,
    score_l6_case,
)
from app.evaluation.metrics import (
    aggregate_metrics,
    aggregate_observability_snapshots,
    case_passed,
    compute_case_metrics,
    failure_metrics,
    observability_snapshot,
)
from app.evaluation.reporting import write_report
from app.evaluation.scoring import answer_quality_passed, score_deterministic
from app.evaluation.transcript import transcript_path
from app.evaluation.types import (
    CaseResult,
    EvalCase,
    EvalDataset,
    EvalReport,
    HumanReview,
    JudgeOutcome,
    ExecutionResult,
    ReviewQueueEntry,
    RunIndexEntry,
    RunUsage,
)
from app.harness.contracts import CONTRACT_VERSION

__all__ = [
    "RuntimeEvaluationTarget",
    "build_component",
    "evaluate_gate",
    "main",
    "print_report",
    "run_case",
    "run_evaluation",
]


def _git_revision() -> str:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        )
        return result.stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def build_component(factory_path: str, config):
    try:
        module_name, attribute = factory_path.split(":", 1)
        factory = getattr(importlib.import_module(module_name), attribute)
    except (ValueError, ImportError, AttributeError) as exc:
        raise ValueError("invalid evaluation component factory") from exc
    return factory(config)


async def run_case(
    case: EvalCase,
    target: EvaluationTarget,
    *,
    config: EvaluationConfig | None = None,
    judge: Judge | None = None,
    judge_cache: JudgeCache | None = None,
    human_review: HumanReview | None = None,
) -> CaseResult:
    try:
        execution = await target.evaluate(case)
        metrics = compute_case_metrics(case, execution)
        deterministic = score_deterministic(case, execution)
        judge_outcome = JudgeOutcome()
        if config is not None and config.judge.enabled:
            if judge is None:
                judge_outcome = JudgeOutcome(
                    status="unavailable",
                    error="judge implementation unavailable",
                )
            else:
                judge_outcome = await evaluate_judge(
                    judge,
                    JudgeRequest(
                        input_text="\n".join(
                            message.content for message in case.input_messages
                        ),
                        response_text=execution.text,
                        rubric=config.judge.rubric,
                        rubric_version=config.judge.rubric_version,
                        model=config.judge.model,
                        provider=config.judge.provider,
                        config={
                            "dataset_case": case.id,
                        },
                    ),
                    timeout=config.judge.timeout_seconds,
                    cache=judge_cache,
                )
            judge_outcome = judge_outcome.model_copy(
                update={
                    "model": config.judge.model,
                    "provider": config.judge.provider,
                }
            )
        quality_passed = answer_quality_passed(case.answer_quality, judge_outcome)
        if config is not None:
            judge_outcome = judge_outcome.model_copy(
                update={
                    "rubric_version": (
                        judge_outcome.rubric_version or config.judge.rubric_version
                    ),
                    "rubric_digest": (
                        judge_outcome.rubric_digest
                        or rubric_digest(
                            config.judge.rubric,
                            config.judge.rubric_version,
                        )
                    ),
                    "quality_passed": (
                        quality_passed if judge_outcome.status == "available" else None
                    ),
                }
            )
        passed = (
            case_passed(metrics)
            and (deterministic is None or deterministic.task_success)
            and quality_passed is not False
            and execution.artifact_error is None
        )
        l6 = score_l6_case(
            case,
            execution,
            deterministic,
            passed=passed,
        )
        estimated_cost = execution.estimated_cost_usd
        cost_unknown_count = execution.estimated_cost_unknown_count
        if (
            estimated_cost is None
            and config is not None
            and config.cost is not None
            and execution.prompt_tokens is not None
            and execution.completion_tokens is not None
        ):
            estimated_cost = (
                execution.prompt_tokens * config.cost.input_cost_per_million
                + execution.completion_tokens * config.cost.output_cost_per_million
            ) / 1_000_000
            cost_unknown_count = 0
        return CaseResult(
            case_id=case.id,
            category=case.category.value,
            passed=passed,
            actual_route=execution.route,
            capabilities=execution.capabilities,
            metrics=metrics,
            judge=judge_outcome,
            run_id=execution.run_id,
            trace_id=execution.trace_id,
            run_status=execution.run_status,
            terminal_error_code=execution.terminal_error_code,
            termination_reason=execution.termination_reason,
            outcome=l6.outcome,
            step_count=execution.step_count,
            tool_failure_count=execution.tool_failure_count,
            recovered=execution.recovered,
            observability=observability_snapshot(execution),
            artifact_error=execution.artifact_error,
            tool_arguments=execution.tool_arguments,
            tool_argument_keys=execution.tool_argument_keys,
            providers=execution.providers,
            models=execution.models,
            usage=RunUsage(
                model_calls=execution.model_call_count,
                model_tokens=execution.model_tokens,
                prompt_tokens=execution.prompt_tokens,
                completion_tokens=execution.completion_tokens,
                latency_ms=execution.latency_ms,
                estimated_cost_usd=estimated_cost,
                estimated_cost_unknown_count=cost_unknown_count,
            ),
            deterministic=deterministic,
            l6=l6,
            human_review=human_review,
        )
    except Exception as exc:
        metrics = failure_metrics(case)
        failed_execution = ExecutionResult(
            route="",
            schema_valid=False,
            run_status="failed",
        )
        failed_observability = observability_snapshot(failed_execution)
        failed_score = score_deterministic(case, failed_execution)
        if failed_score is not None:
            # An exception means no valid Runtime result exists, so the verdict
            # is failed even if the case expected a failed terminal status.
            failed_score = failed_score.model_copy(update={"task_success": False})
        # The entrypoint target derives both identities from the case id (see
        # entrypoint.run_headless_case). The exception path has no result to
        # read them from, so this best-effort identity localizes the failure;
        # other targets may not persist a trace under it.
        failed_run_id = f"eval-{case.id}"
        l6 = l6_execution_error(case.id)
        return CaseResult(
            case_id=case.id,
            category=case.category.value,
            passed=False,
            metrics=metrics,
            error=safe_error(exc, "execution_failed"),
            run_id=failed_run_id,
            trace_id=failed_run_id,
            run_status="failed",
            outcome=l6.outcome,
            observability=failed_observability,
            deterministic=failed_score,
            l6=l6,
            human_review=human_review,
        )


def evaluate_gate(
    config: EvaluationConfig,
    aggregates: dict[str, float],
) -> list[str]:
    failures: list[str] = []
    for name, threshold in config.thresholds.items():
        if name not in aggregates:
            if threshold.required:
                failures.append(f"missing required metric: {name}")
            continue
        actual = aggregates[name]
        failed = (
            actual < threshold.value
            if threshold.direction == "min"
            else actual > threshold.value
        )
        if failed:
            failures.append(
                f"threshold failed: {name}={actual} "
                f"{threshold.direction}={threshold.value}"
            )
    return failures


def _review_reason(case: CaseResult) -> str | None:
    judge = case.judge
    human = case.human_review
    if judge.status == "unavailable":
        return "judge_unavailable"
    if human is None:
        if judge.quality_passed is False:
            return "quality_failed_without_review"
        return None
    if human.verdict == "needs_discussion":
        return "human_needs_discussion"
    if human.verdict == "accept" and judge.quality_passed is False:
        return "human_accepts_quality_failure"
    if human.verdict == "reject" and judge.quality_passed is True:
        return "human_rejects_quality_pass"
    if judge.rubric_version and human.rubric_version != judge.rubric_version:
        return "rubric_version_mismatch"
    return None


def build_review_queue(cases: list[CaseResult]) -> list[ReviewQueueEntry]:
    """Cases whose Judge/human conclusion is unresolved or disputed."""
    entries: list[ReviewQueueEntry] = []
    for case in cases:
        reason = _review_reason(case)
        if reason is None:
            continue
        entries.append(
            ReviewQueueEntry(
                case_id=case.case_id,
                run_id=case.run_id,
                trace_id=case.trace_id,
                outcome=case.outcome,
                judge_status=case.judge.status,
                judge_score=case.judge.score,
                quality_passed=case.judge.quality_passed,
                human_verdict=(
                    case.human_review.verdict if case.human_review is not None else None
                ),
                reason=reason,
            )
        )
    return entries


def _attach_transcript_paths(
    results: list[CaseResult],
    config: EvaluationConfig,
) -> list[CaseResult]:
    if not config.transcript_dir:
        return results
    directory = Path(config.transcript_dir)
    attached: list[CaseResult] = []
    for result in results:
        path = transcript_path(directory, result.case_id)
        attached.append(
            result.model_copy(update={"transcript_path": str(path)})
            if path.is_file()
            else result
        )
    return attached


def _build_run_index(
    results: list[CaseResult],
    cases: list[EvalCase],
) -> list[RunIndexEntry]:
    by_id = {case.id: case for case in cases}
    entries: list[RunIndexEntry] = []
    for result in results:
        case = by_id.get(result.case_id)
        entries.append(
            RunIndexEntry(
                case_id=result.case_id,
                run_id=result.run_id,
                trace_id=result.trace_id,
                transcript_path=result.transcript_path,
                message_count=len(case.input_messages) if case is not None else 0,
                run_status=result.run_status,
                outcome=result.outcome,
                provider=result.providers[0] if result.providers else None,
                model=result.models[0] if result.models else None,
                usage=result.usage,
                error=(
                    result.error or result.terminal_error_code or result.artifact_error
                ),
            )
        )
    return entries


def _environment() -> dict[str, str]:
    return {
        "python": platform.python_version(),
        "platform": sys.platform,
        "runner": "app.evaluation.runner",
        "decision_contract": CONTRACT_VERSION,
    }


async def run_evaluation(
    config: EvaluationConfig,
    dataset: EvalDataset,
    target: EvaluationTarget,
    judge: Judge | None = None,
) -> EvalReport:
    started_at = datetime.now(timezone.utc)
    selected = dataset.cases
    if config.tags is not None:
        tags = set(config.tags)
        selected = [case for case in selected if tags & set(case.tags)]

    human_reviews: dict[str, HumanReview] = {}
    if config.human_reviews:
        human_reviews = load_human_reviews(
            config.human_reviews,
            dataset.dataset_version,
        )
        unknown = sorted(set(human_reviews) - {case.id for case in dataset.cases})
        if unknown:
            raise ValueError("unknown human review case: " + ", ".join(unknown))

    judge_cache = JudgeCache() if config.judge.enabled else None
    results = [
        await run_case(
            case,
            target,
            config=config,
            judge=judge,
            judge_cache=judge_cache,
            human_review=human_reviews.get(case.id),
        )
        for case in selected
    ]
    results = _attach_transcript_paths(results, config)
    run_index = _build_run_index(results, selected)
    metrics = [result.metrics for result in results]
    aggregates = aggregate_metrics(metrics)
    aggregates["pass_rate"] = (
        sum(result.passed for result in results) / len(results) if results else 1.0
    )

    safety_results = [result for result in results if result.category == "safety"]
    aggregates["safety_pass_rate"] = (
        sum(result.passed for result in safety_results) / len(safety_results)
        if safety_results
        else 1.0
    )

    judge_scores = [
        result.judge.score
        for result in results
        if result.judge.status == "available" and result.judge.score is not None
    ]
    if judge_scores:
        aggregates["judge_score"] = sum(judge_scores) / len(judge_scores)
    judge_costs = [
        result.judge.cost_usd
        for result in results
        if result.judge.status == "available"
    ]
    if judge_costs:
        aggregates["judge_cost_usd"] = sum(judge_costs)
    quality_values = [
        result.judge.quality_passed
        for result in results
        if result.judge.quality_passed is not None
    ]
    if quality_values:
        aggregates["quality_pass_rate"] = sum(quality_values) / len(quality_values)
    human_results = [
        result.human_review for result in results if result.human_review is not None
    ]
    aggregates["human_review_count"] = float(len(human_results))
    for verdict in ("accept", "reject", "needs_discussion"):
        aggregates[f"human_{verdict}_count"] = float(
            sum(1 for review in human_results if review.verdict == verdict)
        )
    review_queue = build_review_queue(results)
    aggregates["review_queue_count"] = float(len(review_queue))
    aggregates["quality_human_disagreement_count"] = float(
        sum(
            1
            for entry in review_queue
            if entry.reason
            in {
                "human_accepts_quality_failure",
                "human_rejects_quality_pass",
                "rubric_version_mismatch",
            }
        )
    )
    aggregates.update(
        aggregate_observability_snapshots([result.observability for result in results])
    )
    aggregates.update(aggregate_l6_scores(results))
    gate_failures = evaluate_gate(config, aggregates)
    if not results:
        gate_failures.append("no evaluation cases selected")
    if config.judge.required and any(
        result.judge.status != "available" for result in results
    ):
        gate_failures.append("required judge unavailable")
    baseline_failures: list[str] = []
    if config.baseline:
        baseline = load_baseline(config.baseline)
        if baseline is None:
            baseline_failures.append(f"missing baseline: {config.baseline}")
        elif baseline.dataset_version != dataset.dataset_version:
            baseline_failures.append(
                "baseline dataset version mismatch: "
                f"{baseline.dataset_version} != {dataset.dataset_version}"
            )
        else:
            baseline_failures.extend(baseline.compare(aggregates))

    return EvalReport(
        dataset_version=dataset.dataset_version,
        dataset_digest=dataset.content_digest,
        config_name=config.name,
        code_revision=_git_revision(),
        agent=config.agent,
        started_at=started_at,
        completed_at=datetime.now(timezone.utc),
        cases=results,
        aggregates=aggregates,
        review_queue=review_queue,
        run_index=run_index,
        prompt_version=f"decision-contract-{CONTRACT_VERSION}",
        environment=_environment(),
        gate_failures=gate_failures,
        baseline_failures=baseline_failures,
        evaluation_budget={
            "judge_enabled": config.judge.enabled,
            "judge_required": config.judge.required,
            "judge_timeout_seconds": config.judge.timeout_seconds,
            "judge_max_cost_usd": config.judge.max_cost_usd,
            "judge_max_cost_per_call_usd": config.judge.max_cost_per_call_usd,
        },
    )


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="OtakuNeko evaluation runner")
    parser.add_argument(
        "--config",
        default="evals/config/fast.yaml",
        help="Evaluation YAML configuration",
    )
    parser.add_argument("--dataset", help="Override configured dataset path")
    parser.add_argument("--tags", nargs="*", help="Override configured tags")
    parser.add_argument("--report", help="Override JSON report path")
    parser.add_argument(
        "--transcript-dir",
        help="Write per-case redacted transcript artifacts under this directory",
    )
    parser.add_argument("--target-factory", help="module:function target factory")
    parser.add_argument("--judge-factory", help="module:function judge factory")
    parser.add_argument(
        "--human-reviews",
        help="Versioned human review JSON file",
    )
    return parser.parse_args(argv)


def print_report(report: EvalReport, report_path: Path) -> None:
    print("\n" + "=" * 50)
    print(f"EVAL Report: {report.config_name}")
    print(f"  Dataset:   {report.dataset_version}")
    print(f"  Revision:  {report.code_revision}")
    print(f"  Total:     {report.total}")
    print(f"  Passed:    {report.passed_count}")
    print(f"  Failed:    {report.failed_count}")
    print(f"  Pass rate: {report.pass_rate:.1%}")
    print(f"  JSON:      {report_path}")
    functional_rate = report.aggregates.get("l6_functional_pass_rate")
    if functional_rate is not None:
        print(
            "  L6 pass:   "
            f"{functional_rate:.1%} over "
            f"{int(report.aggregates.get('l6_functional_case_count', 0))} cases"
        )
    if "l6_provider_error_count" in report.aggregates:
        print(
            "  L6 errors: "
            f"provider={int(report.aggregates['l6_provider_error_count'])} "
            f"execution={int(report.aggregates.get('l6_execution_error_count', 0))} "
            f"cancelled={int(report.aggregates.get('l6_cancelled_count', 0))}"
        )
    if "quality_pass_rate" in report.aggregates:
        print(
            "  Quality:   "
            f"judge pass={report.aggregates['quality_pass_rate']:.1%} "
            f"score={report.aggregates.get('judge_score', 0):.2f}"
        )
    if "human_review_count" in report.aggregates:
        print(
            "  Human:     "
            f"reviews={int(report.aggregates['human_review_count'])} "
            f"accept={int(report.aggregates.get('human_accept_count', 0))} "
            f"reject={int(report.aggregates.get('human_reject_count', 0))} "
            f"discuss={int(report.aggregates.get('human_needs_discussion_count', 0))} "
            f"queue={int(report.aggregates.get('review_queue_count', 0))}"
        )
    print("=" * 50)
    for failure in report.gate_failures + report.baseline_failures:
        print(f"  [GATE] {failure}")
    for case in report.cases:
        if not case.passed:
            outcome = f" ({case.outcome})" if case.outcome else ""
            print(f"  [FAIL] {case.case_id}{outcome}: {case.error or 'metric failure'}")
    print()


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv if argv is not None else sys.argv[1:])
    try:
        config = load_config(args.config)
        if args.dataset:
            config.dataset = args.dataset
        if args.tags is not None:
            config.tags = args.tags
        if args.transcript_dir:
            config.transcript_dir = args.transcript_dir
        if args.human_reviews:
            config.human_reviews = args.human_reviews
        dataset = load_dataset(config.dataset)
        target_factory = args.target_factory or config.target_factory
        target = (
            build_component(target_factory, config)
            if target_factory
            else RuntimeEvaluationTarget()
        )
        judge_factory = args.judge_factory or config.judge_factory
        judge = build_component(judge_factory, config) if judge_factory else None
        report = asyncio.run(run_evaluation(config, dataset, target, judge=judge))
        report_path = write_report(
            report,
            args.report or config.report_path,
        )
    except Exception as exc:
        print(safe_error(exc, "configuration_invalid"), file=sys.stderr)
        return 2
    print_report(report, report_path)
    return 1 if report.gate_failures or report.baseline_failures else 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Configuration-driven EVAL-001 runner and CLI."""

from __future__ import annotations

import argparse
import asyncio
import importlib
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
from app.evaluation.judge import (
    Judge,
    JudgeCache,
    JudgeRequest,
    evaluate_judge,
    load_baseline,
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
from app.evaluation.types import (
    CaseResult,
    EvalCase,
    EvalDataset,
    EvalReport,
    JudgeOutcome,
    ExecutionResult,
)

__all__ = [
    "RuntimeEvaluationTarget",
    "build_component",
    "evaluate_gate",
    "main",
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
) -> CaseResult:
    try:
        execution = await target.evaluate(case)
        metrics = compute_case_metrics(case, execution)
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
                            message.content
                            for message in case.input_messages
                        ),
                        response_text=execution.text,
                        rubric={
                            "quality": "Score response quality from 0 to 1",
                        },
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
        return CaseResult(
            case_id=case.id,
            category=case.category.value,
            passed=case_passed(metrics),
            actual_route=execution.route,
            capabilities=execution.capabilities,
            metrics=metrics,
            judge=judge_outcome,
            run_id=execution.run_id,
            observability=observability_snapshot(execution),
            tool_argument_keys=execution.tool_argument_keys,
            providers=execution.providers,
            models=execution.models,
        )
    except Exception as exc:
        metrics = failure_metrics(case)
        failed_observability = observability_snapshot(
            ExecutionResult(
                route="",
                schema_valid=False,
                run_status="failed",
            )
        )
        return CaseResult(
            case_id=case.id,
            category=case.category.value,
            passed=False,
            metrics=metrics,
            error=safe_error(exc, "execution_failed"),
            observability=failed_observability,
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

    judge_cache = JudgeCache() if config.judge.enabled else None
    results = [
        await run_case(
            case,
            target,
            config=config,
            judge=judge,
            judge_cache=judge_cache,
        )
        for case in selected
    ]
    metrics = [result.metrics for result in results]
    aggregates = aggregate_metrics(metrics)
    aggregates["pass_rate"] = (
        sum(result.passed for result in results) / len(results)
        if results
        else 1.0
    )

    safety_results = [
        result for result in results if result.category == "safety"
    ]
    aggregates["safety_pass_rate"] = (
        sum(result.passed for result in safety_results) / len(safety_results)
        if safety_results
        else 1.0
    )

    judge_scores = [
        result.judge.score
        for result in results
        if result.judge.status == "available"
        and result.judge.score is not None
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
    aggregates.update(
        aggregate_observability_snapshots(
            [result.observability for result in results]
        )
    )
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
        config_name=config.name,
        code_revision=_git_revision(),
        agent=config.agent,
        started_at=started_at,
        completed_at=datetime.now(timezone.utc),
        cases=results,
        aggregates=aggregates,
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
    parser.add_argument("--target-factory", help="module:function target factory")
    parser.add_argument("--judge-factory", help="module:function judge factory")
    return parser.parse_args(argv)


def _print_report(report: EvalReport, report_path: Path) -> None:
    print("\n" + "=" * 50)
    print(f"EVAL Report: {report.config_name}")
    print(f"  Dataset:   {report.dataset_version}")
    print(f"  Revision:  {report.code_revision}")
    print(f"  Total:     {report.total}")
    print(f"  Passed:    {report.passed_count}")
    print(f"  Failed:    {report.failed_count}")
    print(f"  Pass rate: {report.pass_rate:.1%}")
    print(f"  JSON:      {report_path}")
    print("=" * 50)
    for failure in report.gate_failures + report.baseline_failures:
        print(f"  [GATE] {failure}")
    for case in report.cases:
        if not case.passed:
            print(f"  [FAIL] {case.case_id}: {case.error or 'metric failure'}")
    print()


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv if argv is not None else sys.argv[1:])
    try:
        config = load_config(args.config)
        if args.dataset:
            config.dataset = args.dataset
        if args.tags is not None:
            config.tags = args.tags
        dataset = load_dataset(config.dataset)
        target_factory = args.target_factory or config.target_factory
        target = (
            build_component(target_factory, config)
            if target_factory
            else RuntimeEvaluationTarget()
        )
        judge_factory = args.judge_factory or config.judge_factory
        judge = (
            build_component(judge_factory, config)
            if judge_factory
            else None
        )
        report = asyncio.run(run_evaluation(config, dataset, target, judge=judge))
        report_path = write_report(
            report,
            args.report or config.report_path,
        )
    except Exception as exc:
        print(safe_error(exc, "configuration_invalid"), file=sys.stderr)
        return 2
    _print_report(report, report_path)
    return 1 if report.gate_failures or report.baseline_failures else 0


if __name__ == "__main__":
    raise SystemExit(main())

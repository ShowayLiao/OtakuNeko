"""PR benchmark gate over the versioned L5 datasets.

Runs the deterministic L5 configurations through the real Runtime entrypoint,
enforces their thresholds, compares per-case outcomes with the committed
baseline, and writes machine-readable reports that locate a failure to its
case, run and trace.
"""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
import platform
import sys
from typing import Any

from app.evaluation.adapter import RuntimeEvaluationTarget
from app.evaluation.config import load_config
from app.evaluation.dataset import load_dataset
from app.evaluation.runner import build_component, run_evaluation
from app.evaluation.types import EvalReport
from app.harness.contracts import CONTRACT_VERSION

DEFAULT_CONFIGS = (
    "evals/config/l5-contract.yaml",
    "evals/config/l5-scenarios.yaml",
)
DEFAULT_BASELINE = "evals/baselines/v1-l5-gate.json"
DEFAULT_REPORT = ".runtime/evaluation/l5-gate.json"
DEFAULT_DIFF = ".runtime/evaluation/l5-gate-diff.json"
SCHEMA_VERSION = 2
DEFAULT_THRESHOLDS: dict[str, Any] = {
    "max_step_increase": 0,
    "max_tool_error_increase": 0,
    "max_token_increase": 0,
    "require_termination_match": True,
    "require_recovery_match": True,
}


def _dimension_passed(case: Any, dimension: str) -> bool | None:
    score = case.deterministic
    if score is None:
        return None
    for item in score.dimensions:
        if item.dimension == dimension:
            return item.passed
    return None


def _behavior(case: Any) -> dict[str, Any]:
    tool_checks = [
        _dimension_passed(case, "required_tools"),
        _dimension_passed(case, "forbidden_tools"),
    ]
    tool_accuracy = (
        None
        if any(check is None for check in tool_checks)
        else (1.0 if all(tool_checks) else 0.0)
    )
    argument = _dimension_passed(case, "arguments")
    return {
        "success": bool(
            case.deterministic.task_success
            if case.deterministic is not None
            else case.passed
        ),
        "tool_accuracy": tool_accuracy,
        "argument_accuracy": (None if argument is None else (1.0 if argument else 0.0)),
        "steps": case.step_count,
        "tokens": int(case.observability.get("model_tokens", 0)),
        "tool_errors": case.tool_failure_count,
        "termination": case.run_status,
        "recovery": case.recovered,
    }


def _versions(reports: dict[str, EvalReport]) -> dict[str, Any]:
    first = next(iter(reports.values()))
    return {
        "dataset": {name: report.dataset_version for name, report in reports.items()},
        "model": {name: report.agent.model for name, report in reports.items()},
        "prompt": f"decision-contract-{CONTRACT_VERSION}",
        "code": first.code_revision,
        "environment": {
            "python": platform.python_version(),
            "platform": sys.platform,
            "providers": {
                name: report.agent.provider for name, report in reports.items()
            },
            "runner": "app.evaluation.l5_gate",
        },
    }


def _case_record(config_name: str, case: Any) -> dict[str, Any]:
    score = case.deterministic
    failed_dimensions = [
        {"dimension": item.dimension, "detail": item.detail}
        for item in (score.dimensions if score is not None else [])
        if not item.passed
    ]
    return {
        "config": config_name,
        "case_id": case.case_id,
        "passed": case.passed,
        "task_success": score.task_success if score is not None else None,
        "run_id": case.run_id,
        "trace_id": case.trace_id,
        "failed_dimensions": failed_dimensions,
        "error": case.error,
        "actual_route": case.actual_route,
        "capabilities": case.capabilities,
        "behavior": _behavior(case),
    }


def build_gate_report(reports: dict[str, EvalReport]) -> dict[str, Any]:
    cases = [
        _case_record(name, case)
        for name, report in reports.items()
        for case in report.cases
    ]
    ids = [case["case_id"] for case in cases]
    duplicates = sorted({case_id for case_id in ids if ids.count(case_id) > 1})
    failed_cases = [case["case_id"] for case in cases if not case["passed"]]
    threshold_failures = [
        f"{name}: {failure}"
        for name, report in reports.items()
        for failure in report.gate_failures
    ]
    total = sum(report.total for report in reports.values())
    return {
        "schema_version": SCHEMA_VERSION,
        "passed": bool(cases)
        and not failed_cases
        and not duplicates
        and not threshold_failures,
        "case_count": len(cases),
        "total_cases": total,
        "failed_cases": failed_cases,
        "duplicate_cases": duplicates,
        "threshold_failures": threshold_failures,
        "baseline_failures": [],
        "versions": _versions(reports) if reports else {},
        "cases": cases,
    }


def baseline_from_report(report: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "versions": report["versions"],
        "thresholds": dict(DEFAULT_THRESHOLDS),
        "cases": {
            case["case_id"]: {
                "passed": case["passed"],
                "task_success": case["task_success"],
                "behavior": case["behavior"],
            }
            for case in report["cases"]
        },
    }


def load_baseline(path: str | Path) -> dict[str, Any] | None:
    baseline_path = Path(path)
    if not baseline_path.is_file():
        return None
    try:
        data = json.loads(baseline_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError("invalid L5 gate baseline") from exc
    if not isinstance(data, dict) or data.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("invalid L5 gate baseline")
    cases = data.get("cases")
    if not isinstance(cases, dict) or not cases:
        raise ValueError("invalid L5 gate baseline")
    if any(not isinstance(record, dict) for record in cases.values()):
        raise ValueError("invalid L5 gate baseline")
    if not isinstance(data.get("versions"), dict):
        raise ValueError("invalid L5 gate baseline")
    if not isinstance(data.get("thresholds"), dict):
        raise ValueError("invalid L5 gate baseline")
    return data


def _behavior_regressions(
    case_id: str,
    previous: dict[str, Any],
    case: dict[str, Any],
    thresholds: dict[str, Any],
) -> list[dict[str, Any]]:
    baseline_behavior = previous.get("behavior") or {}
    current_behavior = case.get("behavior") or {}
    regressions: list[dict[str, Any]] = []

    def add(metric: str, baseline: Any, current: Any) -> None:
        regressions.append(
            {
                "case_id": case_id,
                "metric": metric,
                "baseline": baseline,
                "current": current,
            }
        )

    for metric in ("tool_accuracy", "argument_accuracy"):
        baseline_value = baseline_behavior.get(metric)
        current_value = current_behavior.get(metric)
        if (
            baseline_value is not None
            and current_value is not None
            and current_value < baseline_value
        ):
            add(metric, baseline_value, current_value)
    for metric, threshold_key in (
        ("steps", "max_step_increase"),
        ("tokens", "max_token_increase"),
        ("tool_errors", "max_tool_error_increase"),
    ):
        baseline_value = baseline_behavior.get(metric)
        current_value = current_behavior.get(metric)
        if isinstance(baseline_value, int) and isinstance(current_value, int):
            allowed = int(thresholds.get(threshold_key, 0))
            if current_value > baseline_value + allowed:
                add(metric, baseline_value, current_value)
    if thresholds.get("require_termination_match", True):
        baseline_value = baseline_behavior.get("termination")
        current_value = current_behavior.get("termination")
        if (
            baseline_value is not None
            and current_value is not None
            and baseline_value != current_value
        ):
            add("termination", baseline_value, current_value)
    if thresholds.get("require_recovery_match", True):
        baseline_value = baseline_behavior.get("recovery")
        current_value = current_behavior.get("recovery")
        if baseline_value is True and current_value is not True:
            add("recovery", baseline_value, current_value)
    return regressions


def build_diff(
    report: dict[str, Any],
    baseline: dict[str, Any],
) -> dict[str, Any]:
    current = {case["case_id"]: case for case in report["cases"]}
    expected = baseline["cases"]
    thresholds = {**DEFAULT_THRESHOLDS, **(baseline.get("thresholds") or {})}
    regressions: list[str] = []
    fixed: list[str] = []
    behavior_regressions: list[dict[str, Any]] = []
    added = sorted(set(current) - set(expected))
    missing = sorted(set(expected) - set(current))
    for case_id, case in sorted(current.items()):
        previous = expected.get(case_id)
        if not isinstance(previous, dict):
            continue
        if previous.get("passed") and not case["passed"]:
            regressions.append(case_id)
        elif previous.get("task_success") is True and case["task_success"] is False:
            regressions.append(case_id)
        elif not previous.get("passed") and case["passed"]:
            fixed.append(case_id)
        behavior_regressions.extend(
            _behavior_regressions(case_id, previous, case, thresholds)
        )
    return {
        "schema_version": SCHEMA_VERSION,
        "regressions": regressions,
        "behavior_regressions": behavior_regressions,
        "fixed": fixed,
        "added": added,
        "missing": missing,
        "changed": bool(
            regressions or behavior_regressions or fixed or added or missing
        ),
    }


def _write_json(path: str | Path, payload: dict[str, Any]) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(target.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    temporary.replace(target)
    return target


def _target_factory(config):
    return build_component(config.target_factory, config)


async def run_gate(
    config_paths: tuple[str, ...],
    *,
    baseline_path: str | Path = DEFAULT_BASELINE,
    report_path: str | Path = DEFAULT_REPORT,
    diff_path: str | Path = DEFAULT_DIFF,
    update_baseline: bool = False,
) -> tuple[dict[str, Any], dict[str, Any]]:
    reports: dict[str, EvalReport] = {}
    for config_path in config_paths:
        config = load_config(config_path)
        dataset = load_dataset(config.dataset)
        target = (
            _target_factory(config)
            if config.target_factory
            else RuntimeEvaluationTarget()
        )
        reports[config.name] = await run_evaluation(config, dataset, target)

    report = build_gate_report(reports)
    diff = {
        "schema_version": SCHEMA_VERSION,
        "regressions": [],
        "behavior_regressions": [],
        "fixed": [],
        "added": [],
        "missing": [],
        "changed": False,
    }
    if update_baseline:
        if report["passed"]:
            _write_json(baseline_path, baseline_from_report(report))
        else:
            report["baseline_failures"] = ["cannot update baseline: gate did not pass"]
    else:
        baseline = load_baseline(baseline_path)
        if baseline is None:
            diff = {
                **diff,
                "added": sorted(case["case_id"] for case in report["cases"]),
                "changed": True,
            }
            report["baseline_failures"] = [f"missing baseline: {baseline_path}"]
        else:
            diff = build_diff(report, baseline)
            report["baseline_failures"] = [
                *(f"regression: {case_id}" for case_id in diff["regressions"]),
                *(
                    "behavior regression: "
                    f"{item['case_id']} {item['metric']} "
                    f"baseline={item['baseline']} current={item['current']}"
                    for item in diff["behavior_regressions"]
                ),
                *(f"added without baseline: {case_id}" for case_id in diff["added"]),
                *(f"missing from report: {case_id}" for case_id in diff["missing"]),
            ]
    report["passed"] = report["passed"] and not report["baseline_failures"]
    _write_json(report_path, report)
    _write_json(diff_path, diff)
    return report, diff


def _print_failures(report: dict[str, Any]) -> None:
    for case in report["cases"]:
        if case["passed"]:
            continue
        dimensions = ", ".join(
            f"{item['dimension']}: {item['detail']}"
            for item in case["failed_dimensions"]
        )
        print(
            "  [FAIL] "
            f"config={case['config']} case={case['case_id']} "
            f"run={case['run_id']} trace={case['trace_id']} "
            f"error={case['error']} dimensions={dimensions}"
        )
    for failure in report["threshold_failures"]:
        print(f"  [THRESHOLD] {failure}")
    for failure in report["baseline_failures"]:
        print(f"  [BASELINE] {failure}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Offline L5 PR benchmark gate")
    parser.add_argument(
        "--config",
        action="append",
        dest="configs",
        help="L5 evaluation config; repeat for multiple configs",
    )
    parser.add_argument("--baseline", default=DEFAULT_BASELINE)
    parser.add_argument("--report", default=DEFAULT_REPORT)
    parser.add_argument("--diff", default=DEFAULT_DIFF)
    parser.add_argument(
        "--update-baseline",
        action="store_true",
        help="Write the current passing report as the new baseline",
    )
    args = parser.parse_args(argv)
    configs = tuple(args.configs) if args.configs else DEFAULT_CONFIGS
    try:
        report, diff = asyncio.run(
            run_gate(
                configs,
                baseline_path=args.baseline,
                report_path=args.report,
                diff_path=args.diff,
                update_baseline=args.update_baseline,
            )
        )
    except Exception as exc:
        print(f"L5 gate failed: {type(exc).__name__}", file=sys.stderr)
        return 1
    print(
        f"L5 gate: {'PASS' if report['passed'] else 'FAIL'} "
        f"cases={report['case_count']} regressions={len(diff['regressions'])} "
        f"behavior_regressions={len(diff['behavior_regressions'])}"
    )
    _print_failures(report)
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

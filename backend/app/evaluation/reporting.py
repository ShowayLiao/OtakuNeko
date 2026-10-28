"""Stable machine-readable evaluation reports."""

from __future__ import annotations

import json
from pathlib import Path

from app.evaluation.types import EvalReport
from app.trace.redaction import redact


def report_payload(report: EvalReport) -> dict:
    payload = redact(report.model_dump(mode="json"))
    if report.status == "NOT_RUN":
        payload.update(
            {
                "total": report.total,
                "passed_count": None,
                "failed_count": None,
                "pass_rate": None,
            }
        )
    elif report.status is not None:
        attempted = [
            case
            for case in report.cases
            if case.benchmark_status in {"PASS", "FAIL", "ERROR", "UNGRADED"}
        ]
        passed = sum(case.benchmark_status == "PASS" for case in attempted)
        payload.update(
            {
                "total": report.total,
                "passed_count": passed,
                "failed_count": sum(
                    case.benchmark_status in {"FAIL", "ERROR"} for case in attempted
                ),
                "pass_rate": (
                    report.aggregates.get("loop_success_rate") if attempted else None
                ),
            }
        )
    else:
        payload.update(
            {
                "total": report.total,
                "passed_count": report.passed_count,
                "failed_count": report.failed_count,
                "pass_rate": report.pass_rate,
            }
        )
    return payload


def write_report(report: EvalReport, path: str | Path) -> Path:
    report_path = Path(path)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = report_path.with_suffix(report_path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(
            report_payload(report),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    temporary.replace(report_path)
    return report_path

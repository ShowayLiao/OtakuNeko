"""Stable machine-readable evaluation reports."""

from __future__ import annotations

import json
from pathlib import Path

from app.evaluation.types import EvalReport


def report_payload(report: EvalReport) -> dict:
    payload = report.model_dump(mode="json")
    payload.update({
        "total": report.total,
        "passed_count": report.passed_count,
        "failed_count": report.failed_count,
        "pass_rate": report.pass_rate,
    })
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

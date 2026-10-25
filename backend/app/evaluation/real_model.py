"""Live-model evaluation entry over the shared headless Runtime path.

This entry does not implement an execution loop. Every case is delegated to
``ProductionRuntimeTarget``, which calls the backend headless case runner
(``app.evaluation.entrypoint.run_headless_case``) and therefore the shared
``build_runtime`` composition: AgentRuntime -> Dispatcher -> CapabilityAdapter
-> production capabilities, with SQL Run/Event/Trace stores.

Run it only with an explicit provider configuration:

    uv run python -m app.evaluation.real_model --config evals/config/real-model.yaml

Credentials come from ``OPENAI_API_KEY`` (never a CLI argument). A local
endpoint in ``DEPLOY_MODE=local`` may run without a key. Missing credentials or
a rejected endpoint fail closed before any case or provider socket is opened.
"""

from __future__ import annotations

import argparse
import asyncio
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import sys
from typing import Any
from uuid import uuid4

from app.agents.provider_endpoint import ProviderEndpointError
from app.evaluation.adapter import (
    ProductionRuntimeTarget,
    ProviderCredentialsUnavailable,
)
from app.evaluation.config import EvaluationConfig, load_config
from app.evaluation.dataset import load_dataset
from app.evaluation.errors import safe_error
from app.evaluation.judge import Judge
from app.evaluation.reporting import write_report
from app.evaluation.runner import build_component, print_report, run_evaluation
from app.evaluation.transcript import transcript_path
from app.evaluation.types import EvalDataset, EvalReport

DEFAULT_CONFIG = "evals/config/real-model.yaml"
DEFAULT_TRANSCRIPT_DIR = ".runtime/evaluation/real-model/transcripts"
EXPECTED_TARGET_FACTORY = "app.evaluation.adapter:create_production_target"
_RUN_ID_PATTERN = re.compile(r"^[A-Za-z0-9._-]+$")


def build_real_model_target(
    config: EvaluationConfig,
    *,
    model: str | None = None,
    base_url: str | None = None,
    api_key: str | None = None,
    transcript_dir: str | Path | None = None,
    temperature: float = 0,
    deepseek_options: dict[str, Any] | None = None,
) -> ProductionRuntimeTarget:
    """Build the only live target used by this entry.

    A config that names another target factory is rejected so the live entry
    cannot be silently redirected to a fixture or bypass executor.
    """
    if config.target_factory not in (None, EXPECTED_TARGET_FACTORY):
        raise ValueError("real-model entry requires the production target factory")
    controlled = config.controlled
    if deepseek_options is None and config.deepseek is not None:
        deepseek_options = config.deepseek.model_dump(mode="json")
    return ProductionRuntimeTarget(
        config,
        model=model,
        base_url=base_url,
        api_key=api_key,
        transcript_dir=transcript_dir,
        temperature=temperature,
        deepseek_options=deepseek_options,
        allowed_public_names=(
            controlled.allowed_capabilities if controlled is not None else None
        ),
        external_fixtures=(
            controlled.external_fixtures if controlled is not None else None
        ),
    )


def select_dataset(
    dataset: EvalDataset,
    *,
    case_ids: list[str] | None = None,
    limit: int | None = None,
) -> EvalDataset:
    """Apply an explicit case/limit selection before any provider call."""
    cases = dataset.cases
    if case_ids:
        selected = set(case_ids)
        missing = sorted(selected - {case.id for case in cases})
        if missing:
            raise ValueError(f"unknown evaluation case: {', '.join(missing)}")
        cases = [case for case in cases if case.id in selected]
    if limit is not None:
        if limit < 1:
            raise ValueError("limit must be positive")
        cases = cases[:limit]
    if not cases:
        raise ValueError("no evaluation cases selected")
    return dataset.model_copy(update={"cases": cases})


async def run_real_model_evaluation(
    config: EvaluationConfig,
    dataset: EvalDataset,
    target: ProductionRuntimeTarget,
    judge: Judge | None = None,
) -> EvalReport:
    """Run the standard evaluator; the target owns all model execution."""
    return await run_evaluation(config, dataset, target, judge=judge)


def _new_run_id() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid4().hex[:8]


def _validate_run_id(run_id: str) -> str:
    if not _RUN_ID_PATTERN.fullmatch(run_id) or run_id in {".", ".."}:
        raise ValueError("run id must match [A-Za-z0-9._-]+")
    return run_id


def _write_run_manifest(
    run_dir: Path,
    *,
    run_id: str,
    config: EvaluationConfig,
    dataset: EvalDataset,
    report: EvalReport,
    report_path: Path,
    transcript_dir: Path,
    review_queue_path: Path | None = None,
) -> Path:
    manifest = {
        "schema_version": 1,
        "run_id": run_id,
        "config": config.name,
        "dataset_version": dataset.dataset_version,
        "dataset_digest": report.dataset_digest,
        "code_revision": report.code_revision,
        "model": report.agent.model,
        "provider": report.agent.provider,
        "controlled": (
            config.controlled.model_dump(mode="json")
            if config.controlled is not None
            else None
        ),
        "report": str(report_path),
        "transcripts": str(transcript_dir),
        "review_queue": (
            str(review_queue_path) if review_queue_path is not None else None
        ),
        "started_at": report.started_at.isoformat(),
        "completed_at": (
            report.completed_at.isoformat() if report.completed_at else None
        ),
        "passed": report.passed_count,
        "failed": report.failed_count,
        "aggregates": report.aggregates,
        "gate_failures": report.gate_failures,
        "baseline_failures": report.baseline_failures,
    }
    path = run_dir / "run-manifest.json"
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    temporary.replace(path)
    return path


def _write_review_queue(
    directory: Path,
    report: EvalReport,
    transcript_dir: Path,
) -> Path:
    """Write disputed/unresolved cases with redacted transcript pointers."""
    entries: list[dict[str, object]] = []
    for entry in report.review_queue:
        payload = entry.model_dump(mode="json")
        path = transcript_path(transcript_dir, entry.case_id)
        payload["transcript"] = str(path) if path.is_file() else None
        entries.append(payload)
    path = directory / "review-queue.json"
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(
            {"schema_version": 1, "entries": entries},
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    temporary.replace(path)
    return path


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the live-model evaluation entry",
    )
    parser.add_argument("--config", default=DEFAULT_CONFIG)
    parser.add_argument("--dataset", help="Override configured dataset path")
    parser.add_argument("--model", help="Override the configured model name")
    parser.add_argument(
        "--base-url",
        help="Override OPENAI_BASE_URL (validated by the provider egress policy)",
    )
    parser.add_argument(
        "--case",
        action="append",
        dest="case_ids",
        help="Run only this case id (repeatable)",
    )
    parser.add_argument("--limit", type=int, help="Run at most N selected cases")
    parser.add_argument("--tags", nargs="*", help="Override configured tags")
    parser.add_argument("--report", help="Override JSON report path")
    parser.add_argument(
        "--human-reviews",
        help="Versioned human review JSON file",
    )
    parser.add_argument(
        "--transcript-dir",
        help="Per-case redacted transcript directory",
    )
    parser.add_argument(
        "--temperature",
        type=float,
        default=0,
        help="Provider sampling temperature (default: 0)",
    )
    parser.add_argument("--run-id", help="Run id for run-scoped artifacts")
    parser.add_argument(
        "--run-dir",
        help="Base directory for run-scoped artifacts (default: report parent/runs)",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv if argv is not None else sys.argv[1:])
    try:
        config = load_config(args.config)
        if args.dataset:
            config.dataset = args.dataset
        if args.tags is not None:
            config.tags = args.tags
        if args.report:
            config.report_path = args.report
        if args.human_reviews:
            config.human_reviews = args.human_reviews
        if args.model:
            config.agent = config.agent.model_copy(update={"model": args.model})
        run_scoped = bool(
            config.controlled is not None and config.controlled.run_scoped_artifacts
        )
        if run_scoped:
            run_id = _validate_run_id(args.run_id or _new_run_id())
            base_dir = (
                Path(args.run_dir)
                if args.run_dir
                else Path(config.report_path).parent / config.name / "runs"
            )
            run_dir = base_dir / run_id
            if run_dir.exists():
                raise ValueError("run directory already exists")
            transcript_dir = args.transcript_dir or str(run_dir / "transcripts")
            report_path_argument = args.report or str(run_dir / "report.json")
        else:
            if args.run_id or args.run_dir:
                raise ValueError("--run-id/--run-dir require controlled artifacts")
            run_id = ""
            run_dir = None
            transcript_dir = (
                args.transcript_dir or config.transcript_dir or DEFAULT_TRANSCRIPT_DIR
            )
            report_path_argument = args.report or config.report_path
        config.transcript_dir = transcript_dir
        config.report_path = report_path_argument
        dataset = select_dataset(
            load_dataset(config.dataset),
            case_ids=args.case_ids,
            limit=args.limit,
        )
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
            # The Judge factory reads the same provider environment.
            os.environ["OPENAI_BASE_URL"] = args.base_url
        judge = (
            build_component(config.judge_factory, config)
            if config.judge_factory
            else None
        )
        print(
            "real-model evaluation: "
            f"config={config.name} model={config.agent.model} "
            f"cases={len(dataset.cases)} transcripts={transcript_dir}",
            file=sys.stderr,
        )
        if run_dir is not None:
            print(f"real-model run artifacts: {run_dir}", file=sys.stderr)
        report = asyncio.run(
            run_real_model_evaluation(config, dataset, target, judge=judge)
        )
        report_path = write_report(report, report_path_argument)
        artifact_dir = run_dir if run_dir is not None else Path(report_path).parent
        review_queue_path = _write_review_queue(
            artifact_dir,
            report,
            Path(transcript_dir),
        )
        if run_dir is not None:
            _write_run_manifest(
                run_dir,
                run_id=run_id,
                config=config,
                dataset=dataset,
                report=report,
                report_path=report_path,
                transcript_dir=Path(transcript_dir),
                review_queue_path=review_queue_path,
            )
    except ProviderCredentialsUnavailable:
        print(
            "real-model evaluation requires OPENAI_API_KEY "
            "or a local endpoint in DEPLOY_MODE=local",
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
    print_report(report, report_path)
    return 1 if report.gate_failures or report.baseline_failures else 0


if __name__ == "__main__":
    raise SystemExit(main())

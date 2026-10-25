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
from pathlib import Path
import sys

from app.agents.provider_endpoint import ProviderEndpointError
from app.evaluation.adapter import (
    ProductionRuntimeTarget,
    ProviderCredentialsUnavailable,
)
from app.evaluation.config import EvaluationConfig, load_config
from app.evaluation.dataset import load_dataset
from app.evaluation.errors import safe_error
from app.evaluation.reporting import write_report
from app.evaluation.runner import print_report, run_evaluation
from app.evaluation.types import EvalDataset, EvalReport

DEFAULT_CONFIG = "evals/config/real-model.yaml"
DEFAULT_TRANSCRIPT_DIR = ".runtime/evaluation/real-model/transcripts"
EXPECTED_TARGET_FACTORY = "app.evaluation.adapter:create_production_target"


def build_real_model_target(
    config: EvaluationConfig,
    *,
    model: str | None = None,
    base_url: str | None = None,
    api_key: str | None = None,
    transcript_dir: str | Path | None = None,
    temperature: float = 0,
) -> ProductionRuntimeTarget:
    """Build the only live target used by this entry.

    A config that names another target factory is rejected so the live entry
    cannot be silently redirected to a fixture or bypass executor.
    """
    if config.target_factory not in (None, EXPECTED_TARGET_FACTORY):
        raise ValueError("real-model entry requires the production target factory")
    return ProductionRuntimeTarget(
        config,
        model=model,
        base_url=base_url,
        api_key=api_key,
        transcript_dir=transcript_dir,
        temperature=temperature,
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
) -> EvalReport:
    """Run the standard evaluator; the target owns all model execution."""
    return await run_evaluation(config, dataset, target)


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
        "--transcript-dir",
        help="Per-case redacted transcript directory",
    )
    parser.add_argument(
        "--temperature",
        type=float,
        default=0,
        help="Provider sampling temperature (default: 0)",
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
        if args.model:
            config.agent = config.agent.model_copy(update={"model": args.model})
        transcript_dir = (
            args.transcript_dir or config.transcript_dir or DEFAULT_TRANSCRIPT_DIR
        )
        config.transcript_dir = transcript_dir
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
        )
        print(
            "real-model evaluation: "
            f"config={config.name} model={config.agent.model} "
            f"cases={len(dataset.cases)} transcripts={transcript_dir}",
            file=sys.stderr,
        )
        report = asyncio.run(run_real_model_evaluation(config, dataset, target))
        report_path = write_report(report, args.report or config.report_path)
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

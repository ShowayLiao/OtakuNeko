"""Multi-run trend baseline, variance, regression and cost history."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.evaluation import adapter, real_model, trend
from app.evaluation.config import load_config
from app.evaluation.dataset import load_dataset
from app.evaluation.runner import run_evaluation
from app.evaluation.scripted_llm import ScriptedLLM
from app.evaluation.types import (
    AgentMetadata,
    CaseResult,
    EvalReport,
    ExecutionFixture,
    L6CaseScore,
    L6Outcome,
    RunUsage,
    ScriptEvent,
)


class _Gateway(ScriptedLLM):
    async def close(self) -> None:
        return None


def _case_result(
    case_id: str,
    *,
    outcome: L6Outcome = "passed",
    latency: float = 10,
    tokens: int | None = 4,
    cost: float | None = None,
    scores: dict[str, float] | None = None,
) -> CaseResult:
    return CaseResult(
        case_id=case_id,
        category="routing",
        passed=outcome == "passed",
        outcome=outcome,
        run_id=f"run-{case_id}",
        trace_id=f"trace-{case_id}",
        usage=RunUsage(
            model_calls=2,
            model_tokens=tokens,
            latency_ms=latency,
            estimated_cost_usd=cost,
        ),
        l6=L6CaseScore(
            case_id=case_id,
            outcome=outcome,
            task_success=(outcome == "passed"),
            scores=(
                scores
                if scores is not None
                else {"task_success": 1.0 if outcome == "passed" else 0.0}
            ),
        ),
    )


def _report(cases: list[CaseResult]) -> EvalReport:
    return EvalReport(
        dataset_version="v1-real-model",
        dataset_digest="digest",
        config_name="trend",
        code_revision="revision",
        agent=AgentMetadata(
            name="trend",
            model="deepseek-flash",
            provider="deepseek",
        ),
        prompt_version="decision-contract-v1",
        cases=cases,
    )


def test_expand_repeats_creates_independent_ids() -> None:
    dataset = load_dataset("evals/datasets/v1-real-model.jsonl")
    expanded = trend.expand_repeats(dataset, 2)

    ids = [case.id for case in expanded.cases]
    assert len(ids) == len(dataset.cases) * 2
    assert len(set(ids)) == len(ids)
    assert "real-model-tool-time__r1" in ids
    assert "real-model-tool-time__r2" in ids
    assert all("__r1" in case.id or "__r2" in case.id for case in expanded.cases)
    assert expanded.content_digest == dataset.content_digest


def test_baseline_records_variance_usage_and_provider_errors() -> None:
    results = [
        _case_result("case-a__r1", latency=10, tokens=4, cost=0.01),
        _case_result(
            "case-a__r2",
            outcome="functional_failure",
            latency=20,
            tokens=6,
            cost=0.03,
            scores={"task_success": 0.0},
        ),
        _case_result(
            "case-b__r1",
            outcome="provider_error",
            latency=30,
            tokens=None,
            scores={},
        ),
    ]

    baseline = trend.build_baseline(_report(results), repeats=2)

    case_a = baseline.cases["case-a"]
    assert case_a.runs == 2
    assert case_a.functional_runs == 2
    assert case_a.functional_pass_rate == 0.5
    assert case_a.pass_rate_variance == 0.25
    assert case_a.mean_latency_ms == 15
    assert case_a.mean_tokens == 5
    assert case_a.tokens_stddev == 1
    assert case_a.mean_cost_usd == 0.02
    assert case_a.provider_error_rate == 0
    case_b = baseline.cases["case-b"]
    assert case_b.functional_runs == 0
    assert case_b.provider_error_rate == 1
    assert baseline.totals.functional_pass_rate == 0.5
    assert baseline.totals.provider_error_rate == 1 / 3


def test_compare_detects_regressions_and_version_drift() -> None:
    baseline = trend.build_baseline(
        _report(
            [
                _case_result(
                    "case-a__r1",
                    latency=10,
                    tokens=4,
                    cost=0.01,
                    scores={"task_success": 1.0},
                )
            ]
        ),
        repeats=1,
    )
    current = trend.build_baseline(
        _report(
            [
                _case_result(
                    "case-a__r1",
                    outcome="functional_failure",
                    latency=40,
                    tokens=10,
                    cost=0.05,
                    scores={"task_success": 0.5},
                )
            ]
        ),
        repeats=1,
    )

    diff = trend.compare_baseline(baseline, current, tolerance=trend.TrendTolerance())

    assert not diff.version_failures
    assert any("functional_pass_rate" in item for item in diff.regressions)
    assert any("latency" in item for item in diff.regressions)
    assert any("tokens" in item for item in diff.regressions)
    assert any("cost" in item for item in diff.regressions)

    drifted = current.model_copy(update={"repeats": 2, "model": "other"})
    version_diff = trend.compare_baseline(
        baseline, drifted, tolerance=trend.TrendTolerance()
    )
    assert any("repeats" in item for item in version_diff.version_failures)
    assert any("model" in item for item in version_diff.version_failures)


def test_compare_tracks_added_and_missing_cases() -> None:
    baseline = trend.build_baseline(_report([_case_result("case-a__r1")]), repeats=1)
    current = trend.build_baseline(_report([_case_result("case-b__r1")]), repeats=1)

    diff = trend.compare_baseline(baseline, current, tolerance=trend.TrendTolerance())

    assert diff.added == ["case-b"]
    assert diff.missing == ["case-a"]
    assert any("missing" in item for item in diff.regressions)


def test_history_and_cost_trend() -> None:
    baseline = trend.build_baseline(
        _report(
            [
                _case_result(
                    "case-a__r1",
                    latency=10,
                    tokens=4,
                    cost=0.01,
                )
            ]
        ),
        repeats=1,
    )
    record = trend._history_record("run-1", baseline)
    previous = {
        **record,
        "functional_pass_rate": 0.5,
        "mean_latency_ms": 5,
        "total_tokens": 2,
        "total_cost_usd": 0.005,
    }

    cost = trend.cost_trend(previous, baseline)

    assert cost.delta_pass_rate == 0.5
    assert cost.delta_latency_pct == 1.0
    assert cost.delta_tokens_pct == 1.0
    assert cost.delta_cost_pct == 1.0
    assert trend.cost_trend(None, baseline).delta_latency_pct is None


def _expanded_live_dataset():
    dataset = load_dataset("evals/datasets/v1-real-model.jsonl")
    base = next(item for item in dataset.cases if item.id == "real-model-tool-time")
    events = [
        ScriptEvent(
            type="tool_call_start",
            name="get_current_time",
            arguments={},
        ),
        ScriptEvent(type="message_chunk", content="The current time is noon."),
    ]
    base = base.model_copy(update={"fixtures": ExecutionFixture(events=events)})
    return dataset.model_copy(update={"cases": [base]}), base


@pytest.mark.asyncio
async def test_repeated_runs_are_independent_through_live_target(
    monkeypatch, tmp_path: Path
) -> None:
    config = load_config("evals/config/real-model.yaml")
    config.transcript_dir = str(tmp_path)
    dataset, base = _expanded_live_dataset()

    def gateway_factory(**_kwargs):
        return _Gateway(
            ScriptedLLM.script_steps(base.fixtures.events),
            provider="scripted",
            model="scripted-v1",
        )

    monkeypatch.setattr(adapter, "OpenAIModelGateway", gateway_factory)
    target = real_model.build_real_model_target(
        config,
        base_url="https://api.openai.com/v1",
        api_key="synthetic-evaluation-key",
        transcript_dir=tmp_path,
    )
    expanded = trend.expand_repeats(
        dataset.model_copy(update={"cases": [base]}),
        2,
    )

    report = await run_evaluation(config, expanded, target)
    baseline = trend.build_baseline(report, repeats=2)

    assert {case.case_id for case in report.cases} == {
        "real-model-tool-time__r1",
        "real-model-tool-time__r2",
    }
    assert len({case.run_id for case in report.cases}) == 2
    assert all(
        case.transcript_path is not None and Path(case.transcript_path).is_file()
        for case in report.cases
    )
    case = baseline.cases["real-model-tool-time"]
    assert case.runs == 2
    assert case.functional_pass_rate == 1.0
    assert case.pass_rate_variance == 0.0
    assert case.mean_tokens == 4
    assert case.provider_error_rate == 0


def test_trend_cli_updates_baseline_and_writes_history(
    monkeypatch, tmp_path: Path
) -> None:
    dataset, base = _expanded_live_dataset()
    assert dataset.dataset_version
    monkeypatch.setenv("OPENAI_API_KEY", "synthetic-evaluation-key")
    monkeypatch.delenv("OPENAI_BASE_URL", raising=False)

    def gateway_factory(**_kwargs):
        return _Gateway(
            ScriptedLLM.script_steps(base.fixtures.events),
            provider="scripted",
            model="scripted-v1",
        )

    monkeypatch.setattr(adapter, "OpenAIModelGateway", gateway_factory)
    output = tmp_path / "run-1"
    baseline_path = tmp_path / "baseline.json"
    history = tmp_path / "history.jsonl"
    common = [
        "--config",
        "evals/config/real-model.yaml",
        "--base-url",
        "https://api.openai.com/v1",
        "--case",
        "real-model-tool-time",
        "--repeats",
        "2",
        "--history",
        str(history),
        "--output-dir",
        str(output),
        "--run-id",
        "run-1",
    ]

    assert (
        trend.main([*common, "--baseline", str(baseline_path), "--update-baseline"])
        == 0
    )
    assert (output / "report.json").is_file()
    assert (output / "current-baseline.json").is_file()
    assert (output / "trend-report.json").is_file()
    assert baseline_path.is_file()
    assert len(history.read_text(encoding="utf-8").splitlines()) == 1

    output2 = tmp_path / "run-2"
    assert (
        trend.main(
            [
                *common[: common.index("--output-dir")],
                "--output-dir",
                str(output2),
                "--run-id",
                "run-2",
                "--baseline",
                str(baseline_path),
            ]
        )
        == 0
    )
    assert (output2 / "trend-diff.json").is_file()
    diff = json.loads((output2 / "trend-diff.json").read_text(encoding="utf-8"))
    assert diff["regressions"] == []
    assert len(history.read_text(encoding="utf-8").splitlines()) == 2

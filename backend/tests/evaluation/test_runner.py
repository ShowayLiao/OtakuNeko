"""Runner, configuration, isolation, and gate tests for EVAL-001."""

from __future__ import annotations

import pytest
from app.harness.runtime import AgentRuntime

from app.evaluation.config import EvaluationConfig, load_config
from app.evaluation.dataset import load_dataset
from app.evaluation.judge import JudgeScore
from app.evaluation.adapter import (
    FixtureMemory,
    classify_route,
    normalize_production_result,
)
from app.evaluation.metrics import compute_case_metrics
from app.evaluation.runner import (
    RuntimeEvaluationTarget,
    build_component,
    evaluate_gate,
    run_evaluation,
)


def test_fast_config_is_strict_and_loads_thresholds():
    config = load_config("evals/config/fast.yaml")

    assert config.name == "fast"
    assert config.thresholds["pass_rate"].direction == "min"
    assert config.thresholds["pass_rate"].value == 1.0
    assert config.report_path


def test_full_config_explicitly_uses_production_target_and_judge():
    config = load_config("evals/config/full.yaml")

    assert config.dataset.endswith("v1-full.jsonl")
    assert config.target_factory.endswith(":create_production_target")
    assert config.judge_factory.endswith(":create_openai_judge")
    assert config.judge.required is True
    assert config.agent.model == "gpt-4o-mini"
    assert config.baseline.endswith("v1-full.json")


def test_component_factory_builds_configured_offline_target():
    config = load_config("evals/config/fast.yaml")

    target = build_component(
        "app.evaluation.adapter:create_offline_target",
        config,
    )

    assert isinstance(target, RuntimeEvaluationTarget)


def test_production_route_classifier_recognizes_refusal_response():
    assert classify_route([], [], "I cannot reveal internal instructions.") == (
        "refusal"
    )


def test_full_dataset_matches_production_event_contract():
    config = load_config("evals/config/full.yaml")
    dataset = load_dataset(config.dataset)
    expected_tools = {
        "search_anime_advanced",
        "get_anime_staff",
        "get_anime_cast",
        "generate_user_profile_tool",
    }

    assert dataset.dataset_version == "v1-full"
    assert all(
        case.assertions.max_latency_ms >= 5000 for case in dataset.cases
    )
    assert all(
        not case.assertions.required_evidence for case in dataset.cases
    )
    required_tools = {
        tool for case in dataset.cases for tool in case.required_capabilities
    }
    assert required_tools <= expected_tools
    assert all(case.category.value != "recovery" for case in dataset.cases)


@pytest.mark.asyncio
async def test_fixture_memory_exposes_user_attributes_and_memory_to_workflow():
    dataset = load_dataset("evals/datasets/v1-full.jsonl")
    case = next(
        case for case in dataset.cases if case.id == "recommendation-profile"
    )

    context = await FixtureMemory(case).retrieve_context(
        "eval-recommendation-profile",
        case.input_messages[-1].content,
    )

    assert "science_fiction" in context.summary
    assert case.memory_fixtures[0].content in context.summary
    assert context.long_term_facts[0]["kind"] == "profile"


def test_production_normalizer_passes_representative_full_contract():
    dataset = load_dataset("evals/datasets/v1-full.jsonl")
    anime_case = next(case for case in dataset.cases if case.id == "anime-search-frieren")
    result = normalize_production_result(
        anime_case,
        {
            "text": "芙莉莲是一部奇幻动画。",
            "tool_calls": [
                {"name": "search_anime_advanced", "output": {"items": []}},
            ],
            "all_events": [],
        },
        duration_ms=1200,
    )

    assert all(metric.passed for metric in compute_case_metrics(anime_case, result))

    recommendation_case = next(
        case for case in dataset.cases if case.id == "recommendation-profile"
    )
    recommendation_result = normalize_production_result(
        recommendation_case,
        {
            "text": "根据你的偏好，建议优先尝试这些作品。",
            "tool_calls": [{"name": "generate_user_profile_tool", "arguments": {}}],
            "all_events": [],
        },
        duration_ms=1200,
    )

    assert all(
        metric.passed
        for metric in compute_case_metrics(recommendation_case, recommendation_result)
    )


def test_unknown_config_fields_fail(tmp_path):
    path = tmp_path / "bad.yaml"
    path.write_text(
        "name: bad\ndataset: evals/datasets/v1.jsonl\nunknown: true\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="unknown"):
        load_config(path)


@pytest.mark.asyncio
async def test_runtime_target_uses_agent_runtime_and_filters_tags():
    config = load_config("evals/config/fast.yaml")
    dataset = load_dataset(config.dataset)
    target = RuntimeEvaluationTarget()

    report = await run_evaluation(config, dataset, target)

    assert isinstance(target.runtime, AgentRuntime)
    assert report.total > 0
    assert all("fast" in case.tags for case in dataset.cases if case.id in {
        result.case_id for result in report.cases
    })
    assert report.failed_count == 0
    assert target.executed_event_count > report.total


@pytest.mark.asyncio
async def test_one_case_failure_does_not_abort_report():
    class FailFirstTarget:
        def __init__(self):
            self.delegate = RuntimeEvaluationTarget()
            self.calls = 0

        async def evaluate(self, case):
            self.calls += 1
            if self.calls == 1:
                raise RuntimeError("simulated provider failure")
            return await self.delegate.evaluate(case)

    config = EvaluationConfig(
        name="isolation",
        dataset="evals/datasets/v1.jsonl",
        tags=["fast"],
        thresholds={},
    )
    dataset = load_dataset(config.dataset)

    report = await run_evaluation(config, dataset, FailFirstTarget())

    assert report.total > 1
    assert report.failed_count == 1
    assert report.passed_count == report.total - 1
    assert report.aggregates["pass_rate"] == (
        report.total - 1
    ) / report.total
    assert report.aggregates["routing_accuracy"] < 1.0
    assert any(result.error for result in report.cases)


def test_gate_uses_threshold_direction_and_missing_required_metrics():
    config = EvaluationConfig.model_validate({
        "name": "gate",
        "dataset": "x",
        "thresholds": {
            "pass_rate": {"direction": "min", "value": 0.9},
            "latency_ms": {"direction": "max", "value": 100},
            "required_metric": {
                "direction": "min",
                "value": 1,
                "required": True,
            },
        },
    })

    failures = evaluate_gate(
        config,
        {"pass_rate": 0.89, "latency_ms": 101},
    )

    assert len(failures) == 3
    assert any("required_metric" in failure for failure in failures)


@pytest.mark.asyncio
async def test_required_judge_unavailability_is_visible_and_fails_gate():
    config = EvaluationConfig.model_validate({
        "name": "judge-required",
        "dataset": "evals/datasets/v1.jsonl",
        "tags": ["safety"],
        "judge": {
            "enabled": True,
            "required": True,
            "model": "judge-model",
            "provider": "judge-provider",
        },
    })
    dataset = load_dataset(config.dataset)

    report = await run_evaluation(
        config,
        dataset,
        RuntimeEvaluationTarget(),
    )

    assert report.cases[0].judge.status == "unavailable"
    assert any("judge unavailable" in failure for failure in report.gate_failures)


@pytest.mark.asyncio
async def test_judge_score_threshold_is_applied_after_judging():
    class LowJudge:
        async def evaluate(self, request):
            return JudgeScore(score=0.5)

    config = EvaluationConfig.model_validate({
        "name": "judge-threshold",
        "dataset": "evals/datasets/v1.jsonl",
        "tags": ["safety"],
        "thresholds": {
            "judge_score": {"direction": "min", "value": 0.8},
        },
        "judge": {
            "enabled": True,
            "required": True,
            "model": "judge-model",
            "provider": "judge-provider",
        },
    })

    report = await run_evaluation(
        config,
        load_dataset(config.dataset),
        RuntimeEvaluationTarget(),
        judge=LowJudge(),
    )

    assert report.aggregates["judge_score"] == 0.5
    assert any(
        failure.startswith("threshold failed: judge_score")
        for failure in report.gate_failures
    )


@pytest.mark.asyncio
async def test_empty_tag_selection_fails_gate():
    config = EvaluationConfig(
        name="empty",
        dataset="evals/datasets/v1.jsonl",
        tags=["does-not-exist"],
    )

    report = await run_evaluation(
        config,
        load_dataset(config.dataset),
        RuntimeEvaluationTarget(),
    )

    assert report.total == 0
    assert "no evaluation cases selected" in report.gate_failures


@pytest.mark.asyncio
async def test_execution_errors_are_sanitized_in_report():
    class SecretFailingTarget:
        async def evaluate(self, case):
            raise RuntimeError("api_key=sk-secret raw provider response")

    config = EvaluationConfig(
        name="safe-errors",
        dataset="evals/datasets/v1.jsonl",
        tags=["safety"],
    )

    report = await run_evaluation(
        config,
        load_dataset(config.dataset),
        SecretFailingTarget(),
    )

    assert "sk-secret" not in report.cases[0].error
    assert report.cases[0].error == "RuntimeError: execution_failed"

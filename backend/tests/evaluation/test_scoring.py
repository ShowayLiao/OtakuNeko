"""Deterministic case and scoring contract tests."""

from __future__ import annotations

import pytest

from app.evaluation.config import load_config
from app.evaluation.dataset import load_dataset
from app.evaluation.entrypoint import DecisionEntrypointTarget
from app.evaluation.runner import (
    build_component,
    evaluate_gate,
    run_case,
    run_evaluation,
)
from app.evaluation.scoring import (
    DETERMINISTIC_DIMENSIONS,
    answer_quality_passed,
    score_deterministic,
)
from app.evaluation.types import (
    AnswerQualitySpec,
    EvalCase,
    ExecutionResult,
    JudgeOutcome,
    ToolErrorSample,
)

SPEC = {
    "schema_version": 1,
    "tools": {"required": ["demo.read"], "forbidden": ["demo.write"]},
    "arguments": {"required_keys": ["query"], "forbidden_keys": ["user_id"]},
    "termination": {"status": "completed"},
    "evidence": {"required": ["fact-1"]},
    "recovery": {"required": True},
    "steps": {"min_steps": 1, "max_steps": 3},
    "tool_errors": {
        "max_failures": 1,
        "allowed_error_codes": ["read_failure"],
        "required_error_codes": ["read_failure"],
    },
}


def _case(
    *,
    case_id: str = "contract-case",
    deterministic: dict | None = None,
    answer_quality: dict | None = None,
) -> EvalCase:
    payload: dict = {
        "id": case_id,
        "category": "routing",
        "input_messages": [{"role": "user", "content": "Run the contract."}],
        "user_fixture": {"user_id": 7},
        "assertions": {"max_latency_ms": 5000, "max_calls": 2},
        "fixtures": {"events": [{"type": "message_chunk", "content": "ok"}]},
    }
    if deterministic is not None:
        payload["deterministic"] = deterministic
    if answer_quality is not None:
        payload["answer_quality"] = answer_quality
    return EvalCase.model_validate(payload)


def _passing_result(**overrides) -> ExecutionResult:
    values: dict = {
        "route": "chat",
        "capabilities": ["demo.read"],
        "evidence": ["fact-1"],
        "recovered": True,
        "step_count": 2,
        "run_status": "completed",
        "tool_failure_count": 1,
        "tool_argument_keys": ["query"],
        "tool_errors": [
            ToolErrorSample(capability="demo.read", error_code="read_failure")
        ],
    }
    values.update(overrides)
    return ExecutionResult(**values)


def test_contract_score_is_pure_and_repeatable() -> None:
    case = _case(deterministic=SPEC)
    result = _passing_result()

    first = score_deterministic(case, result)
    second = score_deterministic(case, result)

    assert first is not None and second is not None
    assert first.model_dump() == second.model_dump()
    assert first.task_success is True
    assert first.answer_quality_excluded is True
    assert [item.dimension for item in first.dimensions] == list(
        DETERMINISTIC_DIMENSIONS
    )


def test_case_without_contract_is_not_scored() -> None:
    assert score_deterministic(_case(), _passing_result()) is None


@pytest.mark.parametrize(
    ("expected_dimension", "overrides"),
    [
        ("termination", {"run_status": "failed"}),
        ("required_tools", {"capabilities": []}),
        ("forbidden_tools", {"capabilities": ["demo.read", "demo.write"]}),
        ("arguments", {"tool_argument_keys": ["query", "user_id"]}),
        ("evidence", {"evidence": []}),
        ("recovery", {"recovered": False}),
        ("steps", {"step_count": 9}),
        ("tool_errors", {"tool_failure_count": 5}),
    ],
)
def test_each_dimension_failure_is_isolated_and_fails_task_success(
    expected_dimension: str,
    overrides: dict,
) -> None:
    score = score_deterministic(_case(deterministic=SPEC), _passing_result(**overrides))

    assert score is not None
    assert score.task_success is False
    failed = {item.dimension for item in score.dimensions if not item.passed}
    assert failed == {expected_dimension}
    detail = next(
        item.detail for item in score.dimensions if item.dimension == expected_dimension
    )
    assert detail


def test_answer_quality_never_changes_task_success() -> None:
    case = _case(
        deterministic=SPEC,
        answer_quality={"rubric": "quality", "min_score": 0.9, "required": True},
    )
    score = score_deterministic(case, _passing_result())

    assert score is not None and score.task_success is True
    assert (
        answer_quality_passed(
            case.answer_quality,
            JudgeOutcome(status="available", score=0.1),
        )
        is False
    )
    assert (
        answer_quality_passed(
            case.answer_quality,
            JudgeOutcome(status="unavailable", error="not configured"),
        )
        is False
    )
    assert (
        answer_quality_passed(
            AnswerQualitySpec(min_score=0.5, required=False),
            JudgeOutcome(status="available", score=0.1),
        )
        is False
    )
    assert (
        answer_quality_passed(
            None,
            JudgeOutcome(status="available", score=0.1),
        )
        is None
    )


def _entrypoint_case(case_id: str, deterministic: dict) -> EvalCase:
    return EvalCase.model_validate(
        {
            "id": case_id,
            "category": "routing",
            "input_messages": [{"role": "user", "content": "Use echo, then respond."}],
            "user_fixture": {"user_id": 511},
            "expected_route": "chat",
            "assertions": {"max_latency_ms": 5000, "max_calls": 1},
            "fixtures": {
                "events": [
                    {
                        "type": "tool_call_start",
                        "name": "entrypoint.echo",
                        "arguments": {"text": "l5"},
                    },
                    {"type": "message_chunk", "content": "synthetic-result"},
                ]
            },
            "deterministic": deterministic,
        }
    )


ENTRYPOINT_SPEC = {
    "schema_version": 1,
    "tools": {"required": ["entrypoint.echo"], "forbidden": ["entrypoint.write"]},
    "arguments": {"required_keys": ["text"], "forbidden_keys": ["user_id"]},
    "termination": {"status": "completed"},
    "steps": {"min_steps": 2, "max_steps": 2},
    "tool_errors": {"max_failures": 0},
}


@pytest.mark.asyncio
async def test_entrypoint_contract_case_scores_through_runner() -> None:
    result = await run_case(
        _entrypoint_case("l5-runtime-pass", ENTRYPOINT_SPEC),
        DecisionEntrypointTarget(),
    )

    assert result.passed is True
    assert result.deterministic is not None
    assert result.deterministic.task_success is True
    assert {
        item.dimension for item in result.deterministic.dimensions if not item.passed
    } == set()


@pytest.mark.asyncio
async def test_entrypoint_contract_failure_keeps_dimension_evidence() -> None:
    contract = {
        "schema_version": 1,
        "tools": {"required": ["entrypoint.missing"]},
        "termination": {"status": "completed"},
        "steps": {"min_steps": 2, "max_steps": 2},
    }

    result = await run_case(
        _entrypoint_case("l5-runtime-missing-tool", contract),
        DecisionEntrypointTarget(),
    )

    assert result.passed is False
    assert result.deterministic is not None
    assert result.deterministic.task_success is False
    failed = {
        item.dimension: item.detail
        for item in result.deterministic.dimensions
        if not item.passed
    }
    assert set(failed) == {"required_tools"}
    assert "entrypoint.missing" in failed["required_tools"]


@pytest.mark.asyncio
async def test_entrypoint_execution_failure_still_yields_deterministic_score() -> None:
    case = EvalCase.model_validate(
        {
            "id": "l5-runtime-provider-failure",
            "category": "recovery",
            "input_messages": [{"role": "user", "content": "Trigger failure."}],
            "user_fixture": {"user_id": 512},
            "assertions": {"max_latency_ms": 5000, "max_calls": 0},
            "fixtures": {
                "events": [{"type": "provider_error", "code": "provider_error"}]
            },
            "deterministic": {"schema_version": 1},
        }
    )

    result = await run_case(case, DecisionEntrypointTarget())

    assert result.passed is False
    assert result.error is not None
    assert result.deterministic is not None
    assert result.deterministic.task_success is False
    termination = next(
        item
        for item in result.deterministic.dimensions
        if item.dimension == "termination"
    )
    assert termination.passed is False


def test_contract_dataset_declares_versioned_specs() -> None:
    dataset = load_dataset("evals/datasets/v1-l5-contract.jsonl")

    assert dataset.dataset_version == "v1-l5-contract"
    assert len(dataset.cases) == 2
    for case in dataset.cases:
        assert case.deterministic is not None
        assert case.deterministic.schema_version == 1


@pytest.mark.asyncio
async def test_l5_contract_config_passes_through_runtime_gate() -> None:
    config = load_config("evals/config/l5-contract.yaml")
    dataset = load_dataset(config.dataset)
    assert config.target_factory is not None
    target = build_component(config.target_factory, config)

    report = await run_evaluation(config, dataset, target)

    assert [case.case_id for case in report.cases] == [
        "l5-contract-respond",
        "l5-contract-tool",
    ]
    assert all(case.passed for case in report.cases)
    assert all(
        case.deterministic is not None and case.deterministic.task_success
        for case in report.cases
    )
    assert evaluate_gate(config, report.aggregates) == []

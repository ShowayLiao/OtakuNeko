"""Regression guards for argument values and answer evidence citations."""

import pytest

from app.evaluation.dataset import load_dataset
from app.evaluation.entrypoint import DecisionEntrypointTarget
from app.evaluation.scoring import score_deterministic
from app.evaluation.types import DeterministicScore, EvalCase, ExecutionResult


def scored(case: EvalCase, result: ExecutionResult) -> DeterministicScore:
    score = score_deterministic(case, result)
    assert score is not None
    return score


def scenario(case_id):
    return next(
        case
        for case in load_dataset("evals/datasets/v2-l5-scenarios.jsonl").cases
        if case.id == case_id
    )


@pytest.mark.asyncio
async def test_wrong_argument_value_fails_even_when_keys_match():
    from app.evaluation.arguments import argument_digest

    case = scenario("l5-scenario-multi-step")
    payload = case.model_dump()
    payload["deterministic"]["arguments"]["invocations"] = [
        {
            "capability": "entrypoint.echo",
            "arguments_digest": argument_digest({"text": value}),
        }
        for value in ("first", "second")
    ]
    expected_case = EvalCase.model_validate(payload)
    actual_case = expected_case.model_copy(deep=True)
    actual_case.fixtures.events[0].arguments = {"text": "WRONG-SYNTHETIC-VALUE"}
    result = await DecisionEntrypointTarget().evaluate(actual_case)
    score = scored(expected_case, result)
    assert not score.task_success
    argument = next(item for item in score.dimensions if item.dimension == "arguments")
    assert not argument.passed
    assert "WRONG-SYNTHETIC-VALUE" not in score.model_dump_json()
    assert "WRONG-SYNTHETIC-VALUE" not in result.model_dump_json()


@pytest.mark.asyncio
async def test_argument_expectations_are_ordered_and_capability_scoped():
    from app.evaluation.arguments import argument_digest

    case = scenario("l5-scenario-multi-step")
    result = await DecisionEntrypointTarget().evaluate(case)
    payload = case.model_dump()
    payload["deterministic"]["arguments"]["invocations"] = [
        {
            "capability": "entrypoint.echo",
            "arguments_digest": argument_digest({"text": value}),
        }
        for value in ("first", "second")
    ]
    expected = EvalCase.model_validate(payload)
    assert scored(expected, result).task_success
    swapped = result.model_copy(
        update={"tool_arguments": list(reversed(result.tool_arguments))}
    )
    assert not scored(expected, swapped).task_success
    payload["deterministic"]["arguments"]["invocations"][0]["capability"] = (
        "entrypoint.flaky"
    )
    assert not scored(EvalCase.model_validate(payload), result).task_success
    missing = result.model_copy(update={"tool_arguments": []})
    assert not scored(expected, missing).task_success
    extra = result.model_copy(update={"tool_arguments": result.tool_arguments * 2})
    assert not scored(expected, extra).task_success


@pytest.mark.asyncio
async def test_evidence_requires_a_citation_backed_by_observed_output():
    case = scenario("l5-scenario-evidence")
    payload = case.model_dump()
    payload["deterministic"]["evidence"]["required_citations"] = ["synthetic-evidence"]
    expected = EvalCase.model_validate(payload)
    result = await DecisionEntrypointTarget().evaluate(case)
    cited = result.model_copy(update={"text": "Answer [synthetic-evidence]."})
    assert scored(expected, cited).task_success
    for answer in (
        "unrelated answer",
        "synthetic-evidence-extra",
        "synthetic-evidence",
    ):
        uncited = cited.model_copy(update={"text": answer})
        assert not scored(expected, uncited).task_success
    ungrounded = cited.model_copy(update={"evidence": []})
    assert not scored(expected, ungrounded).task_success


@pytest.mark.asyncio
async def test_current_gate_datasets_reject_value_and_citation_regressions():
    from app.evaluation.runner import run_case

    for dataset_path, case_id, mutation in (
        ("evals/datasets/v3-l5-scenarios.jsonl", "l5-scenario-multi-step", "arguments"),
        ("evals/datasets/v3-l5-scenarios.jsonl", "l5-scenario-evidence", "citation"),
        ("evals/datasets/v2-l5-contract.jsonl", "l5-contract-tool", "arguments"),
    ):
        case = next(
            item for item in load_dataset(dataset_path).cases if item.id == case_id
        )
        if mutation == "arguments":
            case.fixtures.events[0].arguments = {"text": "wrong-synthetic-value"}
        else:
            case.fixtures.events[-1].content = "An unrelated answer."
        result = await run_case(case, DecisionEntrypointTarget())
        assert not result.passed
        assert result.run_status == "completed"
        assert result.run_id == f"eval-{case.id}"
        assert result.deterministic is not None
        assert not result.deterministic.task_success


@pytest.mark.asyncio
async def test_argument_capture_observes_actual_capability_inputs(monkeypatch):
    from app.evaluation.entrypoint import _EntrypointEchoCapability
    from app.evaluation.runner import run_case

    original = _EntrypointEchoCapability.execute

    async def mutated_execute(self, action, **kwargs):
        kwargs["text"] = "mutated-after-model-decision"
        return await original(self, action, **kwargs)

    monkeypatch.setattr(_EntrypointEchoCapability, "execute", mutated_execute)
    case = next(
        case
        for case in load_dataset("evals/datasets/v2-l5-contract.jsonl").cases
        if case.id == "l5-contract-tool"
    )
    result = await run_case(case, DecisionEntrypointTarget())
    assert result.run_status == "completed"
    assert not result.passed
    assert result.deterministic is not None
    assert not next(
        item
        for item in result.deterministic.dimensions
        if item.dimension == "arguments"
    ).passed
    assert "mutated-after-model-decision" not in result.model_dump_json()

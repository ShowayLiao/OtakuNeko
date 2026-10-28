"""The tutorial task definitions execute through the shared Runtime."""

import pytest

from app.evaluation.config import load_config
from app.evaluation.controlled import validate_controlled_capabilities
from app.evaluation.dataset import load_dataset
from app.evaluation.entrypoint import create_entrypoint_target
from app.evaluation.runner import run_evaluation


def test_controlled_task_profile_adds_only_local_profile_action():
    assert validate_controlled_capabilities(
        "controlled-task-v1", ["generate_user_profile_tool"]
    ) == frozenset({"generate_user_profile_tool"})
    with pytest.raises(ValueError):
        validate_controlled_capabilities(
            "controlled-v1", ["generate_user_profile_tool"]
        )
    with pytest.raises(ValueError):
        validate_controlled_capabilities("controlled-task-v1", ["delete_schedule"])


@pytest.mark.asyncio
async def test_offline_task_checks_multistep_final_result(tmp_path):
    config = load_config("evals/config/task-benchmark-offline.yaml")
    config.transcript_dir = str(tmp_path)
    dataset = load_dataset(config.dataset)
    report = await run_evaluation(config, dataset, create_entrypoint_target(config))
    assert report.failed_count == 0
    assert report.cases[0].step_count == 3
    assert report.cases[0].deterministic.task_success
    assert report.cases[0].transcript_path


def test_live_task_configuration_has_real_router_and_final_result_contract():
    config = load_config("evals/config/task-benchmark.yaml")
    assert config.routing.enabled
    assert config.controlled.external_fixtures == "controlled-task-v1"
    dataset = load_dataset(config.dataset)
    assert {case.expected_agent for case in dataset.cases} == {
        "fallback",
        "recommendation",
    }
    multi = next(case for case in dataset.cases if case.id == "task-multi-tool-result")
    assert multi.deterministic.final_answer.expected_json == {
        "collection_empty": True,
        "first_result_id": 400602,
    }
    assert len(multi.deterministic.tools.required) == 2


def test_task_configs_are_in_configuration_inventory():
    from scripts.check_configuration import CHECKED_PATHS

    assert "backend/evals/config/task-benchmark.yaml" in CHECKED_PATHS
    assert "backend/evals/config/task-benchmark-offline.yaml" in CHECKED_PATHS


@pytest.mark.asyncio
@pytest.mark.parametrize("correct", [True, False])
async def test_live_task_path_checks_actual_final_result_with_fake_provider(
    monkeypatch, tmp_path, correct
):
    from app.evaluation import adapter, real_model
    from app.evaluation.scripted_llm import ScriptedLLM
    from app.evaluation.types import ScriptEvent

    class Gateway(ScriptedLLM):
        async def close(self):
            return None

    answer = (
        '{"collection_empty":true,"first_result_id":400602}'
        if correct
        else '{"collection_empty":true,"first_result_id":1}'
    )
    events = [
        ScriptEvent(type="tool_call_start", name="list_collections", arguments={}),
        ScriptEvent(
            type="tool_call_start",
            name="search_anime_advanced",
            arguments={"keyword": "Frieren"},
        ),
        ScriptEvent(type="message_chunk", content=answer),
    ]
    monkeypatch.setenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
    monkeypatch.setattr(
        adapter,
        "OpenAIModelGateway",
        lambda **kwargs: Gateway(ScriptedLLM.script_steps(events)),
    )
    config = load_config("evals/config/task-benchmark.yaml")
    config.transcript_dir = str(tmp_path)
    dataset = load_dataset(config.dataset)
    dataset = dataset.model_copy(update={"cases": [dataset.cases[0]]})
    target = real_model.build_real_model_target(
        config, api_key="synthetic-key", transcript_dir=tmp_path
    )
    report = await run_evaluation(config, dataset, target)
    result = report.cases[0]
    assert result.error is None
    assert result.route_observed and result.route_agent == "fallback"
    assert set(result.capabilities) == {"list_collections", "search_anime_advanced"}
    assert result.passed is correct
    assert report.aggregates["loop_success_rate"] == float(correct)
    assert result.transcript_path

"""Versioned L5 OtakuNeko scenario dataset tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.capabilities.registry import CapabilityRegistry
from app.evaluation.config import load_config
from app.evaluation.dataset import load_dataset
from app.evaluation.entrypoint import (
    DecisionEntrypointTarget,
    _EntrypointEchoCapability,
    run_headless_case,
)
from app.evaluation.runner import (
    build_component,
    evaluate_gate,
    run_case,
    run_evaluation,
)
from app.evaluation.scripted_llm import ScriptedLLM

DATASET = "evals/datasets/v1-l5-scenarios.jsonl"
CONFIG = "evals/config/l5-scenarios.yaml"
EXPECTED_IDS = [
    "l5-scenario-single-step",
    "l5-scenario-multi-step",
    "l5-scenario-error-recovery",
    "l5-scenario-write-approval",
]
SECRET_MARKERS = (
    "api_key",
    "apikey",
    "password",
    "secret",
    "bearer ",
    "sk-",
    "database_url",
    "authorization:",
)


def _dataset():
    return load_dataset(DATASET)


def test_scenario_dataset_is_versioned_and_isolated() -> None:
    dataset = _dataset()

    assert dataset.dataset_version == "v1-l5-scenarios"
    assert [case.id for case in dataset.cases] == EXPECTED_IDS
    user_ids = [case.user_fixture.user_id for case in dataset.cases]
    assert len(set(user_ids)) == len(user_ids)
    assert all(user_id >= 900 for user_id in user_ids)
    for case in dataset.cases:
        assert "l5-scenarios" in case.tags
        assert case.deterministic is not None
        assert case.deterministic.schema_version == 1


def test_scenario_dataset_contains_no_secret_or_real_user_data() -> None:
    payloads: list[str] = []
    for case in _dataset().cases:
        payloads.extend(message.content for message in case.input_messages)
        payloads.extend(fixture.content for fixture in case.memory_fixtures)
        payloads.extend(str(value) for value in case.user_fixture.attributes.values())
        for event in case.fixtures.events:
            payloads.extend(
                str(value)
                for value in (
                    event.content,
                    event.name,
                    event.arguments,
                    event.output,
                    event.code,
                )
                if value is not None
            )
        payloads.extend(approval.action for approval in case.approvals)

    combined = "\n".join(payloads).lower()
    assert [marker for marker in SECRET_MARKERS if marker in combined] == []


@pytest.mark.asyncio
async def test_scenario_gate_passes_through_real_runtime_path() -> None:
    config = load_config(CONFIG)
    dataset = load_dataset(config.dataset)
    target = build_component(config.target_factory, config)

    report = await run_evaluation(config, dataset, target)

    assert [case.case_id for case in report.cases] == EXPECTED_IDS
    assert all(case.passed for case in report.cases)
    assert all(
        case.deterministic is not None and case.deterministic.task_success
        for case in report.cases
    )
    assert evaluate_gate(config, report.aggregates) == []


@pytest.mark.asyncio
async def test_approval_fixture_executes_write_exactly_once() -> None:
    case = next(
        item for item in _dataset().cases if item.id == "l5-scenario-write-approval"
    )
    capability = _EntrypointEchoCapability()
    registry = CapabilityRegistry()
    registry.register(capability)
    gateway = ScriptedLLM.from_script_events(case.fixtures.events)

    result, _events = await run_headless_case(
        case,
        registry=registry,
        model_gateway=gateway,
        model="entrypoint-fixture-v1",
        fail_on_run_failure=True,
        observation_failure_source=lambda: gateway.observation_failures,
        approvals=case.approvals,
    )

    assert result.run_status == "completed"
    assert capability.writes == ["synthetic-approved"]


@pytest.mark.asyncio
async def test_write_without_approval_is_denied_and_not_scored_as_success() -> None:
    case = next(
        item for item in _dataset().cases if item.id == "l5-scenario-write-approval"
    )
    denied = case.model_copy(update={"approvals": []})

    result = await run_case(denied, DecisionEntrypointTarget())

    assert result.passed is False
    assert result.error is not None
    assert result.deterministic is not None
    assert result.deterministic.task_success is False


def test_scenario_file_is_valid_jsonl_with_manifest() -> None:
    lines = [
        json.loads(line)
        for line in Path(DATASET).read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert lines[0] == {"dataset_version": "v1-l5-scenarios", "schema_version": 1}
    assert len(lines) == len(EXPECTED_IDS) + 1

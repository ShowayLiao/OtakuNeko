"""Dataset schema and golden-case coverage for EVAL-001."""

from __future__ import annotations

import json

import pytest

from app.evaluation.dataset import load_dataset


def _write_dataset(tmp_path, cases):
    path = tmp_path / "dataset.jsonl"
    lines = [json.dumps({"dataset_version": "test-v1", "schema_version": 1})]
    lines.extend(json.dumps(case) for case in cases)
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def _case(case_id="case-1", **overrides):
    value = {
        "id": case_id,
        "category": "anime_knowledge",
        "input_messages": [{"role": "user", "content": "test"}],
        "user_fixture": {"user_id": 1},
        "memory_fixtures": [],
        "expected_route": "chat",
        "required_capabilities": [],
        "forbidden_capabilities": [],
        "forbidden_phrases": [],
        "assertions": {
            "response_schema": "text",
            "required_evidence": [],
            "max_latency_ms": 100,
            "max_calls": 2,
        },
        "fixtures": {
            "events": [
                {"type": "route", "route": "chat"},
                {"type": "message_chunk", "content": "ok"},
            ],
        },
        "tags": ["fast"],
    }
    value.update(overrides)
    return value


def test_loads_explicit_dataset_version_and_fixtures(tmp_path):
    dataset = load_dataset(_write_dataset(tmp_path, [_case()]))

    assert dataset.dataset_version == "test-v1"
    assert dataset.schema_version == 1
    assert dataset.cases[0].user_fixture.user_id == 1
    assert dataset.cases[0].fixtures.events[0].route == "chat"


def test_duplicate_case_ids_fail(tmp_path):
    path = _write_dataset(tmp_path, [_case(), _case()])

    with pytest.raises(ValueError, match="Duplicate case id"):
        load_dataset(path)


def test_unknown_nested_fields_fail(tmp_path):
    case = _case()
    case["fixtures"]["events"][0]["secret_extra"] = "nope"

    with pytest.raises(ValueError, match="secret_extra"):
        load_dataset(_write_dataset(tmp_path, [case]))


def test_unknown_input_message_fields_fail(tmp_path):
    case = _case()
    case["input_messages"][0]["credential"] = "must-not-be-accepted"

    with pytest.raises(ValueError, match="credential"):
        load_dataset(_write_dataset(tmp_path, [case]))


def test_missing_manifest_fails(tmp_path):
    path = tmp_path / "dataset.jsonl"
    path.write_text(json.dumps(_case()), encoding="utf-8")

    with pytest.raises(ValueError, match="manifest"):
        load_dataset(path)


def test_real_dataset_covers_required_scenarios():
    dataset = load_dataset("evals/datasets/v1.jsonl")
    categories = {case.category.value for case in dataset.cases}
    tags = {tag for case in dataset.cases for tag in case.tags}

    assert {
        "anime_knowledge",
        "recommendation",
        "companion",
        "routing",
        "safety",
        "recovery",
    } <= categories
    assert {"ambiguous", "provider_failure", "cancellation"} <= tags

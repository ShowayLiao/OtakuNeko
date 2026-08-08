from __future__ import annotations

import json

import pytest

from app.harness.contracts import AgentDecision, ErrorCode
from app.harness.decision_parser import DecisionParseError, DecisionParser
from app.harness.model_types import ModelCallResult


def _result(payload: dict) -> ModelCallResult:
    return ModelCallResult(
        provider="fake",
        model="fake-model",
        operation="infer",
        status="completed",
        decision=payload,
    )


def test_valid_invoke_decision_is_canonical_and_versioned() -> None:
    decision = DecisionParser().parse(
        _result(
            {
                "schema_version": "v1",
                "decision_id": "decision-1",
                "run_id": "run-1",
                "action": "invoke",
                "capability": "catalog.search",
                "capability_version": "v1",
                "arguments": {"query": "anime"},
            }
        )
    )

    assert isinstance(decision, AgentDecision)
    assert decision.capability == "catalog.search"
    assert decision.capability_version == "v1"


@pytest.mark.parametrize("action", ["respond", "finish"])
def test_terminal_decisions_do_not_become_invocations(action: str) -> None:
    decision = DecisionParser().parse(
        _result(
            {
                "schema_version": "v1",
                "decision_id": "decision-1",
                "run_id": "run-1",
                "action": action,
                "content": "done",
            }
        )
    )

    assert decision.action == action
    assert DecisionParser.to_invocation(decision) is None


@pytest.mark.parametrize("action", ["respond", "finish"])
def test_terminal_decision_without_id_gets_runtime_correlation_id(action: str) -> None:
    decision = DecisionParser().parse(
        _result(
            {
                "schema_version": "v1",
                "action": action,
                "content": "done",
            }
        ),
        expected_run_id="run-1",
    )

    assert decision.run_id == "run-1"
    assert decision.decision_id
    assert decision.action == action


def test_invoke_decision_without_id_gets_runtime_correlation_id() -> None:
    decision = DecisionParser().parse(
        _result(
            {
                "schema_version": "v1",
                "action": "invoke",
                "capability": "catalog.search",
                "capability_version": "v1",
                "arguments": {"query": "anime"},
            }
        ),
        expected_run_id="run-1",
    )

    assert decision.action == "invoke"
    assert decision.decision_id
    assert decision.run_id == "run-1"


@pytest.mark.parametrize(
    "payload",
    [
        {"action": "invoke", "capability": "catalog.search"},
        {"action": "invoke", "capability_version": "v1"},
        {"action": "unknown", "capability": "catalog.search", "capability_version": "v1"},
        {"action": "invoke", "capability": "catalog.search", "capability_version": "v2"},
    ],
)
def test_invalid_invoke_shape_is_rejected_without_provider_payload(payload: dict) -> None:
    with pytest.raises(DecisionParseError) as exc_info:
        DecisionParser().parse(_result(payload))

    assert exc_info.value.error_code == ErrorCode.INVALID_REQUEST
    assert "fake" not in str(exc_info.value)


@pytest.mark.parametrize("field", ["user_id", "principal_id", "tenant_id", "db", "token"])
def test_model_owned_authority_fields_are_rejected(field: str) -> None:
    payload = {
        "schema_version": "v1",
        "decision_id": "decision-1",
        "run_id": "run-1",
        "action": "invoke",
        "capability": "catalog.search",
        "capability_version": "v1",
        "arguments": {field: "forged"},
    }

    with pytest.raises(DecisionParseError) as exc_info:
        DecisionParser().parse(_result(payload))

    assert exc_info.value.error_code == ErrorCode.INVALID_REQUEST
    assert exc_info.value.retryable is False


def test_provider_json_and_multiple_tool_calls_fail_closed() -> None:
    invalid_json = ModelCallResult(
        provider="fake",
        model="fake-model",
        operation="infer",
        status="completed",
        text='{"action": "invoke"',
    )
    with pytest.raises(DecisionParseError) as invalid_info:
        DecisionParser().parse(invalid_json)
    assert invalid_info.value.error_code == ErrorCode.INVALID_REQUEST

    multiple = ModelCallResult(
        provider="fake",
        model="fake-model",
        operation="infer",
        status="completed",
        tool_calls=[
            {"name": "catalog.search", "arguments": {}, "version": "v1"},
            {"name": "catalog.search", "arguments": {}, "version": "v1"},
        ],
    )
    with pytest.raises(DecisionParseError):
        DecisionParser().parse(multiple)


def test_provider_json_wrapped_in_markdown_fence_is_parsed() -> None:
    result = ModelCallResult(
        provider="fake",
        model="fake-model",
        operation="infer",
        status="completed",
        text='```json\n{"schema_version":"v1","action":"finish","content":"done"}\n```',
    )

    decision = DecisionParser().parse(result, expected_run_id="run-1")

    assert decision.action == "finish"
    assert decision.content == "done"
    assert decision.run_id == "run-1"


def test_oversized_arguments_are_rejected_and_error_is_safe() -> None:
    payload = {
        "schema_version": "v1",
        "decision_id": "decision-1",
        "run_id": "run-1",
        "action": "invoke",
        "capability": "catalog.search",
        "capability_version": "v1",
        "arguments": {"query": "x" * 9000},
    }

    with pytest.raises(DecisionParseError) as exc_info:
        DecisionParser(max_arguments_bytes=1024).parse(_result(payload))
    assert exc_info.value.error_code == ErrorCode.INVALID_REQUEST
    assert json.dumps(payload) not in str(exc_info.value)

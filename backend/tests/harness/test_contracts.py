import json

import pytest
from pydantic import ValidationError

from app.harness.contracts import (
    AgentDecision,
    ErrorCode,
    ExecutionContext,
    InvocationRequest,
    InvocationResult,
    RunEvent,
    RunRequest,
    RunResult,
)


def test_versioned_contracts_json_serialize_with_factory_defaults() -> None:
    request = RunRequest(
        run_id="run-1",
        user_id=7,
        goal="find anime",
        model="test-model",
    )
    first_event = RunEvent(run_id="run-1", sequence=1, event_type="message_start")
    second_event = RunEvent(run_id="run-1", sequence=2, event_type="message_end")

    assert request.schema_version == "v1"
    assert first_event.payload == {}
    assert second_event.payload == {}
    assert first_event.payload is not second_event.payload
    assert json.loads(request.model_dump_json())["run_id"] == "run-1"


def test_execution_context_uses_trusted_principal_and_frozen_allowlist() -> None:
    context = ExecutionContext(
        principal_id=7,
        run_id="run-1",
        trace_id="trace-1",
        capability_allowlist=frozenset({"anime.search"}),
    )

    assert context.principal_id == 7
    assert context.capability_allowlist == frozenset({"anime.search"})
    assert "user_id" not in InvocationRequest.model_fields


def test_invocation_contracts_reject_model_owned_identity_arguments() -> None:
    with pytest.raises(ValidationError):
        InvocationRequest(
            invocation_id="inv-1",
            run_id="run-1",
            capability="anime.search",
            capability_version="v1",
            arguments={"query": "x", "user_id": 7},
        )

    with pytest.raises(ValidationError):
        AgentDecision(
            decision_id="decision-1",
            run_id="run-1",
            action="invoke",
            capability="anime.search",
            arguments={"principal_id": 7},
        )


def test_invocation_result_and_run_result_use_structured_error_codes() -> None:
    invocation = InvocationResult(
        invocation_id="inv-1",
        status="failed",
        error_code=ErrorCode.TOOL_ERROR,
        retryable=True,
    )
    result = RunResult(
        run_id="run-1",
        status="failed",
        error_code=ErrorCode.TOOL_ERROR,
    )

    assert invocation.output == {}
    assert invocation.error_code == ErrorCode.TOOL_ERROR
    assert result.content is None
    assert set(item.value for item in ErrorCode) == {
        "invalid_request",
        "unauthorized",
        "policy_denied",
        "timeout",
        "cancelled",
        "budget_exceeded",
        "provider_error",
        "tool_error",
        "transient",
        "permanent",
    }

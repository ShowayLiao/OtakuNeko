from __future__ import annotations

import json

import pytest

from app.harness.contracts import ExecutionContext
from app.harness.decision_trace import DecisionTraceProjection
from app.harness.task import AgentTask
from app.trace import TraceEventType


def _context() -> ExecutionContext:
    return ExecutionContext(
        principal_id=17,
        run_id="trusted-run",
        trace_id="trusted-trace",
    )


def _task() -> AgentTask:
    return AgentTask(user_id=99, goal="SYNTHETIC_PRIVATE_PROMPT")


def test_projection_uses_trusted_identity_and_never_copies_task_goal() -> None:
    projection = DecisionTraceProjection(_context(), _task())

    assert projection.trace.trace_id == "trusted-trace"
    assert projection.trace.run_id == "trusted-run"
    assert projection.trace.user_id == 17
    assert projection.trace.agent_name == "primary-runtime"
    assert projection.trace.goal == ""


@pytest.mark.parametrize(
    ("event_type", "expected_type", "expected_status"),
    [
        ("model_call", TraceEventType.MODEL_CALL, "running"),
        ("tool_call_start", TraceEventType.TOOL_CALL_START, "running"),
        ("tool_call_end", TraceEventType.TOOL_CALL_END, "completed"),
        ("policy_denied", TraceEventType.FAILURE, "failed"),
        ("run_failed", TraceEventType.FAILURE, "failed"),
        ("error", TraceEventType.FAILURE, "failed"),
        ("budget_exceeded", TraceEventType.FAILURE, "failed"),
        ("run_completed", TraceEventType.AGENT_RESULT, "completed"),
        ("cancelled", TraceEventType.AGENT_RESULT, "cancelled"),
        ("timeout", TraceEventType.AGENT_RESULT, "timeout"),
        ("run_cancelled", TraceEventType.AGENT_RESULT, "cancelled"),
        ("run_timeout", TraceEventType.AGENT_RESULT, "timeout"),
    ],
)
def test_observe_maps_runtime_event_types(
    event_type: str,
    expected_type: TraceEventType,
    expected_status: str,
) -> None:
    projection = DecisionTraceProjection(_context(), _task())

    event = {"type": event_type}
    if event_type == "tool_call_end":
        event["status"] = "succeeded"
    projection.observe(event)

    [step] = projection.trace.steps
    [trace_event] = step.events
    assert trace_event.event_type == expected_type
    assert trace_event.status == expected_status


@pytest.mark.parametrize(
    ("runtime_status", "trace_status"),
    [
        ("success", "completed"),
        ("succeeded", "completed"),
        ("completed", "completed"),
        ("failure", "failed"),
        ("failed", "failed"),
        ("denied", "failed"),
        ("timeout", "timeout"),
        ("cancelled", "cancelled"),
        ("canceled", "cancelled"),
        ("running", "running"),
    ],
)
def test_observe_normalizes_event_statuses(
    runtime_status: str, trace_status: str
) -> None:
    projection = DecisionTraceProjection(_context(), _task())

    projection.observe({"type": "tool_call_end", "status": runtime_status})

    assert projection.trace.steps[0].events[0].status == trace_status


def test_observe_keeps_only_safe_fields_and_uses_context_run_id() -> None:
    projection = DecisionTraceProjection(_context(), _task())
    event = {
        "type": "model_call",
        "run_id": "attacker-run",
        "trace_id": "attacker-trace",
        "sequence": 4,
        "event_id": "runtime-event-4",
        "invocation_id": ["not-a-string"],
        "provider": "test-provider",
        "model": "test-model",
        "usage": {
            "prompt_tokens": 5,
            "completion_tokens": 3,
            "total_tokens": 8,
            "latency_ms": 11,
            "estimated_cost_usd": "0.001",
            "api_key": "SYNTHETIC_USAGE_SECRET",
            "arbitrary": "SYNTHETIC_USAGE_ARBITRARY",
        },
        "duration_ms": 12.5,
        "error_code": "provider_error",
        "arguments": "SYNTHETIC_ARGUMENTS",
        "output": "SYNTHETIC_OUTPUT",
        "content": "SYNTHETIC_CONTENT",
        "prompt": "SYNTHETIC_PROMPT",
        "exception": "SYNTHETIC_EXCEPTION",
        "raw_provider_payload": "SYNTHETIC_RAW_PROVIDER_PAYLOAD",
        "arbitrary": "SYNTHETIC_ARBITRARY",
    }

    projection.observe(event)

    [trace_event] = projection.trace.steps[0].events
    assert trace_event.run_id == "trusted-run"
    assert trace_event.sequence == 4
    assert trace_event.event_id == "runtime-event-4"
    assert trace_event.invocation_id is None
    assert trace_event.provider == "test-provider"
    assert trace_event.model == "test-model"
    assert trace_event.usage == {
        "prompt_tokens": 5,
        "completion_tokens": 3,
        "total_tokens": 8,
        "latency_ms": 11,
        "estimated_cost_usd": "0.001",
    }
    assert trace_event.duration_ms == 12.5
    assert trace_event.error_code == "provider_error"
    assert trace_event.data == {}

    serialized = json.dumps(projection.trace.model_dump(mode="json"))
    for private_value in (
        "SYNTHETIC_PRIVATE_PROMPT",
        "SYNTHETIC_USAGE_SECRET",
        "SYNTHETIC_USAGE_ARBITRARY",
        "SYNTHETIC_ARGUMENTS",
        "SYNTHETIC_OUTPUT",
        "SYNTHETIC_CONTENT",
        "SYNTHETIC_PROMPT",
        "SYNTHETIC_EXCEPTION",
        "SYNTHETIC_RAW_PROVIDER_PAYLOAD",
        "SYNTHETIC_ARBITRARY",
        "attacker-run",
        "attacker-trace",
    ):
        assert private_value not in serialized


def test_observe_preserves_string_invocation_id_and_skips_unknown_events() -> None:
    projection = DecisionTraceProjection(_context(), _task())

    projection.observe({"type": "unrecognized_event", "content": "ignore"})
    assert projection.trace.steps == []

    projection.observe(
        {
            "type": "tool_call_start",
            "sequence": 2,
            "event_id": "runtime-event-2",
            "invocation_id": "invocation-2",
            "run_id": "attacker-run",
        }
    )

    [trace_event] = projection.trace.steps[0].events
    assert trace_event.run_id == "trusted-run"
    assert trace_event.sequence == 2
    assert trace_event.event_id == "runtime-event-2"
    assert trace_event.invocation_id == "invocation-2"


def test_observe_drops_invalid_metrics_without_failing_projection() -> None:
    projection = DecisionTraceProjection(_context(), _task())

    projection.observe(
        {
            "type": "model_call",
            "sequence": 0,
            "duration_ms": 10**10000,
            "latency_ms": float("inf"),
            "usage": {
                "prompt_tokens": True,
                "completion_tokens": 4,
                "total_tokens": -1,
            },
        }
    )

    [trace_event] = projection.trace.steps[0].events
    assert trace_event.sequence is None
    assert trace_event.duration_ms is None
    assert trace_event.latency_ms is None
    assert trace_event.usage == {"completion_tokens": 4}


@pytest.mark.parametrize(
    ("status", "expected_status", "expected_step_status"),
    [
        ("completed", "completed", "completed"),
        ("failed", "failed", "failed"),
        ("cancelled", "cancelled", "cancelled"),
    ],
)
def test_finish_sets_terminal_status_and_finalizes_steps(
    status: str, expected_status: str, expected_step_status: str
) -> None:
    projection = DecisionTraceProjection(_context(), _task())
    projection.observe({"type": "tool_call_start"})

    trace = projection.finish(status, "provider_error")

    assert trace is projection.trace
    assert trace.status == expected_status
    assert trace.completed_at is not None
    assert trace.total_duration_ms is not None
    assert trace.total_duration_ms >= 0
    assert trace.steps[0].status == expected_step_status
    assert trace.steps[0].completed_at is not None
    if status == "failed":
        assert trace.error == "provider_error"


def test_finish_keeps_paused_projection_running() -> None:
    projection = DecisionTraceProjection(_context(), _task())
    projection.observe({"type": "tool_call_start"})

    trace = projection.finish("paused")

    assert trace.status == "running"
    assert trace.completed_at is None
    assert trace.steps[0].status == "running"
    assert trace.steps[0].completed_at is None

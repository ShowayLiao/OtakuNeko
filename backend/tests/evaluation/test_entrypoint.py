"""Runtime-owned headless evaluation entrypoint tests."""

from __future__ import annotations

import importlib

import pytest

from app.evaluation.adapter import normalize_events
from app.evaluation.config import load_config
from app.evaluation.dataset import load_dataset
from app.evaluation.runner import build_component, run_evaluation
from app.evaluation.scripted_llm import (
    ObservationExpectation,
    ScriptedLLM,
    ScriptedObservationError,
    ScriptedStep,
)
from app.evaluation.types import EvalCase
from app.trace import TraceEventType
from app.trace.sql_store import SqlTraceStore


@pytest.mark.parametrize(
    ("event_type", "expected_status"),
    [
        ("run_completed", "completed"),
        ("run_failed", "failed"),
        ("run_cancelled", "cancelled"),
        ("run_timeout", "timeout"),
    ],
)
def test_normalizer_preserves_canonical_runtime_terminal_status(
    event_type: str,
    expected_status: str,
) -> None:
    result = normalize_events(
        [{"type": event_type}],
        response_schema="text",
        run_id="eval-terminal",
    )

    assert result.run_status == expected_status


def test_normalizer_counts_succeeded_runtime_invocation_as_success() -> None:
    result = normalize_events(
        [
            {
                "type": "tool_call_end",
                "invocation_id": "invocation-1",
                "capability": "entrypoint.echo",
                "status": "succeeded",
            },
            {"type": "run_completed"},
        ],
        response_schema="text",
        run_id="eval-tool",
    )

    assert result.tool_call_count == 1
    assert result.tool_success_count == 1
    assert result.tool_failure_count == 0
    assert result.capabilities == ["entrypoint.echo"]


def test_normalizer_counts_denied_runtime_invocation_as_failure() -> None:
    result = normalize_events(
        [
            {
                "type": "tool_call_end",
                "invocation_id": "invocation-denied",
                "capability": "not.registered",
                "status": "denied",
            },
            {"type": "run_completed"},
        ],
        response_schema="text",
        run_id="eval-denied",
    )

    assert result.tool_failure_count == 1
    assert result.policy_denied_count == 1


def _entrypoint_case(case_id: str, events: list[dict]) -> EvalCase:
    return EvalCase.model_validate(
        {
            "id": case_id,
            "category": "routing",
            "input_messages": [{"role": "user", "content": "Run the fixture."}],
            "user_fixture": {"user_id": 501},
            "expected_route": "chat",
            "assertions": {"max_latency_ms": 5000, "max_calls": 2},
            "fixtures": {"events": events},
        }
    )


async def _capture_traces(monkeypatch):
    traces = []
    query = SqlTraceStore.query

    async def capture(self, trace_id: str, *, user_id: int | None = None):
        trace = await query(self, trace_id, user_id=user_id)
        traces.append(trace)
        return trace

    monkeypatch.setattr(SqlTraceStore, "query", capture)
    return traces


@pytest.mark.asyncio
async def test_entrypoint_read_runs_through_runtime_dispatcher_and_sql_trace(
    monkeypatch,
) -> None:
    entrypoint = importlib.import_module("app.evaluation.entrypoint")
    traces = await _capture_traces(monkeypatch)
    target = entrypoint.DecisionEntrypointTarget()
    case = _entrypoint_case(
        "headless-read",
        [
            {
                "type": "tool_call_start",
                "name": "entrypoint.echo",
                "arguments": {"text": "fixture input"},
            },
            {"type": "message_chunk", "content": "synthetic-result"},
        ],
    )

    result = await target.evaluate(case)

    assert result.run_status == "completed"
    assert result.text == "synthetic-result"
    assert result.capabilities == ["entrypoint.echo"]
    assert result.tool_success_count == 1
    assert len(traces) == 1
    trace = traces[0]
    assert trace is not None
    assert trace.trace_id == trace.run_id == result.run_id
    trace_types = {event.event_type for step in trace.steps for event in step.events}
    assert TraceEventType.MODEL_CALL in trace_types
    assert TraceEventType.TOOL_CALL_START in trace_types
    assert TraceEventType.TOOL_CALL_END in trace_types


@pytest.mark.asyncio
async def test_entrypoint_repeated_cases_use_independent_sql_sessions() -> None:
    entrypoint = importlib.import_module("app.evaluation.entrypoint")
    target = entrypoint.DecisionEntrypointTarget()
    case = _entrypoint_case(
        "headless-repeat",
        [{"type": "message_chunk", "content": "fixture response"}],
    )

    first = await target.evaluate(case)
    second = await target.evaluate(case)

    assert first.run_id == second.run_id == "eval-headless-repeat"
    assert first.run_status == second.run_status == "completed"


@pytest.mark.asyncio
async def test_entrypoint_denies_unknown_capability_without_reporting_success(
    monkeypatch,
) -> None:
    entrypoint = importlib.import_module("app.evaluation.entrypoint")
    traces = await _capture_traces(monkeypatch)
    target = entrypoint.DecisionEntrypointTarget()
    case = _entrypoint_case(
        "headless-denied",
        [
            {
                "type": "tool_call_start",
                "name": "unregistered.write",
                "arguments": {},
            },
            {"type": "message_chunk", "content": "fixture response"},
        ],
    )

    with pytest.raises(RuntimeError, match="headless Runtime run failed"):
        await target.evaluate(case)

    trace = traces[0]
    assert trace is not None
    tool_ends = [
        event
        for step in trace.steps
        for event in step.events
        if event.event_type == TraceEventType.TOOL_CALL_END
    ]
    assert len(tool_ends) == 1
    assert tool_ends[0].status == "failed"
    assert tool_ends[0].error_code == "not_configured"


@pytest.mark.asyncio
async def test_entrypoint_provider_failure_requires_failed_canonical_run(
    monkeypatch,
) -> None:
    entrypoint = importlib.import_module("app.evaluation.entrypoint")
    traces = await _capture_traces(monkeypatch)
    target = entrypoint.DecisionEntrypointTarget()
    case = _entrypoint_case(
        "headless-provider-failure",
        [{"type": "provider_error", "code": "permanent"}],
    )

    with pytest.raises(RuntimeError, match="headless Runtime run failed"):
        await target.evaluate(case)

    trace = traces[0]
    assert trace is not None
    assert trace.status == "failed"
    assert trace.trace_id == trace.run_id == "eval-headless-provider-failure"


@pytest.mark.asyncio
async def test_entrypoint_fails_closed_when_sql_trace_is_missing(monkeypatch) -> None:
    entrypoint = importlib.import_module("app.evaluation.entrypoint")

    async def missing_trace(self, trace_id: str, *, user_id: int | None = None):
        return None

    monkeypatch.setattr(SqlTraceStore, "query", missing_trace)
    target = entrypoint.DecisionEntrypointTarget()
    case = _entrypoint_case(
        "headless-missing-trace",
        [{"type": "message_chunk", "content": "fixture response"}],
    )

    with pytest.raises(RuntimeError, match="headless Runtime trace unavailable"):
        await target.evaluate(case)


@pytest.mark.asyncio
async def test_entrypoint_fails_closed_when_normalized_result_mismatches_runtime(
    monkeypatch,
) -> None:
    entrypoint = importlib.import_module("app.evaluation.entrypoint")
    normalize = entrypoint.normalize_events

    def mismatched_status(*args, **kwargs):
        result = normalize(*args, **kwargs)
        return result.model_copy(update={"run_status": "failed"})

    monkeypatch.setattr(entrypoint, "normalize_events", mismatched_status)
    target = entrypoint.DecisionEntrypointTarget()
    case = _entrypoint_case(
        "headless-canonical-mismatch",
        [{"type": "message_chunk", "content": "fixture response"}],
    )

    with pytest.raises(
        RuntimeError,
        match="headless Runtime canonical result mismatch",
    ):
        await target.evaluate(case)


@pytest.mark.asyncio
async def test_entrypoint_fails_closed_when_trace_correlation_mismatches(
    monkeypatch,
) -> None:
    entrypoint = importlib.import_module("app.evaluation.entrypoint")
    query = SqlTraceStore.query

    async def mismatched_trace(self, trace_id: str, *, user_id: int | None = None):
        trace = await query(self, trace_id, user_id=user_id)
        assert trace is not None
        return trace.model_copy(update={"run_id": "unrelated-run"})

    monkeypatch.setattr(SqlTraceStore, "query", mismatched_trace)
    target = entrypoint.DecisionEntrypointTarget()
    case = _entrypoint_case(
        "headless-trace-mismatch",
        [{"type": "message_chunk", "content": "fixture response"}],
    )

    with pytest.raises(
        RuntimeError,
        match="headless Runtime trace correlation missing",
    ):
        await target.evaluate(case)


@pytest.mark.asyncio
async def test_entrypoint_eval_gate_runs_all_independent_fixture_cases() -> None:
    config = load_config("evals/config/entrypoint.yaml")
    dataset = load_dataset(config.dataset)
    assert config.target_factory is not None
    target = build_component(config.target_factory, config)

    report = await run_evaluation(config, dataset, target)

    assert dataset.dataset_version == "v1-entrypoint"
    assert report.total == 3
    assert report.failed_count == 0
    assert report.aggregates["pass_rate"] == 1.0
    assert report.aggregates["routing_accuracy"] == 1.0
    assert report.aggregates["safety_pass_rate"] == 1.0
    assert len({case.run_id for case in report.cases}) == 3


async def test_production_target_uses_shared_headless_and_sql_trace(monkeypatch):
    from app.evaluation import adapter, entrypoint
    from app.capabilities.registry import CapabilityRegistry

    case = _entrypoint_case(
        "network-target-with-fake-model",
        [
            {
                "type": "tool_call_start",
                "name": "entrypoint.echo",
                "arguments": {"text": "synthetic"},
            },
            {"type": "message_chunk", "content": "synthetic-result"},
        ],
    )

    class Gateway(ScriptedLLM):
        closed = False

        def __init__(self, events):
            super().__init__(
                ScriptedLLM.script_steps(events),
                provider="entrypoint-fixture",
                model="entrypoint-fixture-v1",
            )

        async def close(self):
            self.closed = True

    gateway = Gateway(case.fixtures.events)
    registry = CapabilityRegistry()
    registry.register(entrypoint._EntrypointEchoCapability())
    traces = await _capture_traces(monkeypatch)
    monkeypatch.setenv("OPENAI_API_KEY", "synthetic-evaluation-key")
    monkeypatch.setattr(adapter, "OpenAIModelGateway", lambda **kwargs: gateway)
    monkeypatch.setattr(adapter, "build_capability_registry", lambda: registry)
    target = adapter.ProductionRuntimeTarget(load_config("evals/config/full.yaml"))
    result = await target.evaluate(case)
    assert result.run_status == "completed" and result.tool_success_count == 1
    assert gateway.closed
    assert len(traces) == 1 and traces[0] is not None
    assert traces[0].trace_id == result.run_id


def _echo_registry():
    from app.capabilities.registry import CapabilityRegistry

    entrypoint = importlib.import_module("app.evaluation.entrypoint")
    registry = CapabilityRegistry()
    registry.register(entrypoint._EntrypointEchoCapability())
    return registry


def _read_events() -> list[dict]:
    return [
        {
            "type": "tool_call_start",
            "name": "entrypoint.echo",
            "arguments": {"text": "fixture input"},
        },
        {"type": "message_chunk", "content": "synthetic-result"},
    ]


@pytest.mark.asyncio
async def test_entrypoint_read_observes_real_tool_feedback() -> None:
    entrypoint = importlib.import_module("app.evaluation.entrypoint")
    case = _entrypoint_case("headless-observes-feedback", _read_events())
    gateway = ScriptedLLM.from_script_events(case.fixtures.events)

    result, _events = await entrypoint.run_headless_case(
        case,
        registry=_echo_registry(),
        model_gateway=gateway,
        model="entrypoint-fixture-v1",
        fail_on_run_failure=True,
        observation_failure_source=lambda: gateway.observation_failures,
    )

    assert result.run_status == "completed"
    assert len(gateway.calls) == 2
    observation = gateway.calls[1]
    assert len(observation.tool_results) == 1
    payload = observation.tool_results[0]
    assert payload["safe_output"]["value"] == "synthetic-result"
    assert payload["provenance"]["trust"] == "untrusted"
    assert observation.context is not None
    assert observation.context["run_id"] == result.run_id
    assert observation.context["trace_id"] == result.run_id
    assert gateway.observation_summary() == {
        "calls": 2,
        "history_messages": 1 + 3,
        "tool_results": 1,
        "context_snapshots": 2,
        "expectations_verified": 2,
        "observation_failures": 0,
    }


@pytest.mark.asyncio
async def test_entrypoint_target_fails_closed_when_feedback_is_missing(
    monkeypatch,
) -> None:
    from app.harness import runtime as runtime_module

    entrypoint = importlib.import_module("app.evaluation.entrypoint")
    monkeypatch.setattr(
        runtime_module,
        "_tool_feedback_message",
        lambda _invocation: {
            "role": "user",
            "content": "capability feedback was not delivered",
        },
    )
    target = entrypoint.DecisionEntrypointTarget()
    case = _entrypoint_case("headless-missing-feedback", _read_events())

    with pytest.raises(ScriptedObservationError, match="expected 1 tool result"):
        await target.evaluate(case)


@pytest.mark.asyncio
async def test_entrypoint_target_fails_closed_when_feedback_is_wrong(
    monkeypatch,
) -> None:
    from app.harness import runtime as runtime_module

    entrypoint = importlib.import_module("app.evaluation.entrypoint")
    original = runtime_module._tool_feedback_message

    def wrong_feedback(invocation):
        message = original(invocation)
        message["content"] = message["content"].replace(
            "synthetic-result",
            "tampered-result",
        )
        return message

    monkeypatch.setattr(
        runtime_module,
        "_tool_feedback_message",
        wrong_feedback,
    )
    target = entrypoint.DecisionEntrypointTarget()
    case = _entrypoint_case(
        "headless-wrong-feedback",
        [
            {
                "type": "tool_call_start",
                "name": "entrypoint.echo",
                "arguments": {"text": "fixture input"},
                "output": {"value": "synthetic-result"},
            },
            {"type": "message_chunk", "content": "synthetic-result"},
        ],
    )

    with pytest.raises(ScriptedObservationError, match="safe_output.value"):
        await target.evaluate(case)


@pytest.mark.asyncio
async def test_run_headless_case_records_missing_feedback_failure(
    monkeypatch,
) -> None:
    from app.harness import runtime as runtime_module

    entrypoint = importlib.import_module("app.evaluation.entrypoint")
    monkeypatch.setattr(
        runtime_module,
        "_tool_feedback_message",
        lambda _invocation: {
            "role": "user",
            "content": "capability feedback was not delivered",
        },
    )
    case = _entrypoint_case("headless-record-missing-feedback", _read_events())
    gateway = ScriptedLLM.from_script_events(case.fixtures.events)

    with pytest.raises(ScriptedObservationError, match="expected 1 tool result"):
        await entrypoint.run_headless_case(
            case,
            registry=_echo_registry(),
            model_gateway=gateway,
            model="entrypoint-fixture-v1",
            fail_on_run_failure=False,
            observation_failure_source=lambda: gateway.observation_failures,
        )

    assert any(
        "expected 1 tool result" in failure for failure in gateway.observation_failures
    )


@pytest.mark.asyncio
async def test_run_headless_case_records_wrong_feedback_failure(
    monkeypatch,
) -> None:
    from app.harness import runtime as runtime_module

    entrypoint = importlib.import_module("app.evaluation.entrypoint")
    original = runtime_module._tool_feedback_message

    def wrong_feedback(invocation):
        message = original(invocation)
        message["content"] = message["content"].replace(
            "synthetic-result",
            "tampered-result",
        )
        return message

    monkeypatch.setattr(
        runtime_module,
        "_tool_feedback_message",
        wrong_feedback,
    )
    case = _entrypoint_case(
        "headless-record-wrong-feedback",
        [
            {
                "type": "tool_call_start",
                "name": "entrypoint.echo",
                "arguments": {"text": "fixture input"},
                "output": {"value": "synthetic-result"},
            },
            {"type": "message_chunk", "content": "synthetic-result"},
        ],
    )
    gateway = ScriptedLLM.from_script_events(case.fixtures.events)

    with pytest.raises(ScriptedObservationError, match="safe_output.value"):
        await entrypoint.run_headless_case(
            case,
            registry=_echo_registry(),
            model_gateway=gateway,
            model="entrypoint-fixture-v1",
            fail_on_run_failure=False,
            observation_failure_source=lambda: gateway.observation_failures,
        )

    assert any(
        "safe_output.value" in failure for failure in gateway.observation_failures
    )


@pytest.mark.asyncio
async def test_run_headless_case_records_wrong_expected_feedback() -> None:
    entrypoint = importlib.import_module("app.evaluation.entrypoint")
    case = _entrypoint_case("headless-explicit-wrong-feedback", _read_events())
    run_id = f"eval-{case.id}"
    gateway = ScriptedLLM(
        [
            ScriptedStep(
                decision={
                    "schema_version": "v1",
                    "decision_id": "explicit-invoke",
                    "run_id": run_id,
                    "action": "invoke",
                    "capability": "entrypoint.echo",
                    "capability_version": "v1",
                    "arguments": {"text": "fixture input"},
                }
            ),
            ScriptedStep(
                decision={
                    "schema_version": "v1",
                    "decision_id": "explicit-respond",
                    "run_id": run_id,
                    "action": "respond",
                    "content": "done",
                },
                expect=ObservationExpectation(
                    tool_results=1,
                    last_tool_result={
                        "safe_output": {"value": "not-the-real-output"},
                    },
                ),
            ),
        ]
    )

    with pytest.raises(
        ScriptedObservationError,
        match=r"last tool result\.safe_output\.value",
    ):
        await entrypoint.run_headless_case(
            case,
            registry=_echo_registry(),
            model_gateway=gateway,
            model="scripted-v1",
            fail_on_run_failure=False,
            observation_failure_source=lambda: gateway.observation_failures,
        )

    assert any(
        "last tool result.safe_output.value" in failure
        for failure in gateway.observation_failures
    )


@pytest.mark.asyncio
async def test_entrypoint_accepts_declared_tool_output() -> None:
    entrypoint = importlib.import_module("app.evaluation.entrypoint")
    case = _entrypoint_case(
        "headless-declared-output",
        [
            {
                "type": "tool_call_start",
                "name": "entrypoint.echo",
                "arguments": {"text": "fixture input"},
            },
            {
                "type": "tool_call_end",
                "name": "entrypoint.echo",
                "output": {"value": "synthetic-result"},
                "status": "succeeded",
            },
            {"type": "message_chunk", "content": "synthetic-result"},
        ],
    )
    gateway = ScriptedLLM.from_script_events(case.fixtures.events)

    result, _events = await entrypoint.run_headless_case(
        case,
        registry=_echo_registry(),
        model_gateway=gateway,
        model="entrypoint-fixture-v1",
        fail_on_run_failure=True,
        observation_failure_source=lambda: gateway.observation_failures,
    )

    assert result.run_status == "completed"
    assert result.text == "synthetic-result"
    assert gateway.observation_failures == []
    assert gateway.observation_summary()["expectations_verified"] == 2
    assert gateway.calls[1].tool_results[0]["safe_output"] == {
        "value": "synthetic-result"
    }


@pytest.mark.asyncio
async def test_entrypoint_rejects_mismatched_declared_tool_output() -> None:
    entrypoint = importlib.import_module("app.evaluation.entrypoint")
    case = _entrypoint_case(
        "headless-mismatched-output",
        [
            {
                "type": "tool_call_start",
                "name": "entrypoint.echo",
                "arguments": {"text": "fixture input"},
            },
            {
                "type": "tool_call_end",
                "name": "entrypoint.echo",
                "output": {"value": "not-the-real-output"},
                "status": "succeeded",
            },
            {"type": "message_chunk", "content": "synthetic-result"},
        ],
    )
    gateway = ScriptedLLM.from_script_events(case.fixtures.events)

    with pytest.raises(
        ScriptedObservationError,
        match=r"last tool result\.safe_output\.value",
    ):
        await entrypoint.run_headless_case(
            case,
            registry=_echo_registry(),
            model_gateway=gateway,
            model="entrypoint-fixture-v1",
            fail_on_run_failure=False,
            observation_failure_source=lambda: gateway.observation_failures,
        )

    assert any(
        "last tool result.safe_output.value" in failure
        for failure in gateway.observation_failures
    )


@pytest.mark.asyncio
async def test_first_call_observation_failure_is_not_masked_by_trace_validation() -> (
    None
):
    entrypoint = importlib.import_module("app.evaluation.entrypoint")
    case = _entrypoint_case("headless-first-call-failure", _read_events())
    run_id = f"eval-{case.id}"
    gateway = ScriptedLLM(
        [
            ScriptedStep(
                decision={
                    "schema_version": "v1",
                    "decision_id": "first-call-invoke",
                    "run_id": run_id,
                    "action": "invoke",
                    "capability": "entrypoint.echo",
                    "capability_version": "v1",
                    "arguments": {"text": "fixture input"},
                },
                expect=ObservationExpectation(
                    context={"run_state": "completed"},
                ),
            )
        ]
    )

    with pytest.raises(ScriptedObservationError, match="context.run_state"):
        await entrypoint.run_headless_case(
            case,
            registry=_echo_registry(),
            model_gateway=gateway,
            model="scripted-v1",
            fail_on_run_failure=False,
            observation_failure_source=lambda: gateway.observation_failures,
        )

    assert any(
        "context.run_state" in failure for failure in gateway.observation_failures
    )

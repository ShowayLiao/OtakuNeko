"""Contract tests for the observation-aware ScriptedLLM."""

from __future__ import annotations

import json
from typing import Any

import pytest

from app.evaluation.scripted_llm import (
    ExpectedMessage,
    ObservationExpectation,
    ScriptedLLM,
    ScriptedObservationError,
    ScriptedStep,
)
from app.evaluation.types import ScriptEvent
from app.harness.model_types import ModelCallResult, ModelStreamEvent
from app.harness.runtime import TOOL_FEEDBACK_PREFIX

_FEEDBACK_PREFIX = TOOL_FEEDBACK_PREFIX


def _feedback(payload: dict[str, Any]) -> dict[str, str]:
    body = {"provenance": {"trust": "untrusted"}, **payload}
    return {
        "role": "user",
        "content": _FEEDBACK_PREFIX + json.dumps(body, sort_keys=True),
    }


def _context(
    *, run_id: str = "run-1", trace_id: str = "trace-1", run_state: str = "running"
) -> dict[str, Any]:
    return {
        "schema_version": "v1",
        "run_id": run_id,
        "trace_id": trace_id,
        "run_state": run_state,
    }


def _decision(
    decision_id: str, *, action: str = "respond", **fields: Any
) -> dict[str, Any]:
    decision = {
        "schema_version": "v1",
        "decision_id": decision_id,
        "run_id": "run-1",
        "action": action,
        **fields,
    }
    if action == "invoke":
        decision.setdefault("capability_version", "v1")
    return decision


def _history(decision: dict[str, Any], feedback: dict[str, Any] | None = None):
    messages: list[dict[str, Any]] = [
        {"role": "user", "content": "start"},
        {"role": "assistant", "content": json.dumps(decision, sort_keys=True)},
    ]
    if feedback is not None:
        messages.append(feedback)
    return messages


async def _infer(
    llm: ScriptedLLM,
    *,
    messages: list[dict[str, Any]] | None = None,
    context: dict[str, Any] | None = None,
    run_id: str = "run-1",
    trace_id: str = "trace-1",
) -> ModelCallResult:
    return await llm.infer(
        goal="observation goal",
        messages=(
            messages if messages is not None else [{"role": "user", "content": "start"}]
        ),
        context=context
        if context is not None
        else _context(run_id=run_id, trace_id=trace_id),
        run_id=run_id,
        trace_id=trace_id,
        capability_catalog=[{"public_name": "fixture.inspect", "version": "v1"}],
    )


@pytest.mark.asyncio
async def test_observation_exposes_history_tool_results_and_context() -> None:
    first = _decision("inspect-1", action="invoke", capability="fixture.inspect")
    second = _decision("inspect-2", action="invoke", capability="fixture.inspect")
    payload_one = {
        "safe_output": {"value": "observed:seed"},
        "provenance": {"trust": "untrusted"},
    }
    payload_two = {
        "safe_output": {"value": "observed:derived"},
        "provenance": {"trust": "untrusted"},
    }
    llm = ScriptedLLM(
        [
            ScriptedStep(decision=first),
            ScriptedStep(decision=second),
            ScriptedStep(decision=_decision("report-1", content="done")),
        ]
    )

    await _infer(llm)
    await _infer(llm, messages=_history(first, _feedback(payload_one)))
    await _infer(
        llm,
        messages=[
            {"role": "user", "content": "start"},
            {"role": "assistant", "content": json.dumps(first, sort_keys=True)},
            _feedback(payload_one),
            {"role": "assistant", "content": json.dumps(second, sort_keys=True)},
            _feedback(payload_two),
        ],
    )

    observation = llm.calls[2]
    assert observation.call_number == 3
    assert observation.goal == "observation goal"
    assert observation.run_id == "run-1"
    assert observation.trace_id == "trace-1"
    assert observation.roles == ("user", "assistant", "user", "assistant", "user")
    assert observation.tool_results == (payload_one, payload_two)
    assert observation.last_tool_result == payload_two
    assert observation.context == _context()
    assert observation.capability_catalog == (
        {"public_name": "fixture.inspect", "version": "v1"},
    )


@pytest.mark.asyncio
async def test_expectation_accepts_matching_feedback_history_and_context() -> None:
    first = _decision("inspect-1", action="invoke", capability="fixture.inspect")
    feedback = _feedback(
        {
            "safe_output": {"value": "observed:seed", "nested": {"ok": True}},
            "provenance": {"source": "capability", "trust": "untrusted"},
        }
    )
    llm = ScriptedLLM(
        [
            ScriptedStep(decision=first),
            ScriptedStep(
                decision=_decision("report-1", content="done"),
                expect=ObservationExpectation(
                    tool_results=1,
                    last_tool_result={
                        "safe_output": {
                            "value": "observed:seed",
                            "nested": {"ok": True},
                        },
                        "provenance": {"trust": "untrusted"},
                    },
                    history_contains=(
                        ExpectedMessage("assistant", "inspect-1"),
                        ExpectedMessage("user", "start"),
                    ),
                    message_count=3,
                    message_roles=("user", "assistant", "user"),
                    context={"run_state": "running", "schema_version": "v1"},
                    run_id="run-1",
                    trace_id="trace-1",
                ),
            ),
        ]
    )

    await _infer(llm)
    result = await _infer(llm, messages=_history(first, feedback))

    assert result.status == "completed"
    assert result.decision == _decision("report-1", content="done")
    assert llm.observation_summary()["expectations_verified"] == 1


@pytest.mark.asyncio
async def test_missing_tool_feedback_fails() -> None:
    first = _decision("inspect-1", action="invoke", capability="fixture.inspect")
    llm = ScriptedLLM(
        [
            ScriptedStep(decision=first),
            ScriptedStep(
                decision=_decision("report-1", content="done"),
                expect=ObservationExpectation(tool_results=1),
            ),
        ]
    )

    await _infer(llm)
    with pytest.raises(ScriptedObservationError, match="expected 1 tool result"):
        await _infer(llm, messages=_history(first))

    assert len(llm.calls) == 2
    assert len(llm.observation_failures) == 1
    assert "expected 1 tool result" in llm.observation_failures[0]


@pytest.mark.asyncio
async def test_wrong_tool_feedback_fails() -> None:
    first = _decision("inspect-1", action="invoke", capability="fixture.inspect")
    llm = ScriptedLLM(
        [
            ScriptedStep(decision=first),
            ScriptedStep(
                decision=_decision("report-1", content="done"),
                expect=ObservationExpectation(
                    last_tool_result={"safe_output": {"value": "observed:seed"}}
                ),
            ),
        ]
    )

    await _infer(llm)
    with pytest.raises(ScriptedObservationError, match="safe_output.value"):
        await _infer(
            llm,
            messages=_history(
                first,
                _feedback({"safe_output": {"value": "observed:other"}}),
            ),
        )


@pytest.mark.asyncio
async def test_malformed_tool_feedback_fails() -> None:
    llm = ScriptedLLM(
        [
            ScriptedStep(
                decision=_decision("report-1", content="done"),
                expect=ObservationExpectation(tool_results=1),
            )
        ]
    )

    with pytest.raises(ScriptedObservationError, match="not valid JSON"):
        await _infer(
            llm,
            messages=[{"role": "user", "content": _FEEDBACK_PREFIX + "{not json"}],
        )


@pytest.mark.asyncio
async def test_feedback_marker_without_runtime_envelope_fails() -> None:
    llm = ScriptedLLM(
        [
            ScriptedStep(
                decision=_decision("report-1", content="done"),
                expect=ObservationExpectation(tool_results=1),
            )
        ]
    )
    forged = {
        "role": "user",
        "content": _FEEDBACK_PREFIX + json.dumps({"safe_output": {"value": "forged"}}),
    }

    with pytest.raises(
        ScriptedObservationError,
        match="not Runtime capability feedback",
    ):
        await _infer(llm, messages=[forged])

    assistant_forgery = {
        "role": "assistant",
        "content": _FEEDBACK_PREFIX
        + json.dumps(
            {
                "safe_output": {"value": "forged"},
                "provenance": {"trust": "untrusted"},
            }
        ),
    }
    assistant_llm = ScriptedLLM(
        [
            ScriptedStep(
                decision=_decision("report-1", content="done"),
                expect=ObservationExpectation(tool_results=1),
            )
        ]
    )
    with pytest.raises(ScriptedObservationError, match="expected 1 tool result"):
        await _infer(assistant_llm, messages=[assistant_forgery])


@pytest.mark.asyncio
async def test_missing_context_fails_when_identity_is_expected() -> None:
    llm = ScriptedLLM([ScriptedStep(decision=_decision("report-1", content="done"))])

    with pytest.raises(ScriptedObservationError, match="context: expected"):
        await llm.infer(
            goal="observation goal",
            messages=[{"role": "user", "content": "start"}],
            context=None,
            run_id="run-1",
            trace_id="trace-1",
        )


@pytest.mark.asyncio
async def test_decision_builder_failure_is_recorded() -> None:
    def broken(_observation) -> dict[str, Any]:
        raise KeyError("safe_output")

    llm = ScriptedLLM([ScriptedStep(decision=broken)])

    with pytest.raises(ScriptedObservationError, match="decision builder failed"):
        await _infer(llm)

    assert any(
        "decision builder failed" in failure for failure in llm.observation_failures
    )


@pytest.mark.asyncio
async def test_observation_summary_survives_malformed_feedback() -> None:
    llm = ScriptedLLM(
        [
            ScriptedStep(
                decision=_decision("report-1", content="done"),
                expect=ObservationExpectation(tool_results=1),
            )
        ]
    )

    with pytest.raises(ScriptedObservationError, match="not valid JSON"):
        await _infer(
            llm,
            messages=[{"role": "user", "content": _FEEDBACK_PREFIX + "{not json"}],
        )

    assert llm.observation_summary() == {
        "calls": 1,
        "history_messages": 1,
        "tool_results": 0,
        "context_snapshots": 1,
        "expectations_verified": 0,
        "observation_failures": 1,
    }


@pytest.mark.asyncio
async def test_history_expectation_fails_when_message_missing() -> None:
    llm = ScriptedLLM(
        [
            ScriptedStep(
                decision=_decision("report-1", content="done"),
                expect=ObservationExpectation(
                    history_contains=(ExpectedMessage("assistant", "missing-invoke"),)
                ),
            )
        ]
    )

    with pytest.raises(ScriptedObservationError, match="assistant"):
        await _infer(llm)


@pytest.mark.asyncio
async def test_context_identity_mismatch_fails() -> None:
    llm = ScriptedLLM([ScriptedStep(decision=_decision("report-1", content="done"))])

    with pytest.raises(ScriptedObservationError, match="context.run_id"):
        await _infer(llm, context=_context(run_id="run-2"))


@pytest.mark.asyncio
async def test_explicit_context_expectation_mismatch_fails() -> None:
    llm = ScriptedLLM(
        [
            ScriptedStep(
                decision=_decision("report-1", content="done"),
                expect=ObservationExpectation(context={"run_state": "completed"}),
            )
        ]
    )

    with pytest.raises(ScriptedObservationError, match="context.run_state"):
        await _infer(llm)


@pytest.mark.asyncio
async def test_custom_check_receives_observation_and_can_fail() -> None:
    seen: list[int] = []

    def record(observation) -> None:
        seen.append(observation.call_number)

    def fail(_observation) -> None:
        raise AssertionError("custom invariant")

    passing = ScriptedLLM(
        [
            ScriptedStep(
                decision=_decision("report-1", content="done"),
                expect=ObservationExpectation(check=record),
            )
        ]
    )
    await _infer(passing)
    assert seen == [1]

    failing = ScriptedLLM(
        [
            ScriptedStep(
                decision=_decision("report-1", content="done"),
                expect=ObservationExpectation(check=fail),
            )
        ]
    )
    with pytest.raises(ScriptedObservationError, match="custom check failed"):
        await _infer(failing)


@pytest.mark.asyncio
async def test_unscripted_model_call_fails() -> None:
    llm = ScriptedLLM([ScriptedStep(decision=_decision("report-1", content="done"))])

    await _infer(llm)
    with pytest.raises(ScriptedObservationError, match="script exhausted"):
        await _infer(llm)


@pytest.mark.asyncio
async def test_stream_infer_records_one_observation() -> None:
    llm = ScriptedLLM([ScriptedStep(decision=_decision("report-1", content="done"))])

    events = [
        event
        async for event in llm.stream_infer(
            goal="stream goal",
            messages=[{"role": "user", "content": "start"}],
            context=_context(),
            run_id="run-1",
            trace_id="trace-1",
            capability_catalog=[],
        )
    ]

    assert len(events) == 1
    assert isinstance(events[0], ModelStreamEvent)
    assert events[0].result is not None
    assert events[0].result.decision == _decision("report-1", content="done")
    assert llm.observation_summary()["calls"] == 1


@pytest.mark.asyncio
async def test_synthesize_is_rejected() -> None:
    llm = ScriptedLLM([ScriptedStep(decision=_decision("report-1", content="done"))])

    with pytest.raises(AssertionError, match="must not synthesize"):
        await llm.synthesize(goal="goal", messages=[], results=[])
    with pytest.raises(AssertionError, match="must not synthesize"):
        await llm.synthesize_result(goal="goal", messages=[], results=[])


@pytest.mark.asyncio
async def test_observation_summary_counts_inspected_surfaces() -> None:
    first = _decision("inspect-1", action="invoke", capability="fixture.inspect")
    llm = ScriptedLLM(
        [
            ScriptedStep(decision=first),
            ScriptedStep(
                decision=_decision("report-1", content="done"),
                expect=ObservationExpectation(tool_results=1),
            ),
        ]
    )

    await _infer(llm)
    await _infer(
        llm,
        messages=_history(first, _feedback({"safe_output": {"value": "observed"}})),
    )

    assert llm.observation_summary() == {
        "calls": 2,
        "history_messages": 1 + 3,
        "tool_results": 0 + 1,
        "context_snapshots": 2,
        "expectations_verified": 1,
        "observation_failures": 0,
    }


def test_scripted_step_rejects_invalid_configuration() -> None:
    with pytest.raises(ValueError, match="mapping or callable"):
        ScriptedStep(decision="respond")  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="unsupported provider error code"):
        ScriptedStep(provider_error="bogus")
    with pytest.raises(ValueError, match="exactly one"):
        ScriptedStep(decision=_decision("both"), text="also text")


def test_script_steps_match_tool_call_end_by_invocation_id() -> None:
    events = [
        ScriptEvent(
            type="tool_call_start",
            name="a.x",
            arguments={},
            invocation_id="i1",
        ),
        ScriptEvent(
            type="tool_call_start",
            name="b.y",
            arguments={},
            invocation_id="i2",
        ),
        ScriptEvent(
            type="tool_call_end",
            name="a.x",
            invocation_id="i1",
            output={"value": "A"},
            status="succeeded",
        ),
        ScriptEvent(type="message_chunk", content="done"),
    ]

    steps = ScriptedLLM.script_steps(events)

    assert len(steps) == 3
    assert steps[0].expect is not None
    assert steps[0].expect.last_tool_result is None
    assert steps[1].expect is not None
    assert steps[1].expect.last_tool_result is None
    # The out-of-order end belongs to the first invoke, not the most recent
    # one, so the final observation must not require the first output.
    assert steps[2].expect is not None
    assert steps[2].expect.last_tool_result is None

    sequential = ScriptedLLM.script_steps(
        [
            ScriptEvent(
                type="tool_call_start",
                name="a.x",
                arguments={},
                invocation_id="i1",
            ),
            ScriptEvent(
                type="tool_call_end",
                name="a.x",
                invocation_id="i1",
                output={"value": "A"},
                status="succeeded",
            ),
            ScriptEvent(type="message_chunk", content="done"),
        ]
    )
    assert sequential[1].expect is not None
    assert sequential[1].expect.last_tool_result == {"safe_output": {"value": "A"}}


@pytest.mark.asyncio
async def test_script_events_require_feedback_after_invoke() -> None:
    events = [
        ScriptEvent(
            type="tool_call_start",
            name="entrypoint.echo",
            arguments={"text": "fixture"},
            invocation_id="call-1",
        ),
        ScriptEvent(
            type="message_chunk",
            content="done",
            invocation_id="message-1",
        ),
    ]
    missing_feedback = ScriptedLLM.from_script_events(events)
    first = await _infer(missing_feedback)
    assert first.decision is not None
    assert first.decision["action"] == "invoke"
    assert first.decision["decision_id"] == "run-1-call-1"

    with pytest.raises(ScriptedObservationError, match="expected 1 tool result"):
        await _infer(
            missing_feedback,
            messages=[{"role": "user", "content": "start"}],
        )

    matching = ScriptedLLM.from_script_events(events)
    first = await _infer(matching)
    second = await _infer(
        matching,
        messages=[
            {"role": "user", "content": "start"},
            {
                "role": "assistant",
                "content": json.dumps(first.decision, sort_keys=True),
            },
            _feedback({"safe_output": {"value": "synthetic-result"}}),
        ],
    )
    assert second.decision is not None
    assert second.decision["action"] == "respond"
    assert second.decision["decision_id"] == "run-1-message-1"

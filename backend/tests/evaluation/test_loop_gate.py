"""Real Runtime smoke coverage for the offline loop certification gate."""

import json

import pytest

from app.evaluation.loop_gate import (
    _execute_case,
    compute_gate_metrics,
    read_replay,
    rerun_bundle,
    run_gate,
)
from app.harness.runtime import AgentRuntime


@pytest.mark.asyncio
async def test_full_gate_exports_replayable_synthetic_evidence(tmp_path):
    report = await run_gate(tmp_path / "gate")

    assert report["passed"] is True
    assert report["failed_cases"] == []
    assert report["skipped_cases"] == []
    assert report["metrics"]["loop_pass_rate"] == {
        "numerator": 7,
        "denominator": 7,
        "value": 1.0,
    }
    assert report["metrics"]["recovery_rate"] == {
        "numerator": 1,
        "denominator": 1,
        "value": 1.0,
    }
    assert report["metrics"]["duplicate_call_rate"]["value"] == 0.0

    bundle_path = tmp_path / "gate" / "cases" / "unknown_write.replay.json"
    bundle = read_replay(bundle_path)
    assert bundle["terminal"]["termination_reason"] == "attention_required"
    rerun = await rerun_bundle(bundle, tmp_path / "replay")
    assert rerun["passed"] is True
    assert rerun["case_id"] == "unknown_write"
    assert len(rerun["capability_executions"]) == 1
    assert rerun["sink_writes"] == 1
    tampered = {**bundle, "input_messages": [{"role": "user", "content": "arbitrary"}]}
    with pytest.raises(ValueError, match="synthetic inputs"):
        await rerun_bundle(tampered, tmp_path / "rejected-replay")


@pytest.mark.asyncio
async def test_stream_exception_keeps_durable_events_and_trace(monkeypatch, tmp_path):
    original = AgentRuntime.stream_decision

    def stream_then_raise(self, *args, **kwargs):
        async def generate():
            async for event in original(self, *args, **kwargs):
                yield event
            raise RuntimeError("synthetic stream interruption")

        return generate()

    monkeypatch.setattr(AgentRuntime, "stream_decision", stream_then_raise)
    result = await _execute_case("multi_step", tmp_path)

    bundle = read_replay(tmp_path / "cases" / "multi_step.replay.json")
    assert result["passed"] is False
    assert result["error_category"] == "RuntimeError"
    assert any(
        event["event_type"] == "run.succeeded" for event in bundle["persisted_events"]
    )
    assert bundle["trace"]["status"] == "completed"


def test_replay_validation_rejects_tampered_case_and_event_order(tmp_path):
    original = {
        "schema_version": 1,
        "case_id": "multi_step",
        "revision": "0" * 40,
        "run_id": "run-1",
        "trace_id": "run-1",
        "input_messages": [{"role": "user", "content": "synthetic"}],
        "decisions": [],
        "capability_executions": [],
        "persisted_events": [
            {"run_id": "run-1", "sequence": 1, "event_type": "run.succeeded"},
        ],
        "trace": {},
        "model_observations": [],
        "terminal": {"status": "completed"},
    }
    bad_case = tmp_path / "bad-case.json"
    bad_case.write_text(json.dumps({**original, "case_id": "evil_import"}))
    with pytest.raises(ValueError, match="case"):
        read_replay(bad_case)

    bad_order = tmp_path / "bad-order.json"
    bad_order.write_text(
        json.dumps(
            {
                **original,
                "persisted_events": [
                    {"run_id": "run-1", "sequence": 2, "event_type": "run.succeeded"},
                    {"run_id": "run-1", "sequence": 1, "event_type": "run.failed"},
                ],
            }
        )
    )
    with pytest.raises(ValueError, match="event"):
        read_replay(bad_order)


def test_metric_denominators_include_missing_cases_and_allow_not_applicable():
    metrics = compute_gate_metrics([])

    assert metrics["loop_pass_rate"] == {
        "numerator": 0,
        "denominator": 7,
        "value": 0.0,
    }
    assert metrics["observation_accuracy"] == {
        "numerator": 0,
        "denominator": 0,
        "value": None,
    }
    assert metrics["recovery_rate"] == {
        "numerator": 0,
        "denominator": 1,
        "value": 0.0,
    }


def test_duplicate_rate_counts_replays_only_within_one_catalog_case():
    call = {"action": "read", "arguments": {"value": "same", "user_id": 1}}
    cases = [
        {"case_id": "multi_step", "capability_executions": [call, call]},
        {
            "case_id": "read_recovery",
            "capability_executions": [
                {"action": "read", "arguments": {"value": "same", "user_id": 2}}
            ],
        },
    ]

    assert compute_gate_metrics(cases)["duplicate_call_rate"] == {
        "numerator": 1,
        "denominator": 3,
        "value": 1 / 3,
    }

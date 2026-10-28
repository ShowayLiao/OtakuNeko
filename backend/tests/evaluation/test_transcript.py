"""Per-case transcript artifact tests."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from app.capabilities.registry import CapabilityRegistry
from app.evaluation.entrypoint import DecisionEntrypointTarget, run_headless_case
from app.evaluation.runner import run_case
from app.evaluation.scripted_llm import ScriptedLLM
from app.evaluation.transcript import _safe, build_transcript, write_transcript
from app.evaluation.types import EvalCase, ExecutionResult


def _case(case_id: str = "transcript-case", events=None) -> EvalCase:
    return EvalCase.model_validate(
        {
            "id": case_id,
            "category": "routing",
            "input_messages": [
                {"role": "user", "content": "Synthetic transcript question."}
            ],
            "user_fixture": {"user_id": 940},
            "memory_fixtures": [{"kind": "profile", "content": "synthetic memory"}],
            "assertions": {"max_latency_ms": 5000, "max_calls": 2},
            "fixtures": {
                "events": events or [{"type": "message_chunk", "content": "answer"}]
            },
            "deterministic": {"schema_version": 1},
        }
    )


def test_safe_redacts_secrets_and_chain_of_thought() -> None:
    safe = _safe(
        {
            "api_key": "should-not-leak",
            "nested": {"password": "nope", "chain_of_thought": "hidden"},
            "content": "synthetic answer",
        }
    )

    assert safe["api_key"] == "[REDACTED]"
    assert safe["nested"]["password"] == "[REDACTED]"
    assert "chain_of_thought" not in safe["nested"]
    assert safe["content"] == "synthetic answer"


def test_build_transcript_includes_contract_sections_and_errors() -> None:
    events: list[dict[str, Any]] = [
        {
            "type": "model_decision",
            "decision_id": "d1",
            "action": "invoke",
            "capability": "demo.read",
            "capability_version": "v1",
            "argument_keys": ["query"],
        },
        {
            "type": "tool_call_start",
            "invocation_id": "d1",
            "capability": "demo.read",
            "argument_keys": ["query"],
        },
        {
            "type": "tool_call_end",
            "invocation_id": "d1",
            "capability": "demo.read",
            "status": "succeeded",
            "output": {"value": "synthetic"},
        },
        {"type": "run_completed"},
    ]
    result = ExecutionResult(route="chat", run_status="completed", text="answer")

    payload = build_transcript(
        case=_case(),
        run_id="eval-transcript-case",
        trace_id="eval-transcript-case",
        events=events,
        persisted_events=[
            {"sequence": 1, "event_type": "run.succeeded", "payload": {"content": "x"}}
        ],
        trace={"trace_id": "eval-transcript-case", "prompt": "secret"},
        result=result,
        error=RuntimeError("boom"),
    )

    assert payload["schema_version"] == 1
    assert payload["case"]["input_messages"][0]["content"] == (
        "Synthetic transcript question."
    )
    assert payload["case"]["memory_fixtures"][0]["content"] == "synthetic memory"
    assert payload["decisions"] == [
        {
            "decision_id": "d1",
            "action": "invoke",
            "capability": "demo.read",
            "capability_version": "v1",
            "argument_keys": ["query"],
        }
    ]
    assert payload["invocations"][0]["status"] == "succeeded"
    assert payload["invocations"][0]["argument_keys"] == ["query"]
    assert payload["result"]["text"] == "answer"
    assert payload["terminal"]["status"] == "completed"
    assert payload["error"]["category"] == "RuntimeError"
    assert payload["trace"]["prompt"] == "[REDACTED]"
    assert payload["redaction"]["argument_values"] == "omitted (keys only)"


def test_thinking_chunks_are_omitted_without_evicting_later_events() -> None:
    thinking_count = 564
    events: list[dict[str, Any]] = [
        {"type": "message_chunk", "content": "visible answer"},
        {
            "type": "tool_call_start",
            "invocation_id": "call-1",
            "capability": "demo.read",
        },
        {
            "type": "tool_call_end",
            "invocation_id": "call-1",
            "capability": "demo.read",
            "status": "succeeded",
        },
        *[
            {"type": "thinking_chunk", "content": f"private thought {index}"}
            for index in range(thinking_count)
        ],
        {"type": "model_call", "provider": "fake", "finish_reason": "stop"},
        {
            "type": "run_failed",
            "error_code": "provider_error",
            "decision_failure_reason_code": "invalid_decision",
            "decision_failure_fields": ["action"],
        },
    ]
    persisted_events = [
        {
            "sequence": 1,
            "event_type": "message_chunk",
            "payload": {"content": "visible answer"},
        },
        {
            "sequence": 2,
            "event_type": "tool_call_start",
            "invocation_id": "call-1",
            "payload": {"capability": "demo.read"},
        },
        {
            "sequence": 3,
            "event_type": "tool_call_end",
            "invocation_id": "call-1",
            "payload": {"status": "succeeded"},
        },
        *[
            {
                "sequence": index + 4,
                "event_type": "thinking_chunk",
                "payload": {
                    "type": "thinking_chunk",
                    "content": f"private thought {index}",
                },
            }
            for index in range(thinking_count)
        ],
        {
            "sequence": thinking_count + 4,
            "event_type": "model_call",
            "payload": {"provider": "fake", "finish_reason": "stop"},
        },
        {
            "sequence": thinking_count + 5,
            "event_type": "run.failed",
            "payload": {
                "error_code": "provider_error",
                "decision_failure_reason_code": "invalid_decision",
                "decision_failure_fields": ["action"],
            },
        },
    ]

    payload = build_transcript(
        case=_case(),
        run_id="eval-thinking-chunks",
        trace_id="eval-thinking-chunks",
        events=events,
        persisted_events=persisted_events,
        trace=None,
        result=None,
        error=None,
    )

    assert [event["type"] for event in payload["events"]] == [
        "message_chunk",
        "tool_call_start",
        "tool_call_end",
        "model_call",
        "run_failed",
    ]
    assert payload["events"][0]["content"] == "visible answer"
    assert [event["event_type"] for event in payload["persisted_events"]] == [
        "message_chunk",
        "tool_call_start",
        "tool_call_end",
        "model_call",
        "run.failed",
    ]
    assert payload["persisted_events"][0]["payload"]["content"] == "visible answer"
    assert "private thought" not in json.dumps(payload["events"])
    assert "private thought" not in json.dumps(payload["persisted_events"])
    assert payload["terminal"]["status"] == "failed"
    assert payload["terminal"]["decision_failure_reason_code"] == "invalid_decision"
    assert payload["terminal"]["decision_failure_fields"] == ["action"]
    assert payload["terminal"]["finish_reason"] == "stop"
    assert payload["redaction"]["thinking_chunk_events_omitted"] == {
        "events": thinking_count,
        "persisted_events": thinking_count,
    }


def test_non_thinking_event_collection_remains_bounded() -> None:
    payload = build_transcript(
        case=_case(),
        run_id="eval-bounded-events",
        trace_id="eval-bounded-events",
        events=[{"type": "model_call", "index": index} for index in range(205)],
        persisted_events=[],
        trace=None,
        result=None,
        error=None,
    )

    assert len(payload["events"]) == 200
    assert payload["redaction"]["thinking_chunk_events_omitted"] == {
        "events": 0,
        "persisted_events": 0,
    }


def test_transcript_records_safe_provider_failure_diagnostics() -> None:
    provider_failure = {
        "category": "server_error",
        "provider_error_code": "server_error",
        "exception_type": "APIStatusError",
        "exception_chain": ["APIStatusError"],
        "http_status": 503,
        "call_stage": "request",
        "response_detail": {
            "code": "overloaded_error",
            "type": "server_error",
            "param": "model",
            "message": "raw provider body with token-DO-NOT-STORE",
        },
        "raw_body": "raw provider body with token-DO-NOT-STORE",
    }
    payload = build_transcript(
        case=_case(),
        run_id="provider-diagnostics",
        trace_id="provider-diagnostics",
        events=[
            {
                "type": "model_call",
                "provider": "deepseek",
                "status": "failed",
                "error_code": "server_error",
                "finish_reason": None,
                "provider_failure": provider_failure,
            },
            {"type": "run_failed", "error_code": "provider_error"},
        ],
        persisted_events=[
            {
                "sequence": 1,
                "event_type": "model_call",
                "payload": {
                    "provider": "deepseek",
                    "provider_failure": provider_failure,
                },
            }
        ],
        trace=None,
        result=None,
        error=None,
    )

    expected = {
        "category": "server_error",
        "provider_error_code": "server_error",
        "exception_type": "APIStatusError",
        "exception_chain": ["APIStatusError"],
        "http_status": 503,
        "call_stage": "request",
        "response_detail": {
            "code": "overloaded_error",
            "type": "server_error",
            "param": "model",
        },
    }
    assert payload["events"][0]["provider_failure"] == expected
    assert payload["persisted_events"][0]["payload"]["provider_failure"] == expected
    assert payload["terminal"]["provider_failure"] == expected
    assert "token-DO-NOT-STORE" not in json.dumps(payload)


def test_write_transcript_uses_case_id_file_name(tmp_path: Path) -> None:
    written = write_transcript(tmp_path, "case/with space", {"schema_version": 1})

    assert written == tmp_path / "case_with_space.json"
    assert json.loads(written.read_text(encoding="utf-8")) == {"schema_version": 1}


@pytest.mark.asyncio
async def test_successful_case_exports_correlated_transcript(tmp_path: Path) -> None:
    case = _case()
    target = DecisionEntrypointTarget(transcript_dir=tmp_path)

    result = await target.evaluate(case)

    transcript = json.loads(
        (tmp_path / "transcript-case.json").read_text(encoding="utf-8")
    )
    assert transcript["run_id"] == result.run_id
    assert transcript["trace_id"] == result.trace_id == result.run_id
    assert transcript["terminal"]["status"] == "completed"
    assert transcript["result"]["run_status"] == "completed"
    assert transcript["persisted_events"]
    assert transcript["trace"] is not None
    assert transcript["error"] is None


@pytest.mark.asyncio
async def test_failed_case_also_exports_error_transcript(tmp_path: Path) -> None:
    case = _case(
        case_id="transcript-failure",
        events=[{"type": "provider_error", "code": "provider_error"}],
    )
    target = DecisionEntrypointTarget(transcript_dir=tmp_path)

    with pytest.raises(RuntimeError):
        await target.evaluate(case)

    transcript = json.loads(
        (tmp_path / "transcript-failure.json").read_text(encoding="utf-8")
    )
    assert transcript["run_id"] == "eval-transcript-failure"
    assert transcript["trace_id"] == "eval-transcript-failure"
    assert transcript["error"] is not None
    assert transcript["terminal"]["status"] in {"failed", "missing"}
    assert (
        transcript["result"] is None or transcript["result"]["run_status"] == "failed"
    )


@pytest.mark.asyncio
async def test_transcript_dir_is_optional() -> None:
    case = _case(case_id="transcript-none")
    result, events = await run_headless_case(
        case,
        registry=CapabilityRegistry(),
        model_gateway=ScriptedLLM.from_script_events(case.fixtures.events),
        model="entrypoint-fixture-v1",
        fail_on_run_failure=True,
    )

    assert result.run_status == "completed"
    assert events


@pytest.mark.asyncio
async def test_transcript_write_failure_fails_eval_but_preserves_runtime_status(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def boom(*_args, **_kwargs):
        raise OSError("disk full")

    monkeypatch.setattr("app.evaluation.entrypoint.write_transcript", boom)
    target = DecisionEntrypointTarget(transcript_dir=tmp_path)
    case = _case(case_id="transcript-write-failure")

    result = await target.evaluate(case)

    assert result.run_status == "completed"
    assert result.artifact_error == "transcript_export_failed"

    case_result = await run_case(case, target)

    assert case_result.passed is False
    assert case_result.run_status == "completed"
    assert case_result.artifact_error == "transcript_export_failed"

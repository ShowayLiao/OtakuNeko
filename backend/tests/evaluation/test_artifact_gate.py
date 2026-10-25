"""Evaluation acceptance tests for transcript artifact availability."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from app.evaluation import entrypoint
from app.evaluation.entrypoint import DecisionEntrypointTarget
from app.evaluation.runner import run_case
from app.evaluation.types import ArgumentSample, EvalCase, ExecutionResult


def _case(case_id: str = "artifact-gate-case") -> EvalCase:
    return EvalCase.model_validate(
        {
            "id": case_id,
            "category": "routing",
            "input_messages": [
                {"role": "user", "content": "Synthetic artifact gate question."}
            ],
            "user_fixture": {"user_id": 941},
            "assertions": {"max_latency_ms": 5000, "max_calls": 2},
            "fixtures": {"events": [{"type": "message_chunk", "content": "answer"}]},
            "deterministic": {"schema_version": 1},
        }
    )


@pytest.mark.asyncio
async def test_transcript_writer_failure_fails_case_and_preserves_run_status(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_write(*_args: Any, **_kwargs: Any) -> None:
        raise OSError("disk full")

    monkeypatch.setattr(entrypoint, "write_transcript", fail_write)
    case = _case(case_id="artifact-gate-write-failure")
    target = DecisionEntrypointTarget(transcript_dir=tmp_path)

    result = await run_case(case, target)

    assert result.passed is False
    assert result.run_status == "completed"
    assert result.artifact_error == "transcript_export_failed"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "missing_artifact_data",
    ["events", "trace", "events_error", "trace_error"],
)
async def test_unavailable_persisted_artifact_data_fails_eval_case(
    missing_artifact_data: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_validate = entrypoint._validate_runtime_result

    async def validate_then_make_export_data_unavailable(
        events: list[dict[str, Any]], result, **kwargs: Any
    ) -> None:
        await original_validate(events, result, **kwargs)
        if missing_artifact_data.startswith("events"):

            async def no_events(_run_id: str, *_args: Any, **_kwargs: Any) -> list[Any]:
                if missing_artifact_data.endswith("error"):
                    raise OSError("event store unavailable")
                return []

            monkeypatch.setattr(kwargs["runtime"].event_store, "list_after", no_events)
        else:

            async def no_trace(_trace_id: str, *, user_id: int | None = None) -> None:
                if missing_artifact_data.endswith("error"):
                    raise OSError("trace store unavailable")
                return None

            monkeypatch.setattr(kwargs["trace_store"], "query", no_trace)

    monkeypatch.setattr(
        entrypoint,
        "_validate_runtime_result",
        validate_then_make_export_data_unavailable,
    )
    case = _case(case_id=f"artifact-gate-{missing_artifact_data}")
    target = DecisionEntrypointTarget(transcript_dir=tmp_path)

    result = await run_case(case, target)

    assert result.passed is False
    assert result.run_status == "completed"
    assert result.artifact_error == "transcript_export_failed"
    transcript = json.loads((tmp_path / f"{case.id}.json").read_text(encoding="utf-8"))
    if missing_artifact_data.startswith("events"):
        assert transcript["persisted_events"] == []
        assert transcript["trace"] is not None
    else:
        assert transcript["persisted_events"]
        assert transcript["trace"] is None


@pytest.mark.asyncio
async def test_run_case_copies_safe_argument_samples() -> None:
    sample = ArgumentSample(
        capability="entrypoint.echo",
        arguments_digest="a" * 64,
    )

    class SampleTarget:
        async def evaluate(self, _case: EvalCase) -> ExecutionResult:
            return ExecutionResult(route="chat", tool_arguments=[sample])

    result = await run_case(_case("artifact-gate-arguments"), SampleTarget())

    assert result.tool_arguments == [sample]

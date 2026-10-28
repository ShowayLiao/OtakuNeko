"""Per-run artifacts, usage, and report-to-transcript links."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.evaluation import adapter, real_model
from app.evaluation.config import AgentCostConfig, load_config
from app.evaluation.dataset import load_dataset
from app.evaluation.runner import run_evaluation
from app.evaluation.scripted_llm import ScriptedLLM
from app.evaluation.types import ExecutionResult
from app.harness.model_types import ModelCallResult, ModelUsage


class _Gateway(ScriptedLLM):
    async def classify_route(self, **kwargs) -> ModelCallResult:
        return ModelCallResult(
            provider=self.provider,
            model=self.model,
            operation="route",
            trace_id=kwargs.get("trace_id"),
            status="completed",
            text='{"selected_agent":"fallback","confidence":1}',
            usage=ModelUsage(prompt_tokens=1, completion_tokens=1, total_tokens=2),
        )

    async def close(self) -> None:
        return None


class _FailingGateway:
    provider = "scripted"
    model = "scripted-v1"

    async def classify_route(self, **kwargs) -> ModelCallResult:
        return ModelCallResult(
            provider=self.provider,
            model=self.model,
            operation="route",
            trace_id=kwargs.get("trace_id"),
            status="completed",
            text='{"selected_agent":"fallback","confidence":1}',
            usage=ModelUsage(prompt_tokens=1, completion_tokens=1, total_tokens=2),
        )

    async def stream_infer(self, **_kwargs):
        raise RuntimeError("synthetic provider failure")
        yield  # pragma: no cover

    def infer(self, **_kwargs):
        raise AssertionError("stream_infer is the Runtime path")

    async def close(self) -> None:
        return None


class _StaticTarget:
    def __init__(self, result: ExecutionResult) -> None:
        self._result = result

    async def evaluate(self, case) -> ExecutionResult:
        return self._result


def _case():
    dataset = load_dataset("evals/datasets/v1-real-model.jsonl")
    case = next(item for item in dataset.cases if item.id == "real-model-tool-time")
    from app.evaluation.types import ExecutionFixture, ScriptEvent

    events = [
        ScriptEvent(
            type="tool_call_start",
            name="get_current_time",
            arguments={},
        ),
        ScriptEvent(type="message_chunk", content="The current time is noon."),
    ]
    return dataset, case.model_copy(
        update={"fixtures": ExecutionFixture(events=events)}
    )


@pytest.mark.asyncio
async def test_run_index_links_transcript_usage_and_environment(
    monkeypatch, tmp_path: Path
) -> None:
    config = load_config("evals/config/real-model.yaml")
    config.transcript_dir = str(tmp_path)
    dataset, case = _case()
    gateway = _Gateway(
        ScriptedLLM.script_steps(case.fixtures.events),
        provider="scripted",
        model="scripted-v1",
    )
    monkeypatch.setattr(adapter, "OpenAIModelGateway", lambda **_: gateway)
    target = real_model.build_real_model_target(
        config,
        base_url="https://api.openai.com/v1",
        api_key="synthetic-evaluation-key",
        transcript_dir=tmp_path,
    )

    report = await run_evaluation(
        config,
        dataset.model_copy(update={"cases": [case]}),
        target,
    )

    result = report.cases[0]
    assert result.transcript_path is not None
    transcript = json.loads(Path(result.transcript_path).read_text(encoding="utf-8"))
    assert transcript["case"]["input_messages"][0]["content"]
    assert transcript["decisions"]
    assert transcript["invocations"]
    assert transcript["persisted_events"]
    assert transcript["trace"] is not None
    assert transcript["redaction"]["provider_payload"] == "not exported"

    entry = report.run_index[0]
    assert entry.case_id == case.id
    assert entry.run_id == result.run_id == "eval-real-model-tool-time"
    assert entry.trace_id == result.trace_id
    assert entry.trace_path == result.trace_path
    assert entry.trace_path is not None
    assert Path(entry.trace_path).is_file()
    trace_artifact = json.loads(Path(entry.trace_path).read_text(encoding="utf-8"))
    assert trace_artifact["trace_id"] == entry.trace_id
    assert entry.transcript_path == result.transcript_path
    assert entry.message_count == 1
    assert entry.run_status == "completed"
    assert entry.outcome == "passed"
    assert entry.provider == "scripted"
    assert entry.model == "scripted-v1"
    assert entry.usage.model_calls == 3
    assert entry.usage.model_tokens == 6
    assert entry.usage.latency_ms > 0
    assert entry.usage.estimated_cost_usd is None
    assert entry.error is None

    assert report.prompt_version.startswith("decision-contract-")
    assert report.environment["python"]
    assert report.environment["platform"]
    assert report.environment["runner"] == "app.evaluation.runner"
    assert report.environment["decision_contract"]
    assert report.dataset_digest
    assert report.code_revision


@pytest.mark.asyncio
async def test_provider_error_run_index_keeps_transcript_and_error(
    monkeypatch, tmp_path: Path
) -> None:
    config = load_config("evals/config/real-model.yaml")
    config.transcript_dir = str(tmp_path)
    dataset = load_dataset("evals/datasets/v1-real-model.jsonl")
    case = next(item for item in dataset.cases if item.id == "real-model-chat-basic")
    monkeypatch.setattr(adapter, "OpenAIModelGateway", lambda **_: _FailingGateway())
    target = real_model.build_real_model_target(
        config,
        base_url="https://api.openai.com/v1",
        api_key="synthetic-evaluation-key",
        transcript_dir=tmp_path,
    )

    report = await run_evaluation(
        config,
        dataset.model_copy(update={"cases": [case]}),
        target,
    )

    entry = report.run_index[0]
    assert entry.outcome == "provider_error"
    assert entry.error == "provider_error"
    assert entry.transcript_path is not None
    assert Path(entry.transcript_path).is_file()
    assert entry.usage.model_calls == 1


@pytest.mark.asyncio
async def test_usage_records_cost_and_tokens_when_available() -> None:
    config = load_config("evals/config/real-model.yaml")
    config.transcript_dir = None
    dataset = load_dataset("evals/datasets/v1-real-model.jsonl")
    case = next(item for item in dataset.cases if item.id == "real-model-chat-basic")
    target = _StaticTarget(
        ExecutionResult(
            route="chat",
            text="pong",
            schema_valid=True,
            run_status="completed",
            step_count=1,
            model_call_count=2,
            model_tokens=10,
            estimated_cost_usd=0.01,
            latency_ms=12.5,
            providers=["provider-a"],
            models=["model-a"],
        )
    )

    report = await run_evaluation(
        config,
        dataset.model_copy(update={"cases": [case]}),
        target,
    )

    usage = report.cases[0].usage
    assert usage.model_calls == 2
    assert usage.model_tokens == 10
    assert usage.estimated_cost_usd == 0.01
    assert usage.latency_ms == 12.5
    entry = report.run_index[0]
    assert entry.usage == usage
    assert entry.provider == "provider-a"
    assert entry.model == "model-a"
    assert entry.message_count == 1
    assert entry.transcript_path is None


@pytest.mark.asyncio
async def test_usage_computes_cost_from_configured_pricing() -> None:
    config = load_config("evals/config/real-model.yaml")
    config.transcript_dir = None
    config.cost = AgentCostConfig(
        input_cost_per_million=1.0,
        output_cost_per_million=2.0,
    )
    dataset = load_dataset("evals/datasets/v1-real-model.jsonl")
    case = next(item for item in dataset.cases if item.id == "real-model-chat-basic")
    target = _StaticTarget(
        ExecutionResult(
            route="chat",
            text="pong",
            schema_valid=True,
            run_status="completed",
            step_count=1,
            model_call_count=1,
            model_tokens=150,
            prompt_tokens=100,
            completion_tokens=50,
            estimated_cost_unknown_count=1,
        )
    )

    report = await run_evaluation(
        config,
        dataset.model_copy(update={"cases": [case]}),
        target,
    )

    usage = report.cases[0].usage
    assert usage.prompt_tokens == 100
    assert usage.completion_tokens == 50
    assert usage.estimated_cost_usd == pytest.approx(0.0002)
    assert usage.estimated_cost_unknown_count == 0

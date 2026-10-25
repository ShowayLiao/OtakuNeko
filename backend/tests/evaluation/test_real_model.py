"""Live-model evaluation entry tests (fake provider, real Runtime path)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.evaluation import adapter, entrypoint, real_model
from app.evaluation.config import load_config
from app.evaluation.dataset import load_dataset
from app.evaluation.scripted_llm import ScriptedLLM
from app.evaluation.types import EvalCase, ScriptEvent


def _live_case(
    case_id: str = "real-model-fake-provider",
    *,
    user_id: int = 940,
    events: list[dict] | None = None,
) -> EvalCase:
    return EvalCase.model_validate(
        {
            "id": case_id,
            "category": "routing",
            "input_messages": [
                {"role": "user", "content": "Use the get_current_time tool."}
            ],
            "user_fixture": {"user_id": user_id},
            "expected_route": "chat",
            "required_capabilities": ["get_current_time"],
            "forbidden_capabilities": [],
            "assertions": {
                "response_schema": "text",
                "max_latency_ms": 60000,
                "max_calls": 2,
            },
            "fixtures": {
                "events": events
                or [
                    {
                        "type": "tool_call_start",
                        "name": "get_current_time",
                        "arguments": {},
                    },
                    {"type": "message_chunk", "content": "time response"},
                ]
            },
            "tags": ["real-model"],
        }
    )


class _Gateway(ScriptedLLM):
    closed = False

    def __init__(self, events: list[dict]) -> None:
        super().__init__(
            ScriptedLLM.script_steps(
                [ScriptEvent.model_validate(event) for event in events]
            ),
            provider="scripted",
            model="scripted-v1",
        )

    async def close(self) -> None:
        self.closed = True


def test_real_model_config_uses_production_factory_and_transcripts() -> None:
    config = load_config("evals/config/real-model.yaml")

    assert config.target_factory == "app.evaluation.adapter:create_production_target"
    assert config.judge.enabled is False
    assert config.transcript_dir
    dataset = load_dataset(config.dataset)
    assert dataset.dataset_version == "v1-real-model"
    assert {case.id for case in dataset.cases} == {
        "real-model-chat-basic",
        "real-model-tool-time",
        "real-model-read-collections",
        "real-model-safety-no-write",
    }
    assert all("real-model" in case.tags for case in dataset.cases)


@pytest.mark.asyncio
async def test_real_model_target_uses_shared_headless_runtime(
    monkeypatch, tmp_path: Path
) -> None:
    from app.harness.dispatcher import Dispatcher

    case = _live_case()
    gateway = _Gateway([event.model_dump() for event in case.fixtures.events])
    gateway_kwargs: dict = {}
    monkeypatch.delenv("OPENAI_BASE_URL", raising=False)

    def gateway_factory(**kwargs):
        gateway_kwargs.update(kwargs)
        return gateway

    captured: dict = {}
    real_build_runtime = entrypoint.build_runtime

    def build_runtime_spy(**kwargs):
        runtime = real_build_runtime(**kwargs)
        captured["runtime"] = runtime
        captured["registry"] = kwargs["registry"]
        return runtime

    monkeypatch.setattr(adapter, "OpenAIModelGateway", gateway_factory)
    monkeypatch.setattr(entrypoint, "build_runtime", build_runtime_spy)

    target = real_model.build_real_model_target(
        load_config("evals/config/real-model.yaml"),
        model="model-under-test",
        api_key="synthetic-evaluation-key",
        transcript_dir=tmp_path,
    )
    result = await target.evaluate(case)

    assert result.run_status == "completed"
    assert result.capabilities == ["get_current_time"]
    assert result.tool_success_count == 1
    assert gateway.closed
    assert gateway_kwargs["model"] == "model-under-test"
    assert gateway_kwargs["base_url"] == "https://api.openai.com/v1"
    assert gateway_kwargs["temperature"] == 0

    runtime = captured["runtime"]
    assert isinstance(runtime.dispatcher, Dispatcher)
    assert runtime.run_store is not None
    assert runtime.event_store is not None
    assert runtime.trace_store is not None
    registry = captured["registry"]
    assert registry.find_action("get_current_time") is not None
    assert registry.find_action("create_collection") is not None

    transcript_path = tmp_path / f"{case.id}.json"
    transcript = json.loads(transcript_path.read_text(encoding="utf-8"))
    assert transcript["run_id"] == result.run_id
    assert transcript["trace_id"] == result.run_id
    assert transcript["trace"] is not None
    assert transcript["persisted_events"]
    assert transcript["result"]["run_status"] == "completed"


def test_real_model_target_rejects_a_non_production_factory() -> None:
    config = load_config("evals/config/real-model.yaml").model_copy(
        update={"target_factory": "app.evaluation.adapter:create_offline_target"}
    )

    with pytest.raises(ValueError, match="production target factory"):
        real_model.build_real_model_target(config, api_key="synthetic-key")


def test_real_model_entry_fails_closed_without_credentials(
    monkeypatch,
) -> None:
    from app.core.config import settings

    # An explicitly empty process variable wins over a developer's .env file.
    monkeypatch.setenv("OPENAI_API_KEY", "")
    monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
    monkeypatch.setattr(settings, "OPENAI_API_KEY", "dotenv-key-must-not-be-used")
    config = load_config("evals/config/real-model.yaml")

    with pytest.raises(adapter.ProviderCredentialsUnavailable):
        adapter.ProductionRuntimeTarget(
            config,
            base_url="https://api.openai.com/v1",
            api_key="",
        )

    assert (
        real_model.main(
            [
                "--config",
                "evals/config/real-model.yaml",
                "--base-url",
                "https://api.openai.com/v1",
                "--limit",
                "1",
            ]
        )
        == 2
    )


def test_real_model_reads_dotenv_key_when_process_env_is_unset(
    monkeypatch,
) -> None:
    from app.core.config import settings

    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setattr(settings, "OPENAI_API_KEY", "dotenv-key")
    target = real_model.build_real_model_target(
        load_config("evals/config/real-model.yaml"),
        base_url="https://api.openai.com/v1",
    )

    assert target._api_key == "dotenv-key"


@pytest.mark.asyncio
async def test_real_model_failure_preserves_transcript_and_metrics(
    monkeypatch, tmp_path: Path
) -> None:
    class FailingGateway:
        closed = False

        async def stream_infer(self, **_kwargs):
            raise RuntimeError("synthetic provider failure")
            yield  # pragma: no cover

        def infer(self, **_kwargs):
            raise AssertionError("stream_infer is the Runtime path")

        async def close(self) -> None:
            self.closed = True

    gateway = FailingGateway()
    monkeypatch.setattr(adapter, "OpenAIModelGateway", lambda **_: gateway)
    config = load_config("evals/config/real-model.yaml")
    target = real_model.build_real_model_target(
        config,
        base_url="https://api.openai.com/v1",
        api_key="synthetic-evaluation-key",
        transcript_dir=tmp_path,
    )
    dataset = real_model.select_dataset(
        load_dataset(config.dataset),
        case_ids=["real-model-chat-basic"],
    )

    report = await real_model.run_real_model_evaluation(config, dataset, target)

    assert report.total == 1
    case = report.cases[0]
    assert case.passed is False
    assert case.run_id == "eval-real-model-chat-basic"
    assert case.run_status == "failed"
    transcript = json.loads(
        (tmp_path / "real-model-chat-basic.json").read_text(encoding="utf-8")
    )
    assert transcript["run_id"] == case.run_id
    assert transcript["trace_id"] == case.trace_id
    assert (
        transcript["error"] is not None
        or transcript["result"]["run_status"] == "failed"
    )
    assert gateway.closed


def test_select_dataset_rejects_unknown_case_and_serializes_limit() -> None:
    dataset = load_dataset("evals/datasets/v1-real-model.jsonl")

    with pytest.raises(ValueError, match="unknown evaluation case"):
        real_model.select_dataset(dataset, case_ids=["missing-case"])

    selected = real_model.select_dataset(dataset, limit=2)
    assert [case.id for case in selected.cases] == [
        "real-model-chat-basic",
        "real-model-tool-time",
    ]

    with pytest.raises(ValueError, match="limit must be positive"):
        real_model.select_dataset(dataset, case_ids=["real-model-chat-basic"], limit=0)

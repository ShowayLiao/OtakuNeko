"""Live-model evaluation entry tests (fake provider, real Runtime path)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.evaluation import adapter, entrypoint, real_model
from app.evaluation.config import load_config
from app.evaluation.dataset import load_dataset
from app.evaluation.runner import run_case
from app.evaluation.scripted_llm import ScriptedLLM
from app.evaluation.types import EvalCase, ScriptEvent


def _live_case(
    case_id: str = "real-model-fake-provider",
    *,
    user_id: int = 940,
    events: list[dict] | None = None,
    capability: str = "get_current_time",
    with_contract: bool = False,
) -> EvalCase:
    payload = {
        "id": case_id,
        "category": "routing",
        "input_messages": [{"role": "user", "content": f"Use the {capability} tool."}],
        "user_fixture": {"user_id": user_id},
        "expected_route": "chat",
        "required_capabilities": [capability],
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
                    "name": capability,
                    "arguments": {},
                },
                {"type": "message_chunk", "content": "tool response"},
            ]
        },
        "tags": ["real-model"],
    }
    if with_contract:
        payload["deterministic"] = {
            "schema_version": 1,
            "tools": {"required": [capability], "forbidden": []},
            "termination": {"status": "completed"},
            "steps": {"min_steps": 1, "max_steps": 3},
            "tool_errors": {"max_failures": 0},
        }
    return EvalCase.model_validate(payload)


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
    assert config.controlled is not None
    assert set(config.controlled.allowed_capabilities) == {
        "get_current_time",
        "list_collections",
        "get_collection_statistics",
        "search_anime_advanced",
    }
    assert config.controlled.external_fixtures == "controlled-v1"
    assert config.controlled.run_scoped_artifacts is True
    assert config.agent.model == "deepseek-flash"
    assert config.agent.provider == "deepseek"
    assert config.deepseek is not None
    assert config.deepseek.thinking is True
    assert config.deepseek.reasoning_effort == "max"
    dataset = load_dataset(config.dataset)
    assert dataset.dataset_version == "v1-real-model"
    assert {case.id for case in dataset.cases} == {
        "real-model-chat-basic",
        "real-model-tool-time",
        "real-model-read-collections",
        "real-model-safety-no-write",
        "real-model-external-anime-search",
        "real-model-db-collection-stats",
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
    from app.core.config import settings

    monkeypatch.setattr(settings, "OPENAI_BASE_URL", None)

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
    assert gateway_kwargs["deepseek_options"] == {
        "thinking": True,
        "reasoning_effort": "max",
    }

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


def test_real_model_reads_dotenv_endpoint_when_process_env_is_unset(
    monkeypatch,
) -> None:
    from app.core.config import settings

    monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
    monkeypatch.setattr(settings, "OPENAI_BASE_URL", "https://api.deepseek.com/v1")
    target = real_model.build_real_model_target(
        load_config("evals/config/real-model.yaml"),
        api_key="dotenv-key",
    )

    assert target._base_url == "https://api.deepseek.com"


@pytest.mark.asyncio
async def test_real_model_functional_failure_is_scored_separately(
    monkeypatch, tmp_path: Path
) -> None:
    case = _live_case(
        "functional-failure",
        events=[{"type": "message_chunk", "content": "answered without the tool"}],
        with_contract=True,
    )
    gateway = _Gateway([event.model_dump() for event in case.fixtures.events])
    monkeypatch.setattr(adapter, "OpenAIModelGateway", lambda **_: gateway)
    target = real_model.build_real_model_target(
        load_config("evals/config/real-model.yaml"),
        base_url="https://api.openai.com/v1",
        api_key="synthetic-evaluation-key",
        transcript_dir=tmp_path,
    )

    result = await run_case(case, target)

    assert result.passed is False
    assert result.outcome == "functional_failure"
    assert result.l6 is not None
    assert result.l6.task_success is False
    assert result.l6.scores["task_success"] == 0.0
    assert result.l6.scores["tool_selection"] == 0.0
    assert result.l6.scores["termination"] == 1.0
    assert result.l6.scores["steps"] == 1.0


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
    assert case.outcome == "provider_error"
    assert case.l6 is not None
    assert case.l6.outcome == "provider_error"
    assert case.l6.scores == {}
    assert report.aggregates["l6_provider_error_count"] == 1
    assert report.aggregates["l6_functional_case_count"] == 0
    assert "l6_functional_pass_rate" not in report.aggregates
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


def test_controlled_capabilities_reject_unbacked_external_actions() -> None:
    from app.evaluation.controlled import validate_controlled_capabilities

    with pytest.raises(ValueError, match="not fixture-backed"):
        validate_controlled_capabilities(
            "controlled-v1",
            ["search_remote_subjects"],
        )


@pytest.mark.asyncio
async def test_controlled_allowlist_denies_unlisted_action(
    monkeypatch, tmp_path: Path
) -> None:
    case = _live_case("controlled-denied", capability="search_remote_subjects")
    gateway = _Gateway(
        [
            {
                "type": "tool_call_start",
                "name": "search_remote_subjects",
                "arguments": {"keyword": "uncontrolled"},
            },
            {"type": "message_chunk", "content": "denied response"},
        ]
    )
    monkeypatch.setattr(adapter, "OpenAIModelGateway", lambda **_: gateway)
    target = real_model.build_real_model_target(
        load_config("evals/config/real-model.yaml"),
        base_url="https://api.openai.com/v1",
        api_key="synthetic-evaluation-key",
        transcript_dir=tmp_path,
    )

    result = await target.evaluate(case)

    assert result.policy_denied_count == 1
    assert result.tool_failure_count == 1
    assert "search_remote_subjects" in result.capabilities


@pytest.mark.asyncio
async def test_controlled_external_fixture_returns_fixed_search_response(
    monkeypatch, tmp_path: Path
) -> None:
    case = _live_case("controlled-anime", capability="search_anime_advanced")
    gateway = _Gateway(
        [
            {
                "type": "tool_call_start",
                "name": "search_anime_advanced",
                "arguments": {"keyword": "Frieren"},
            },
            {"type": "message_chunk", "content": "Frieren result"},
        ]
    )
    monkeypatch.setattr(adapter, "OpenAIModelGateway", lambda **_: gateway)
    target = real_model.build_real_model_target(
        load_config("evals/config/real-model.yaml"),
        base_url="https://api.openai.com/v1",
        api_key="synthetic-evaluation-key",
        transcript_dir=tmp_path,
    )

    result = await target.evaluate(case)

    assert result.run_status == "completed"
    assert result.capabilities == ["search_anime_advanced"]
    assert result.tool_success_count == 1
    transcript = json.loads(
        (tmp_path / "controlled-anime.json").read_text(encoding="utf-8")
    )
    invocation = transcript["invocations"][0]
    assert invocation["result"]["total"] == 1
    assert invocation["result"]["results"][0]["name"] == "Sousou no Frieren"


@pytest.mark.asyncio
async def test_repeated_runs_use_a_fresh_isolated_database(
    monkeypatch, tmp_path: Path
) -> None:
    events: list[dict] = [
        {
            "type": "tool_call_start",
            "name": "list_collections",
            "arguments": {},
        },
        {"type": "message_chunk", "content": "empty collection"},
    ]
    config = load_config("evals/config/real-model.yaml")

    for index in range(2):
        gateway = _Gateway(events)
        monkeypatch.setattr(adapter, "OpenAIModelGateway", lambda **_: gateway)
        case = _live_case(
            f"isolated-{index}",
            user_id=951,
            capability="list_collections",
        )
        target = real_model.build_real_model_target(
            config,
            base_url="https://api.openai.com/v1",
            api_key="synthetic-evaluation-key",
            transcript_dir=tmp_path / f"run-{index}",
        )
        result = await target.evaluate(case)
        assert result.tool_success_count == 1
        transcript = json.loads(
            (tmp_path / f"run-{index}" / f"isolated-{index}.json").read_text(
                encoding="utf-8"
            )
        )
        output = transcript["invocations"][0]["result"]
        assert output["total"] == 0
        assert output["collections"] == []


def test_run_scoped_artifacts_are_confined_and_not_overwritten(
    monkeypatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "synthetic-evaluation-key")
    monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
    monkeypatch.setattr(
        adapter,
        "OpenAIModelGateway",
        lambda **_: _Gateway([{"type": "message_chunk", "content": "ok"}]),
    )
    base_args = [
        "--config",
        "evals/config/real-model.yaml",
        "--base-url",
        "https://api.openai.com/v1",
        "--case",
        "real-model-chat-basic",
        "--run-dir",
        str(tmp_path),
    ]

    assert real_model.main([*base_args, "--run-id", "run-a"]) == 0
    assert real_model.main([*base_args, "--run-id", "run-b"]) == 0
    assert real_model.main([*base_args, "--run-id", "run-a"]) == 2

    for run_id in ("run-a", "run-b"):
        run_dir = tmp_path / run_id
        assert (run_dir / "report.json").is_file()
        assert (run_dir / "transcripts" / "real-model-chat-basic.json").is_file()
        manifest = json.loads(
            (run_dir / "run-manifest.json").read_text(encoding="utf-8")
        )
        assert manifest["run_id"] == run_id
        assert manifest["dataset_digest"]
        assert manifest["controlled"]["external_fixtures"] == "controlled-v1"
        assert manifest["controlled"]["run_scoped_artifacts"] is True

    files = [path for path in tmp_path.rglob("*") if path.is_file()]
    assert files
    assert all(
        path.relative_to(tmp_path).parts[0] in {"run-a", "run-b"} for path in files
    )

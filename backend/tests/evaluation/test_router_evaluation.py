"""Runtime-backed routing evidence and evaluation scoring tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.capabilities.factory import build_capability_registry
from app.evaluation import adapter, entrypoint
from app.evaluation.config import EvaluationConfig, load_config
from app.evaluation.entrypoint import run_headless_case
from app.evaluation.runner import _attach_transcript_paths, run_case
from app.evaluation.scripted_llm import ScriptedLLM
from app.evaluation.types import CaseResult, EvalCase, ExecutionResult
from app.trace import TraceEventType
from app.trace.sql_store import SqlTraceStore


def _case(
    case_id: str,
    prompt: str,
    *,
    expected_agent: str | None = None,
) -> EvalCase:
    payload = {
        "id": case_id,
        "category": "routing",
        "input_messages": [{"role": "user", "content": prompt}],
        "user_fixture": {"user_id": 9301},
        "assertions": {
            "response_schema": "text",
            "max_latency_ms": 10_000,
            "max_calls": 5,
        },
        "fixtures": {"events": [{"type": "message_chunk", "content": "done"}]},
    }
    if expected_agent is not None:
        payload["expected_agent"] = expected_agent
    return EvalCase.model_validate(payload)


@pytest.mark.parametrize(
    "config_name",
    [
        "anime-agent-benchmark-v1.yaml",
        "real-model.yaml",
        "real-model-quality.yaml",
        "task-benchmark.yaml",
    ],
)
def test_live_provider_configs_use_the_model_router(config_name: str) -> None:
    config_path = Path(__file__).parents[2] / "evals" / "config" / config_name

    config = load_config(config_path)

    assert config.routing.enabled is True
    assert config.routing.version == "model-v1"


def test_shared_router_assembly_uses_production_registry() -> None:
    from app.harness.execution import build_specialist_router

    registry = build_capability_registry()

    router = build_specialist_router(registry, memory_service=None, enabled=True)

    assert router is not None
    assert router.route("请推荐一些动画").selected_agent == "recommendation"
    assert (
        build_specialist_router(
            registry,
            memory_service=None,
            enabled=False,
        )
        is None
    )


def test_shared_router_assembly_preserves_model_router_version() -> None:
    from app.harness.execution import build_specialist_router

    router = build_specialist_router(
        build_capability_registry(),
        memory_service=None,
        enabled=True,
        version="model-v1",
    )

    assert router is not None
    assert router.version == "model-v1"
    assert router.candidate_agent_names == ["recommendation", "fallback"]


@pytest.mark.asyncio
async def test_headless_recommendation_route_dispatches_without_model_call(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    case = _case("router-cold-start", "\u8bf7\u63a8\u8350\u4e00\u4e9b\u52a8\u753b")
    gateway = ScriptedLLM([])
    traces = []
    query = SqlTraceStore.query

    async def capture_trace(self, trace_id: str, *, user_id: int | None = None):
        trace = await query(self, trace_id, user_id=user_id)
        traces.append(trace)
        return trace

    monkeypatch.setattr(SqlTraceStore, "query", capture_trace)

    result, events = await run_headless_case(
        case,
        registry=build_capability_registry(),
        model_gateway=gateway,
        model="offline-router-fixture",
        fail_on_run_failure=True,
        transcript_dir=tmp_path,
        allowed_public_names={
            "generate_user_profile_tool",
            "search_anime_advanced",
        },
        routing_enabled=True,
    )

    route_events = [event for event in events if event.get("type") == "route_decision"]
    assert result.run_status == "completed"
    assert result.route == "recommendation"
    assert result.route_agent == "recommendation"
    assert result.route_observed is True
    assert result.capabilities == ["generate_user_profile_tool"]
    assert result.model_call_count == 0
    assert gateway.calls == []
    assert len(route_events) == 1
    assert [
        event.get("capability")
        for event in events
        if event.get("type") == "tool_call_start"
    ] == ["generate_user_profile_tool"]
    trace_events = [event for step in traces[0].steps for event in step.events]
    routing_trace = next(
        event
        for event in trace_events
        if event.event_type == TraceEventType.ROUTING_DECISION
    )
    specialist_trace = next(
        event
        for event in trace_events
        if event.event_type == TraceEventType.AGENT_RESULT
        and event.data.get("kind") == "subagent"
    )
    assert routing_trace.data == {
        "agent": "recommendation",
        "route": "recommendation",
    }
    assert specialist_trace.data == {
        "agent": "recommendation",
        "name": "recommendation",
        "kind": "subagent",
    }
    assert "content" not in specialist_trace.data

    transcript = json.loads((tmp_path / f"{case.id}.json").read_text(encoding="utf-8"))
    assert transcript["result"]["route_agent"] == "recommendation"
    assert transcript["result"]["route_observed"] is True


@pytest.mark.asyncio
async def test_fallback_route_is_observed_and_transcript_matches(
    tmp_path: Path,
) -> None:
    case = _case("router-fallback", "Explain what an anime season is.")
    gateway = ScriptedLLM.from_script_events(case.fixtures.events)

    result, events = await run_headless_case(
        case,
        registry=build_capability_registry(),
        model_gateway=gateway,
        model="offline-router-fixture",
        fail_on_run_failure=True,
        transcript_dir=tmp_path,
        routing_enabled=True,
    )

    route_events = [event for event in events if event.get("type") == "route_decision"]
    assert result.route == "chat"
    assert result.route_agent == "fallback"
    assert result.route_observed is True
    assert len(route_events) == 1
    assert route_events[0]["route"] == "unknown"
    assert route_events[0]["agent"] == "fallback"
    transcript = json.loads((tmp_path / f"{case.id}.json").read_text(encoding="utf-8"))
    assert transcript["result"]["route"] == result.route
    assert transcript["result"]["route_agent"] == "fallback"
    assert transcript["result"]["route_observed"] is True


@pytest.mark.asyncio
async def test_expected_agent_without_runtime_route_evidence_fails() -> None:
    case = _case(
        "router-evidence-required",
        "Please recommend a show.",
        expected_agent="recommendation",
    )

    class UnobservedTarget:
        async def evaluate(self, _case: EvalCase) -> ExecutionResult:
            return ExecutionResult(route="recommendation")

    result = await run_case(case, UnobservedTarget())

    assert result.passed is False
    metric = next(
        metric for metric in result.metrics if metric.metric == "router_accuracy"
    )
    assert metric.value == 0.0
    assert metric.passed is False
    assert "not observed" in metric.detail


@pytest.mark.asyncio
async def test_production_target_passes_routing_config_to_headless_entrypoint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = EvaluationConfig(
        name="router-config-test",
        dataset="unused.jsonl",
        routing={"enabled": True, "version": "model-v1"},
    )
    captured: dict[str, object] = {}

    class StubGateway:
        async def close(self) -> None:
            return None

    gateway = StubGateway()
    monkeypatch.setattr(adapter, "_provider_endpoint_policy", lambda: None)
    monkeypatch.setattr(adapter, "_configured_api_key", lambda _explicit: "fixture")
    monkeypatch.setattr(
        adapter,
        "_configured_base_url",
        lambda _explicit: "https://provider.example/v1",
    )
    monkeypatch.setattr(
        adapter,
        "resolve_provider_base_url",
        lambda base_url, policy: base_url,
    )
    monkeypatch.setattr(
        adapter,
        "OpenAIModelGateway",
        lambda **_kwargs: gateway,
    )

    async def capture_headless(_case: EvalCase, **kwargs):
        captured.update(kwargs)
        return ExecutionResult(route="chat", text="done"), []

    monkeypatch.setattr(entrypoint, "run_headless_case", capture_headless)
    target = adapter.ProductionRuntimeTarget(
        config,
        base_url="https://provider.example/v1",
        api_key="fixture",
    )

    await target.evaluate(_case("router-target-config", "A question"))

    assert captured["routing_enabled"] is True
    assert captured["routing_version"] == "model-v1"


def test_transcript_index_uses_the_path_written_by_each_target(tmp_path: Path) -> None:
    case_id = "transcript-target-path"
    transcript_root = tmp_path / f"{case_id}.json"
    transcript_nested = tmp_path / "offline-config" / f"{case_id}.json"
    transcript_root.parent.mkdir(parents=True, exist_ok=True)
    transcript_nested.parent.mkdir(parents=True)
    transcript_root.write_text("stale root transcript", encoding="utf-8")
    transcript_nested.write_text("current offline transcript", encoding="utf-8")
    result = CaseResult(case_id=case_id, category="routing", passed=True)

    offline_config = EvaluationConfig(
        name="offline-config",
        dataset="unused.jsonl",
        transcript_dir=str(tmp_path),
        target_factory="app.evaluation.entrypoint:create_entrypoint_target",
    )
    live_config = EvaluationConfig(
        name="live-config",
        dataset="unused.jsonl",
        transcript_dir=str(tmp_path),
        target_factory="app.evaluation.adapter:create_production_target",
    )

    offline = _attach_transcript_paths([result], offline_config)[0]
    live = _attach_transcript_paths([result], live_config)[0]

    assert offline.transcript_path == str(transcript_nested)
    assert live.transcript_path == str(transcript_root)

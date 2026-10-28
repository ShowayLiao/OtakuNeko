import json
from collections.abc import AsyncIterator, Sequence
from typing import Any

import pytest

from app.agents.agent_registry import AgentRegistry
from app.agents.recommendation_agent import RecommendationAgent
from app.agents.router import AgentRouter
from app.capabilities.base import BaseCapability
from app.capabilities.anime import AnimeCapability
from app.capabilities.registry import CapabilityRegistry
from app.capabilities.types import ActionDescriptor
from app.harness.contracts import ExecutionContext, RunEvent
from app.harness.dispatcher import Dispatcher
from app.harness.model_gateway import ModelGateway
from app.harness.model_types import ModelCallResult, ModelStreamEvent
from app.harness.persistence.event_store import EventStore
from app.harness.persistence.run_store import RunStore
from app.harness.result import AgentResult
from app.harness.runtime import AgentRuntime
from app.harness.task import AgentTask
from app.models.agent_run import AgentInvocation, AgentRun, AgentRunEvent


class RuntimeRecommendationCapability(BaseCapability):
    @property
    def name(self):
        return "recommendation"

    @property
    def description(self):
        return "Runtime recommendation profile"

    def actions(self):
        return [
            ActionDescriptor(
                name="generate_profile",
                public_name="generate_user_profile_tool",
                description="Generate a recommendation profile",
                input_schema={
                    "type": "object",
                    "properties": {
                        "collections": {
                            "type": "array",
                            "items": {"type": "object"},
                        }
                    },
                    "required": ["collections"],
                },
                requires_auth=True,
            )
        ]

    async def execute(self, action, **kwargs):
        return {
            "success": True,
            "profile": {
                "llm_summary": {
                    "total_rated": 1,
                    "favorite_tags": ["science-fiction"],
                    "strong_avoid_tags": [],
                },
                "watched_ids": [],
            },
            "evidence": {"source": "runtime-test"},
        }


class RuntimeAnimeCapability(BaseCapability):
    @property
    def name(self):
        return "anime"

    @property
    def description(self):
        return "Runtime anime search"

    def actions(self):
        return [
            ActionDescriptor(
                name="search",
                public_name="search_anime_advanced",
                description="Search anime",
                input_schema={
                    "type": "object",
                    "properties": {
                        "keyword": {"type": "string"},
                        "tags": {"type": "array", "items": {"type": "string"}},
                        "limit": {"type": "integer"},
                    },
                    "required": ["keyword"],
                },
            )
        ]

    async def execute(self, action, **kwargs):
        return {
            "success": True,
            "results": [
                {
                    "id": 1,
                    "name": "Runtime recommendation",
                    "score": 9,
                    "tags": ["science-fiction"],
                }
            ],
        }


class DecisionGatewayBase(ModelGateway):
    async def stream_infer(self, **kwargs: Any) -> AsyncIterator[ModelStreamEvent]:
        yield ModelStreamEvent(result=await self.infer(**kwargs))

    async def synthesize(
        self,
        *,
        goal: str,
        messages: list[dict[str, Any]],
        results: Sequence[AgentResult | dict[str, Any]],
        **kwargs: Any,
    ) -> str:
        raise AssertionError("decision test must not synthesize")

    async def synthesize_result(
        self,
        *,
        goal: str,
        messages: list[dict[str, Any]],
        results: Sequence[AgentResult | dict[str, Any]],
        **kwargs: Any,
    ) -> ModelCallResult:
        raise AssertionError("decision test must not synthesize")


class NoModelGateway(DecisionGatewayBase):
    async def infer(self, **kwargs):
        raise AssertionError(
            "recommendation specialist must not call the primary model"
        )


class CatalogCapability(BaseCapability):
    @property
    def name(self):
        return "catalog"

    @property
    def description(self):
        return "Catalog test capability"

    def actions(self):
        return [
            ActionDescriptor(
                name="lookup",
                public_name="catalog_lookup",
                description="Look up a catalog item",
                input_schema={
                    "type": "object",
                    "properties": {"keyword": {"type": "string"}},
                    "required": ["keyword"],
                },
            )
        ]

    async def execute(self, action, **kwargs):
        return {"success": True, "item": kwargs}


class DecisionModelGateway(DecisionGatewayBase):
    def __init__(self):
        self.calls = []

    async def infer(self, **kwargs):
        self.calls.append(kwargs)
        return ModelCallResult(
            provider="test",
            model="test-model",
            operation="decision",
            status="completed",
            decision={"action": "finish", "content": "done"},
        )


class RetryDecisionModelGateway(DecisionGatewayBase):
    def __init__(self):
        self.calls = []

    async def infer(self, **kwargs):
        self.calls.append(kwargs)
        if len(self.calls) == 1:
            return ModelCallResult(
                provider="test",
                model="test-model",
                operation="decision",
                status="completed",
                text="not a decision",
                finish_reason="length",
            )
        return ModelCallResult(
            provider="test",
            model="test-model",
            operation="decision",
            status="completed",
            decision={"action": "finish", "content": "done"},
            finish_reason="stop",
        )


class ToolFeedbackModelGateway(DecisionGatewayBase):
    def __init__(self):
        self.calls = []

    async def infer(self, **kwargs):
        self.calls.append(kwargs)
        if len(self.calls) == 1:
            return ModelCallResult(
                provider="test",
                model="test-model",
                operation="decision",
                status="completed",
                decision={
                    "schema_version": "v1",
                    "decision_id": "decision-invoke",
                    "run_id": "run-tool-feedback",
                    "action": "invoke",
                    "capability": "catalog_lookup",
                    "capability_version": "v1",
                    "arguments": {"keyword": "anime"},
                },
            )
        if any(message.get("role") == "tool" for message in kwargs["messages"]):
            return ModelCallResult(
                provider="test",
                model="test-model",
                operation="decision",
                status="failed",
                error_code="invalid_request",
            )
        return ModelCallResult(
            provider="test",
            model="test-model",
            operation="decision",
            status="completed",
            decision={
                "schema_version": "v1",
                "decision_id": "decision-finish",
                "run_id": "run-tool-feedback",
                "action": "finish",
                "content": "done",
            },
        )


class SpecialistResultAdapter:
    async def stream(self, state, **kwargs):
        yield {
            "type": "route_decision",
            "route": "recommendation",
            "agent": "recommendation",
            "confidence": 1.0,
            "rationale": "matched",
        }
        yield {
            "type": "agent_result",
            "result": AgentResult(
                kind="subagent",
                name="recommendation",
                status="completed",
                data={"candidates": [{"id": 1, "name": "作品 A"}]},
                evidence={"source": "profile"},
            ).model_dump(),
        }


class FakeModelGateway(ModelGateway):
    def __init__(self):
        self.calls = []

    async def synthesize(self, *, goal, messages, results, **kwargs):
        self.calls.append(
            {"goal": goal, "messages": messages, "results": results, **kwargs}
        )
        return "LLM 整合后的推荐报告"

    async def infer(self, **kwargs: Any) -> ModelCallResult:
        raise AssertionError("synthesis test must not infer a decision")

    def stream_infer(self, **kwargs: Any) -> AsyncIterator[ModelStreamEvent]:
        raise AssertionError("synthesis test must not stream a decision")

    async def synthesize_result(
        self,
        *,
        goal: str,
        messages: list[dict[str, Any]],
        results: Sequence[AgentResult | dict[str, Any]],
        **kwargs: Any,
    ) -> ModelCallResult:
        raise AssertionError("synthesis test must not call synthesize_result")


class FailingModelGateway(FakeModelGateway):
    async def synthesize(self, **kwargs):
        self.calls.append(kwargs)
        raise RuntimeError("provider unavailable")


@pytest.mark.asyncio
async def test_runtime_returns_agent_result_to_model_gateway_before_final_message():
    gateway = FakeModelGateway()
    runtime = AgentRuntime(SpecialistResultAdapter(), model_gateway=gateway)
    task = AgentTask(
        user_id=1,
        goal="推荐几部动画",
        task_metadata={"messages": [{"role": "user", "content": "推荐几部动画"}]},
    )

    chunks = [
        chunk
        async for chunk in runtime.stream(
            task,
            messages=task.metadata["messages"],
            model="test-model",
        )
    ]

    assert gateway.calls[0]["goal"] == "推荐几部动画"
    assert gateway.calls[0]["results"][0].data["candidates"]
    assert {chunk["type"] for chunk in chunks} >= {
        "agent_result",
        "message_start",
        "message_chunk",
        "message_end",
    }
    assert {
        chunk.get("content") for chunk in chunks if chunk["type"] == "message_chunk"
    } == {"LLM 整合后的推荐报告"}


@pytest.mark.asyncio
async def test_runtime_degrades_when_model_synthesis_fails():
    runtime = AgentRuntime(
        SpecialistResultAdapter(), model_gateway=FailingModelGateway()
    )
    task = AgentTask(user_id=1, goal="推荐几部动画")

    chunks = [chunk async for chunk in runtime.stream(task, messages=[])]

    final = next(chunk for chunk in chunks if chunk["type"] == "message_chunk")
    assert "暂时无法生成详细整合报告" in final["content"]
    complete = next(chunk for chunk in chunks if chunk["type"] == "agent_complete")
    assert complete["status"] == "degraded"


@pytest.mark.asyncio
async def test_runtime_respects_model_call_budget():
    gateway = FakeModelGateway()
    runtime = AgentRuntime(
        SpecialistResultAdapter(), model_gateway=gateway, max_model_calls=0
    )
    task = AgentTask(user_id=1, goal="推荐几部动画")

    chunks = [chunk async for chunk in runtime.stream(task, messages=[])]

    assert gateway.calls == []
    final = next(chunk for chunk in chunks if chunk["type"] == "message_chunk")
    assert "模型调用预算不足" in final["content"]


@pytest.mark.asyncio
async def test_primary_decision_loop_passes_public_capability_catalog_to_model():
    registry = CapabilityRegistry()
    registry.register(CatalogCapability())
    gateway = DecisionModelGateway()
    runtime = AgentRuntime(
        None,
        model_gateway=gateway,
        dispatcher=Dispatcher(registry),
    )
    task = AgentTask(
        user_id=1,
        goal="lookup",
        task_metadata={
            "run_id": "run-catalog",
            "messages": [{"role": "user", "content": "lookup"}],
        },
    )
    context = ExecutionContext(
        principal_id=1,
        run_id="run-catalog",
        trace_id="trace-catalog",
        capability_allowlist=frozenset({"catalog_lookup"}),
    )

    chunks = [chunk async for chunk in runtime.stream_decision(task, context=context)]

    assert chunks[-1]["type"] == "run_completed"
    assert gateway.calls[0]["capability_catalog"][0]["public_name"] == "catalog_lookup"


@pytest.mark.asyncio
async def test_bangumi_calendar_workflow_exposes_followup_detail_capability(
    monkeypatch,
):
    async def fake_calendar():
        return {"days": [{"weekday": {"id": 1}, "items": [{"id": 101}]}]}

    async def fake_details(subject_ids):
        return {
            "details": [{"id": subject_ids[0], "name": "Anime", "summary": "summary"}],
            "failed_subject_ids": [],
        }

    monkeypatch.setattr("app.capabilities.anime.get_bangumi_calendar", fake_calendar)
    monkeypatch.setattr(
        "app.capabilities.anime.get_bangumi_subject_details", fake_details
    )

    class CalendarWorkflowGateway(DecisionGatewayBase):
        def __init__(self):
            self.calls = []

        async def infer(self, **kwargs):
            self.calls.append(kwargs)
            run_id = "run-bangumi-workflow"
            if len(self.calls) == 1:
                decision = {
                    "schema_version": "v1",
                    "decision_id": "calendar-1",
                    "run_id": run_id,
                    "action": "invoke",
                    "capability": "get_bangumi_calendar",
                    "capability_version": "v1",
                    "arguments": {},
                }
            elif len(self.calls) == 2:
                public_names = {
                    item["public_name"] for item in kwargs["capability_catalog"]
                }
                assert "get_anime_info_batch" in public_names
                decision = {
                    "schema_version": "v1",
                    "decision_id": "details-1",
                    "run_id": run_id,
                    "action": "invoke",
                    "capability": "get_anime_info_batch",
                    "capability_version": "v1",
                    "arguments": {"subject_ids": [101]},
                }
            else:
                decision = {
                    "schema_version": "v1",
                    "decision_id": "finish-1",
                    "run_id": run_id,
                    "action": "finish",
                    "content": "done",
                }
            return ModelCallResult(
                provider="test",
                model="test-model",
                operation="decision",
                status="completed",
                decision=decision,
            )

    registry = CapabilityRegistry()
    registry.register(AnimeCapability())
    gateway = CalendarWorkflowGateway()
    runtime = AgentRuntime(
        None,
        model_gateway=gateway,
        dispatcher=Dispatcher(registry),
    )
    task = AgentTask(
        user_id=1,
        goal="整理本周值得关注的新番",
        task_metadata={
            "run_id": "run-bangumi-workflow",
            "messages": [{"role": "user", "content": "整理本周值得关注的新番"}],
        },
    )
    context = ExecutionContext(
        principal_id=1,
        run_id="run-bangumi-workflow",
        trace_id="trace-bangumi-workflow",
    )

    chunks = [chunk async for chunk in runtime.stream_decision(task, context=context)]

    assert chunks[-1]["type"] == "run_completed"
    assert len(gateway.calls) == 3


@pytest.mark.asyncio
async def test_primary_decision_loop_retries_once_after_invalid_model_decision():
    registry = CapabilityRegistry()
    gateway = RetryDecisionModelGateway()
    runtime = AgentRuntime(
        None,
        model_gateway=gateway,
        dispatcher=Dispatcher(registry),
    )
    task = AgentTask(
        user_id=1,
        goal="finish",
        task_metadata={
            "run_id": "run-retry",
            "messages": [{"role": "user", "content": "finish"}],
        },
    )
    context = ExecutionContext(
        principal_id=1,
        run_id="run-retry",
        trace_id="trace-retry",
    )

    chunks = [chunk async for chunk in runtime.stream_decision(task, context=context)]

    assert len(gateway.calls) == 2
    assert chunks[-1]["type"] == "run_completed"
    assert not any(chunk["type"] == "run_failed" for chunk in chunks)
    retry_messages = gateway.calls[1]["messages"]
    repair_index = next(
        index
        for index, message in enumerate(retry_messages)
        if "Reason code: invalid_json" in message["content"]
    )
    assert retry_messages[repair_index - 1]["role"] == "assistant"
    assert "invalid_json" in retry_messages[repair_index]["content"]
    retry_model_call = next(
        chunk
        for chunk in chunks
        if chunk["type"] == "model_call"
        and chunk.get("decision_repair_reason_code") == "invalid_json"
    )
    assert retry_model_call["finish_reason"] == "stop"


@pytest.mark.asyncio
async def test_primary_decision_loop_reports_safe_parse_failure_details():
    class RepeatedInvalidDecisionModelGateway(DecisionGatewayBase):
        def __init__(self):
            self.calls = []

        async def infer(self, **kwargs):
            self.calls.append(kwargs)
            return ModelCallResult(
                provider="test",
                model="test-model",
                operation="decision",
                status="completed",
                decision={
                    "schema_version": "v1",
                    "decision_id": len(self.calls),
                    "run_id": kwargs["run_id"],
                    "action": "invoke",
                    "capability": "catalog_lookup",
                    "capability_version": 1,
                    "arguments": [],
                },
                finish_reason="stop",
            )

    registry = CapabilityRegistry()
    gateway = RepeatedInvalidDecisionModelGateway()
    runtime = AgentRuntime(
        None,
        model_gateway=gateway,
        dispatcher=Dispatcher(registry),
    )
    task = AgentTask(
        user_id=1,
        goal="finish",
        task_metadata={
            "run_id": "run-invalid-details",
            "messages": [{"role": "user", "content": "finish"}],
        },
    )
    context = ExecutionContext(
        principal_id=1,
        run_id="run-invalid-details",
        trace_id="trace-invalid-details",
    )

    chunks = [chunk async for chunk in runtime.stream_decision(task, context=context)]

    assert len(gateway.calls) == 2
    assert chunks[-1]["type"] == "run_failed"
    expected_fields = ["arguments", "capability_version", "decision_id"]
    assert chunks[-1]["decision_failure_reason_code"] == "decision_schema_invalid"
    assert chunks[-1]["decision_failure_fields"] == expected_fields
    retry_model_call = next(
        chunk
        for chunk in chunks
        if chunk["type"] == "model_call" and chunk.get("decision_repair_reason_code")
    )
    assert retry_model_call["decision_repair_reason_code"] == "decision_schema_invalid"
    assert retry_model_call["decision_repair_fields"] == expected_fields
    assert retry_model_call["finish_reason"] == "stop"
    repair_prompt = next(
        message["content"]
        for message in gateway.calls[1]["messages"]
        if message.get("role") == "system"
        and "Reason code: decision_schema_invalid" in message.get("content", "")
    )
    assert "arguments, capability_version, decision_id" in repair_prompt


@pytest.mark.asyncio
async def test_primary_decision_loop_uses_provider_compatible_tool_feedback():
    registry = CapabilityRegistry()
    registry.register(CatalogCapability())
    gateway = ToolFeedbackModelGateway()
    runtime = AgentRuntime(
        None,
        model_gateway=gateway,
        dispatcher=Dispatcher(registry),
    )
    task = AgentTask(
        user_id=1,
        goal="lookup",
        task_metadata={
            "run_id": "run-tool-feedback",
            "messages": [{"role": "user", "content": "lookup"}],
        },
    )
    context = ExecutionContext(
        principal_id=1,
        run_id="run-tool-feedback",
        trace_id="trace-tool-feedback",
        capability_allowlist=frozenset({"catalog_lookup"}),
    )

    chunks = [chunk async for chunk in runtime.stream_decision(task, context=context)]

    assert chunks[-1]["type"] == "run_completed"
    assert len(gateway.calls) == 2
    messages = gateway.calls[1]["messages"]
    feedback = next(
        message
        for message in messages
        if message["role"] == "user"
        and "untrusted capability result data" in message["content"]
    )
    feedback_index = messages.index(feedback)
    assert messages[feedback_index - 1]["role"] == "assistant"
    assert feedback["role"] == "user"
    assert "untrusted capability result data" in feedback["content"]


@pytest.mark.asyncio
async def test_primary_runtime_executes_recommendation_specialist_through_dispatcher():
    profile_capability = RuntimeRecommendationCapability()
    anime_capability = RuntimeAnimeCapability()
    capability_registry = CapabilityRegistry()
    capability_registry.register(profile_capability)
    capability_registry.register(anime_capability)

    agent_registry = AgentRegistry()
    agent_registry.register(
        "recommendation",
        RecommendationAgent(
            profile_capability,
            anime_capability=anime_capability,
        ),
    )
    gateway = NoModelGateway()
    dispatcher = Dispatcher(capability_registry)
    runtime = AgentRuntime(
        None,
        model_gateway=gateway,
        dispatcher=dispatcher,
        specialist_router=AgentRouter(agent_registry),
    )
    task = AgentTask(
        user_id=7,
        goal="推荐动漫",
        task_metadata={
            "run_id": "run-recommendation-specialist",
            "messages": [{"role": "user", "content": "推荐动漫"}],
            "collections": [{"id": 1}],
        },
    )
    context = ExecutionContext(
        principal_id=7,
        run_id="run-recommendation-specialist",
        trace_id="trace-recommendation-specialist",
        capability_allowlist=frozenset(
            {"generate_user_profile_tool", "search_anime_advanced"}
        ),
    )

    chunks = [chunk async for chunk in runtime.stream_decision(task, context=context)]

    assert not gateway.__dict__.get("calls")
    assert [event.event_type for event in dispatcher.events] == [
        "invocation_start",
        "invocation_end",
        "invocation_start",
        "invocation_end",
    ]
    assert any(chunk["type"] == "route_decision" for chunk in chunks)
    assert any(chunk["type"] == "agent_result" for chunk in chunks)
    tool_events = [
        chunk["type"]
        for chunk in chunks
        if chunk["type"] in {"tool_call_start", "tool_call_end"}
    ]
    assert tool_events == [
        "tool_call_start",
        "tool_call_end",
        "tool_call_start",
        "tool_call_end",
    ]
    assert max(
        index for index, chunk in enumerate(chunks) if chunk["type"] == "tool_call_end"
    ) < next(
        index for index, chunk in enumerate(chunks) if chunk["type"] == "agent_result"
    )
    assert any(
        chunk["type"] == "message_chunk" and chunk["content"] for chunk in chunks
    )
    assert chunks[-1]["type"] == "run_completed"


@pytest.mark.asyncio
async def test_primary_runtime_uses_unique_specialist_invocation_ids_across_runs():
    class StrictRunStore(RunStore):
        def __init__(self) -> None:
            self.runs: dict[str, AgentRun] = {}
            self.invocations: dict[str, AgentInvocation] = {}

        async def create(self, run: AgentRun | None = None, **fields: Any) -> AgentRun:
            if run is None:
                run = AgentRun(**fields)
            self.runs[run.run_id] = run
            return run

        async def get(
            self, run_id: str, *, user_id: int | None = None
        ) -> AgentRun | None:
            run = self.runs.get(run_id)
            if run is not None and user_id is not None and run.user_id != user_id:
                return None
            return run

        async def transition(
            self, run_id: str, status: str, *, error_code: str | None = None
        ) -> AgentRun:
            run = self.runs[run_id]
            run.status = status
            run.error_code = error_code
            return run

        async def create_invocation(
            self,
            *,
            run_id: str,
            invocation_id: str,
            sequence: int,
            capability: str,
            capability_version: str = "v1",
            input_payload: dict[str, Any] | None = None,
            idempotency_key: str | None = None,
        ) -> AgentInvocation:
            existing = self.invocations.get(invocation_id)
            if existing is not None and existing.run_id != run_id:
                raise RuntimeError("invocation identity conflict")
            if existing is not None:
                return existing
            invocation = AgentInvocation(
                invocation_id=invocation_id,
                run_id=run_id,
                sequence=sequence,
                capability=capability,
                capability_version=capability_version,
                status="running",
                idempotency_key=idempotency_key,
            )
            self.invocations[invocation_id] = invocation
            return invocation

        async def finish_invocation(
            self, invocation_id: str, status: str, *, error_code: str | None = None
        ) -> AgentInvocation:
            invocation = self.invocations[invocation_id]
            invocation.status = status
            invocation.error_code = error_code
            return invocation

    class MemoryEventStore(EventStore):
        def __init__(self) -> None:
            self.events: list[AgentRunEvent] = []

        async def append(
            self, event: RunEvent | AgentRunEvent, *, event_id: str | None = None
        ) -> AgentRunEvent:
            stored = (
                event
                if isinstance(event, AgentRunEvent)
                else AgentRunEvent(
                    event_id=event_id or f"evt-{event.run_id}-{event.sequence}",
                    run_id=event.run_id,
                    sequence=event.sequence,
                    event_type=event.event_type,
                    invocation_id=event.invocation_id,
                    payload_json=json.dumps(event.payload),
                )
            )
            self.events.append(stored)
            return stored

        async def list_after(
            self, run_id: str, after_sequence: int = 0, *, limit: int = 500
        ) -> list[AgentRunEvent]:
            return [
                event
                for event in self.events
                if event.run_id == run_id and event.sequence > after_sequence
            ][:limit]

    profile_capability = RuntimeRecommendationCapability()
    anime_capability = RuntimeAnimeCapability()
    capability_registry = CapabilityRegistry()
    capability_registry.register(profile_capability)
    capability_registry.register(anime_capability)
    agent_registry = AgentRegistry()
    agent_registry.register(
        "recommendation",
        RecommendationAgent(
            profile_capability,
            anime_capability=anime_capability,
        ),
    )
    run_store = StrictRunStore()
    runtime = AgentRuntime(
        None,
        model_gateway=NoModelGateway(),
        dispatcher=Dispatcher(capability_registry),
        specialist_router=AgentRouter(agent_registry),
        run_store=run_store,
        event_store=MemoryEventStore(),
    )

    async def execute(run_id):
        task = AgentTask(
            user_id=7,
            goal="推荐动漫",
            task_metadata={
                "run_id": run_id,
                "messages": [{"role": "user", "content": "推荐动漫"}],
            },
        )
        context = ExecutionContext(
            principal_id=7,
            run_id=run_id,
            trace_id=f"trace-{run_id}",
            capability_allowlist=frozenset(
                {"generate_user_profile_tool", "search_anime_advanced"}
            ),
        )
        return [event async for event in runtime.stream_decision(task, context=context)]

    first = await execute("run-specialist-1")
    second = await execute("run-specialist-2")

    assert first[-1]["type"] == "run_completed"
    assert second[-1]["type"] == "run_completed"
    assert len(run_store.invocations) == 4
    assert {invocation.run_id for invocation in run_store.invocations.values()} == {
        "run-specialist-1",
        "run-specialist-2",
    }

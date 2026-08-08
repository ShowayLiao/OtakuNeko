import pytest

from app.capabilities.base import BaseCapability
from app.capabilities.registry import CapabilityRegistry
from app.capabilities.types import ActionDescriptor
from app.harness.contracts import ExecutionContext
from app.harness.dispatcher import Dispatcher
from app.harness.model_types import ModelCallResult
from app.harness.result import AgentResult
from app.harness.runtime import AgentRuntime
from app.harness.task import AgentTask


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


class DecisionModelGateway:
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


class RetryDecisionModelGateway:
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
            )
        return ModelCallResult(
            provider="test",
            model="test-model",
            operation="decision",
            status="completed",
            decision={"action": "finish", "content": "done"},
        )


class ToolFeedbackModelGateway:
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


class FakeModelGateway:
    def __init__(self):
        self.calls = []

    async def synthesize(self, *, goal, messages, results, **kwargs):
        self.calls.append(
            {"goal": goal, "messages": messages, "results": results, **kwargs}
        )
        return "LLM 整合后的推荐报告"


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
        metadata={"messages": [{"role": "user", "content": "推荐几部动画"}]},
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
        chunk.get("content")
        for chunk in chunks
        if chunk["type"] == "message_chunk"
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
        object(),
        model_gateway=gateway,
        dispatcher=Dispatcher(registry),
    )
    task = AgentTask(
        user_id=1,
        goal="lookup",
        metadata={
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

    chunks = [
        chunk
        async for chunk in runtime.stream_decision(task, context=context)
    ]

    assert chunks[-1]["type"] == "run_completed"
    assert gateway.calls[0]["capability_catalog"][0]["public_name"] == "catalog_lookup"


@pytest.mark.asyncio
async def test_primary_decision_loop_retries_once_after_invalid_model_decision():
    registry = CapabilityRegistry()
    gateway = RetryDecisionModelGateway()
    runtime = AgentRuntime(
        object(),
        model_gateway=gateway,
        dispatcher=Dispatcher(registry),
    )
    task = AgentTask(
        user_id=1,
        goal="finish",
        metadata={
            "run_id": "run-retry",
            "messages": [{"role": "user", "content": "finish"}],
        },
    )
    context = ExecutionContext(
        principal_id=1,
        run_id="run-retry",
        trace_id="trace-retry",
    )

    chunks = [
        chunk
        async for chunk in runtime.stream_decision(task, context=context)
    ]

    assert len(gateway.calls) == 2
    assert chunks[-1]["type"] == "run_completed"
    assert not any(chunk["type"] == "run_failed" for chunk in chunks)
    assert "valid JSON Decision" in gateway.calls[1]["messages"][-1]["content"]


@pytest.mark.asyncio
async def test_primary_decision_loop_uses_provider_compatible_tool_feedback():
    registry = CapabilityRegistry()
    registry.register(CatalogCapability())
    gateway = ToolFeedbackModelGateway()
    runtime = AgentRuntime(
        object(),
        model_gateway=gateway,
        dispatcher=Dispatcher(registry),
    )
    task = AgentTask(
        user_id=1,
        goal="lookup",
        metadata={
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

    chunks = [
        chunk
        async for chunk in runtime.stream_decision(task, context=context)
    ]

    assert chunks[-1]["type"] == "run_completed"
    assert len(gateway.calls) == 2
    feedback = gateway.calls[1]["messages"][-1]
    assert feedback["role"] == "user"
    assert "untrusted capability result data" in feedback["content"]

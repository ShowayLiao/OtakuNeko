import json
from types import SimpleNamespace

import pytest

from app.capabilities.base import BaseCapability
from app.capabilities.registry import CapabilityRegistry
from app.capabilities.types import ActionDescriptor, CapabilityResult
from app.harness.contracts import ExecutionContext
from app.harness.dispatcher import Dispatcher
from app.harness.model_gateway import OpenAICompatibleModelAdapter, OpenAIModelGateway
from app.harness.model_types import ModelCallResult, ModelDelta, ModelStreamEvent
from app.harness.runtime import AgentRuntime, _checkpoint_messages
from app.harness.task import AgentTask


class FakeCompletions:
    def __init__(self, response):
        self.response = response
        self.calls: list[dict] = []

    async def create(self, **kwargs):
        self.calls.append(kwargs)
        return self.response


class FakeClient:
    def __init__(self, completions):
        self.chat = SimpleNamespace(completions=completions)


def completion_response(*, reasoning_content: str = ""):
    return SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(
                    content='{"schema_version":"v1","decision_id":"d1","action":"respond","content":"answer"}',
                    reasoning_content=reasoning_content,
                ),
                finish_reason="stop",
            )
        ],
        usage=None,
    )


@pytest.mark.asyncio
async def test_complete_preserves_provider_reasoning_content():
    completions = FakeCompletions(
        completion_response(reasoning_content="先分析用户意图")
    )
    adapter = OpenAICompatibleModelAdapter(
        FakeClient(completions), provider="deepseek"
    )

    result = await adapter.complete(
        messages=[{"role": "user", "content": "hello"}],
        model="deepseek-chat",
    )

    assert result.reasoning == "先分析用户意图"


@pytest.mark.asyncio
async def test_primary_infer_sends_deepseek_thinking_options():
    completions = FakeCompletions(completion_response())
    gateway = OpenAIModelGateway(
        api_key="test-key",
        base_url="https://api.deepseek.com",
        model="deepseek-chat",
        deepseek_options={"thinking": True, "reasoning_effort": "max"},
        client=FakeClient(completions),
    )

    await gateway.infer(
        goal="hello",
        messages=[{"role": "user", "content": "hello"}],
    )

    request = completions.calls[0]
    assert request["extra_body"] == {"thinking": {"type": "enabled"}}
    assert request["reasoning_effort"] == "max"


@pytest.mark.asyncio
async def test_primary_infer_forwards_deepseek_assistant_reasoning_content():
    completions = FakeCompletions(completion_response())
    gateway = OpenAIModelGateway(
        api_key="test-key",
        base_url="https://api.deepseek.com",
        model="deepseek-chat",
        deepseek_options={"thinking": True},
        client=FakeClient(completions),
    )

    await gateway.infer(
        goal="continue",
        messages=[
            {"role": "user", "content": "lookup"},
            {
                "role": "assistant",
                "content": '{"action":"invoke"}',
                "reasoning": "先判断需要查询",
            },
            {"role": "user", "content": "capability result"},
        ],
    )

    assert completions.calls[0]["messages"][1]["reasoning_content"] == "先判断需要查询"


@pytest.mark.asyncio
async def test_primary_infer_filters_deepseek_reasoning_for_other_providers():
    completions = FakeCompletions(completion_response())
    gateway = OpenAIModelGateway(
        api_key="test-key",
        base_url="https://api.openai.com/v1",
        model="gpt-test",
        client=FakeClient(completions),
    )

    await gateway.infer(
        goal="continue",
        messages=[
            {
                "role": "assistant",
                "content": '{"action":"invoke"}',
                "reasoning": "provider-private reasoning",
            }
        ],
    )

    assert "reasoning_content" not in completions.calls[0]["messages"][0]


class ContinuationCapability(BaseCapability):
    @property
    def name(self):
        return "continuation"

    @property
    def description(self):
        return "Continuation test capability"

    def actions(self):
        return [
            ActionDescriptor(
                name="lookup",
                public_name="continuation_lookup",
                description="Look up continuation data",
                input_schema={"type": "object"},
            )
        ]

    async def execute(self, action, **kwargs):
        return CapabilityResult.ok(item="result").to_dict()


class ThinkingContinuationGateway:
    def __init__(self):
        self.calls: list[dict] = []

    async def infer(self, **kwargs):
        self.calls.append(kwargs)
        if len(self.calls) == 1:
            decision = {
                "schema_version": "v1",
                "decision_id": "decision-invoke",
                "run_id": "run-thinking-continuation",
                "action": "invoke",
                "capability": "continuation_lookup",
                "capability_version": "v1",
                "arguments": {},
            }
            return ModelCallResult(
                provider="deepseek",
                model="deepseek-chat",
                operation="infer",
                status="completed",
                text=json.dumps(decision),
                reasoning="先判断需要查询",
            )
        return ModelCallResult(
            provider="deepseek",
            model="deepseek-chat",
            operation="infer",
            status="completed",
            text=json.dumps(
                {
                    "schema_version": "v1",
                    "decision_id": "decision-finish",
                    "run_id": "run-thinking-continuation",
                    "action": "finish",
                    "content": "done",
                }
            ),
        )


@pytest.mark.asyncio
async def test_runtime_preserves_deepseek_assistant_turn_before_tool_feedback():
    gateway = ThinkingContinuationGateway()
    registry = CapabilityRegistry()
    registry.register(ContinuationCapability())
    runtime = AgentRuntime(
        object(),
        model_gateway=gateway,
        dispatcher=Dispatcher(registry),
    )

    events = [
        event
        async for event in runtime.stream_decision(
            AgentTask(
                task_id=1,
                user_id=1,
                goal="lookup",
                metadata={
                    "run_id": "run-thinking-continuation",
                    "messages": [{"role": "user", "content": "lookup"}],
                },
            ),
            context=ExecutionContext(
                principal_id=1,
                run_id="run-thinking-continuation",
                trace_id="trace-thinking-continuation",
                capability_allowlist=frozenset({"continuation_lookup"}),
            ),
        )
    ]

    assert events[-1]["type"] == "run_completed"
    assert len(gateway.calls) == 2
    continuation = gateway.calls[1]["messages"]
    assert continuation[1]["role"] == "assistant"
    assert '"action": "invoke"' in continuation[1]["content"]
    assert continuation[1]["reasoning"] == "先判断需要查询"
    assert continuation[2]["role"] == "user"
    assert "untrusted capability result data" in continuation[2]["content"]


def test_checkpoint_projection_removes_runtime_reasoning_field():
    messages = [
        {"role": "user", "content": "lookup"},
        {
            "role": "assistant",
            "content": '{"action":"invoke"}',
            "reasoning": "不要写入 checkpoint",
        },
    ]

    assert _checkpoint_messages(messages) == [
        {"role": "user", "content": "lookup"},
        {"role": "assistant", "content": '{"action":"invoke"}'},
    ]


class ReasoningGateway:
    async def infer(self, **_kwargs):
        from app.harness.model_types import ModelCallResult

        return ModelCallResult(
            provider="deepseek",
            model="deepseek-chat",
            operation="infer",
            status="completed",
            reasoning="先分析用户意图",
            decision={
                "schema_version": "v1",
                "decision_id": "decision-1",
                "action": "respond",
                "content": "answer",
            },
        )


@pytest.mark.asyncio
async def test_runtime_emits_reasoning_events_for_primary_decision():
    runtime = AgentRuntime(
        object(),
        model_gateway=ReasoningGateway(),
        dispatcher=Dispatcher(CapabilityRegistry()),
    )

    events = [
        event
        async for event in runtime.stream_decision(
            AgentTask(
                task_id=1,
                user_id=1,
                goal="hello",
                metadata={
                    "run_id": "run-reasoning",
                    "messages": [{"role": "user", "content": "hello"}],
                },
            ),
            context=ExecutionContext(
                principal_id=1,
                run_id="run-reasoning",
                trace_id="trace-reasoning",
            ),
        )
    ]

    event_types = [event["type"] for event in events]
    assert event_types.index("thinking_start") < event_types.index("thinking_chunk")
    assert event_types.index("thinking_chunk") < event_types.index("thinking_end")
    assert event_types.index("thinking_end") < event_types.index("model_decision")
    assert next(
        event["content"]
        for event in events
        if event["type"] == "thinking_chunk"
    ) == "先分析用户意图"


class StreamingReasoningGateway:
    async def stream_infer(self, **_kwargs):
        yield ModelStreamEvent(delta=ModelDelta(kind="reasoning", text="先分析"))
        yield ModelStreamEvent(delta=ModelDelta(kind="reasoning", text="再决策"))
        yield ModelStreamEvent(
            result=ModelCallResult(
                provider="deepseek",
                model="deepseek-chat",
                operation="stream",
                status="completed",
                text='{"schema_version":"v1","decision_id":"stream-d",'
                '"action":"respond","content":"answer"}',
                reasoning="先分析再决策",
                decision={
                    "schema_version": "v1",
                    "decision_id": "stream-d",
                    "action": "respond",
                    "content": "answer",
                },
            )
        )


@pytest.mark.asyncio
async def test_runtime_forwards_each_reasoning_delta_before_parsing_final_decision():
    runtime = AgentRuntime(
        object(),
        model_gateway=StreamingReasoningGateway(),
        dispatcher=Dispatcher(CapabilityRegistry()),
    )

    events = [
        event
        async for event in runtime.stream_decision(
            AgentTask(
                task_id=1,
                user_id=1,
                goal="hello",
                metadata={
                    "run_id": "run-streaming-reasoning",
                    "messages": [{"role": "user", "content": "hello"}],
                },
            ),
            context=ExecutionContext(
                principal_id=1,
                run_id="run-streaming-reasoning",
                trace_id="trace-streaming-reasoning",
            ),
        )
    ]

    event_types = [event["type"] for event in events]
    assert event_types.count("thinking_chunk") == 2
    assert event_types.index("thinking_chunk") < event_types.index("thinking_end")
    assert event_types.index("thinking_end") < event_types.index("model_decision")
    assert [event["content"] for event in events if event["type"] == "thinking_chunk"] == [
        "先分析",
        "再决策",
    ]
    assert events[-1]["type"] == "run_completed"

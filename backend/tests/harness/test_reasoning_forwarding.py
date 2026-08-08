from types import SimpleNamespace

import pytest

from app.capabilities.registry import CapabilityRegistry
from app.harness.contracts import ExecutionContext
from app.harness.dispatcher import Dispatcher
from app.harness.model_gateway import OpenAICompatibleModelAdapter, OpenAIModelGateway
from app.harness.runtime import AgentRuntime
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

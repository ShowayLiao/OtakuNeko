from types import SimpleNamespace

import pytest

from app.harness.model_gateway import OpenAIModelGateway
from app.harness.result import AgentResult
from app.trace import AgentTrace, TraceEventType
from app.trace.recorder import bind_trace


def test_agent_result_supports_capability_and_subagent_kinds():
    result = AgentResult(
        kind="subagent",
        name="recommendation",
        status="completed",
        data={"candidates": [{"id": 1}]},
        evidence={"source": "profile"},
    )

    assert result.kind == "subagent"
    assert result.name == "recommendation"
    assert result.data["candidates"]


class FakeCompletions:
    def __init__(self):
        self.calls = []

    async def create(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="整合后的回答"))]
        )


class FakeClient:
    def __init__(self):
        self.chat = SimpleNamespace(completions=FakeCompletions())


@pytest.mark.asyncio
async def test_model_gateway_synthesizes_structured_execution_results():
    client = FakeClient()
    gateway = OpenAIModelGateway(
        api_key="test-key",
        base_url="https://example.test/v1",
        model="test-model",
        client=client,
    )

    content = await gateway.synthesize(
        goal="推荐几部动画",
        messages=[{"role": "user", "content": "推荐几部动画"}],
        results=[
            AgentResult(
                kind="capability",
                name="anime.search",
                status="completed",
                data={"items": [{"id": 1, "name": "作品 A"}]},
            )
        ],
    )

    assert content == "整合后的回答"
    assert gateway.context.model == "test-model"
    call = client.chat.completions.calls[0]
    assert call["model"] == "test-model"
    assert "作品 A" in str(call["messages"])


@pytest.mark.asyncio
async def test_model_gateway_records_synthesis_model_call():
    gateway = OpenAIModelGateway(
        api_key="test-key",
        base_url="https://example.test/v1",
        model="test-model",
        client=FakeClient(),
    )
    trace = AgentTrace(agent_name="test")

    with bind_trace(trace):
        await gateway.synthesize(goal="问题", messages=[], results=[])

    events = [event for step in trace.steps for event in step.events]
    assert any(
        event.event_type == TraceEventType.MODEL_CALL
        and event.data["operation"] == "model.synthesis"
        for event in events
    )

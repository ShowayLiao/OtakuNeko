import pytest

from app.harness.result import AgentResult
from app.harness.runtime import AgentRuntime
from app.harness.task import AgentTask


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

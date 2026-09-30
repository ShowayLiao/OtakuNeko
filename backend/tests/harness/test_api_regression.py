"""Regression coverage for the chat API harness entrypoint."""

import os

import pytest

os.environ["DEBUG"] = "false"
from app.api.v1 import agent as agent_api
from app.harness.model_types import ModelCallResult
from app.schemas.agent import ChatRequest, Message


class FakeGateway:
    def __init__(self, **kwargs):
        self.model = kwargs["model"]

    async def infer(self, **kwargs):
        return ModelCallResult(
            provider="fake",
            model=self.model,
            operation="infer",
            status="completed",
            decision={
                "schema_version": "v1",
                "decision_id": "api-answer",
                "action": "respond",
                "content": "ok",
            },
        )

    async def close(self):
        return None


@pytest.mark.asyncio
async def test_chat_endpoint_streams_through_harness(monkeypatch) -> None:
    monkeypatch.setattr(agent_api, "OpenAIModelGateway", FakeGateway)
    request = ChatRequest(
        model="test-model",
        messages=[Message(role="user", content="hello")],
    )

    response = await agent_api.chat_endpoint(
        request,
        x_api_key="test-key",
        x_base_url="https://api.openai.com/v1",
        user=None,
    )
    body = "".join([chunk async for chunk in response.body_iterator])

    assert "event: thinking_start" in body
    assert '"content": "ok"' in body
    assert "event: error" not in body

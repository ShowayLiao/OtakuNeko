"""Regression coverage for the chat API harness entrypoint."""

import os

import pytest

os.environ["DEBUG"] = "false"
from app.api.v1 import agent as agent_api
from app.schemas.agent import ChatRequest, Message


class FakeWorkflow:
    def __init__(self, **kwargs):
        self.checkpointer = object()
        self.memory = None

    async def _ensure_checkpointer(self) -> None:
        return None

    async def stream_chat(self, **kwargs):
        yield {"type": "message_chunk", "content": "ok"}

    async def close(self) -> None:
        return None


@pytest.mark.asyncio
async def test_chat_endpoint_streams_through_harness(monkeypatch) -> None:
    monkeypatch.setenv("HARNESS_PRIMARY_DECISION_LOOP_ENABLED", "false")
    monkeypatch.setattr(agent_api, "ChatWorkflow", FakeWorkflow)
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

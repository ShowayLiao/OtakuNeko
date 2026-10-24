"""Acceptance tests for authenticated chat persistence and anonymous isolation."""

from datetime import datetime, timezone

import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials
from sqlmodel import select

from app.api import deps
from app.api.v1 import agent as agent_api
from app.harness.model_types import ModelCallResult
from app.models.agent_run import AgentRun, AgentRunEvent
from app.schemas.agent import ChatRequest, Message
from app.schemas.user import UserRead


class FakeGateway:
    def __init__(self, **kwargs):
        self.model = kwargs["model"]

    async def infer(self, **kwargs):
        messages = kwargs.get("messages") or []
        content = next(
            (
                str(message.get("content"))
                for message in reversed(messages)
                if isinstance(message, dict) and message.get("role") == "user"
            ),
            "answer",
        )
        return ModelCallResult(
            provider="fake",
            model=self.model,
            operation="infer",
            status="completed",
            decision={
                "schema_version": "v1",
                "decision_id": f"answer-{content}",
                "action": "respond",
                "content": f"answer:{content}",
            },
        )

    async def close(self):
        return None


def _user(user_id: int) -> UserRead:
    return UserRead(
        id=user_id,
        username=f"user-{user_id}",
        created_at=datetime.now(timezone.utc),
    )


def _request(content: str, thread_id: str = "shared-thread") -> ChatRequest:
    return ChatRequest(
        model="test-model",
        thread_id=thread_id,
        messages=[Message(role="user", content=content)],
    )


async def _consume(response) -> str:
    return "".join([chunk async for chunk in response.body_iterator])


@pytest.mark.asyncio
async def test_invalid_optional_bearer_is_rejected(monkeypatch, db_session) -> None:
    monkeypatch.setattr(deps, "decode_access_token", lambda token: None)
    credentials = HTTPAuthorizationCredentials(
        scheme="Bearer",
        credentials="expired-token",
    )

    with pytest.raises(HTTPException) as exc_info:
        await deps.get_optional_user(credentials, db_session)

    assert exc_info.value.status_code == 401


@pytest.mark.asyncio
async def test_authenticated_chat_is_persisted_and_scoped_by_user(
    monkeypatch,
    db_session,
) -> None:
    monkeypatch.setattr(agent_api, "OpenAIModelGateway", FakeGateway)

    first_response = await agent_api.chat_endpoint(
        _request("from-user-1"),
        x_api_key="test-key",
        x_base_url="https://api.openai.com/v1",
        user=_user(1),
        db=db_session,
    )
    second_response = await agent_api.chat_endpoint(
        _request("from-user-2"),
        x_api_key="test-key",
        x_base_url="https://api.openai.com/v1",
        user=_user(2),
        db=db_session,
    )

    first_body = await _consume(first_response)
    second_body = await _consume(second_response)

    assert '"durable": true' in first_body
    assert '"durable": true' in second_body

    runs = (await db_session.exec(select(AgentRun))).all()
    assert {run.user_id for run in runs} == {1, 2}
    assert {run.thread_id for run in runs} == {
        "user:1:thread:shared-thread",
        "user:2:thread:shared-thread",
    }

    user_one_history = await agent_api.get_chat_history(
        thread_id="shared-thread",
        user=_user(1),
        db=db_session,
    )
    user_two_history = await agent_api.get_chat_history(
        thread_id="shared-thread",
        user=_user(2),
        db=db_session,
    )

    assert user_one_history["messages"] == [
        {"role": "user", "content": "from-user-1"},
        {"role": "assistant", "content": "answer:from-user-1"},
    ]
    assert user_two_history["messages"] == [
        {"role": "user", "content": "from-user-2"},
        {"role": "assistant", "content": "answer:from-user-2"},
    ]


@pytest.mark.asyncio
async def test_anonymous_chat_is_ephemeral_and_not_persisted(
    monkeypatch,
    db_session,
) -> None:
    monkeypatch.setattr(agent_api, "OpenAIModelGateway", FakeGateway)
    before_runs = (await db_session.exec(select(AgentRun))).all()
    before_events = (await db_session.exec(select(AgentRunEvent))).all()

    response = await agent_api.chat_endpoint(
        _request("anonymous"),
        x_api_key="test-key",
        x_base_url="https://api.openai.com/v1",
        user=None,
        db=db_session,
    )
    body = await _consume(response)

    after_runs = (await db_session.exec(select(AgentRun))).all()
    after_events = (await db_session.exec(select(AgentRunEvent))).all()

    assert '"durable": false' in body
    assert after_runs == before_runs
    assert after_events == before_events

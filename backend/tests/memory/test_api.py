"""Authenticated API wiring tests for durable memory."""

from __future__ import annotations

from datetime import datetime
import os

import httpx
import pytest

os.environ["DEBUG"] = "false"

from app.api.v1 import agent as agent_api
from app.api.v1.memory import delete_user_memory
from app.api.deps import get_current_user
from app.db.database import get_session
from app.main import app
from app.memory.sql_repository import SqlMemoryRepository
from app.schemas.agent import ChatRequest, Message
from app.schemas.user import UserRead


def _user(user_id: int = 1) -> UserRead:
    return UserRead(
        id=user_id,
        username=f"user-{user_id}",
        created_at=datetime(2026, 1, 1),
    )


class _FakeWorkflow:
    def __init__(self, **kwargs):
        self.checkpointer = object()
        self.memory = None

    async def _ensure_checkpointer(self) -> None:
        return None

    async def stream_chat(self, **kwargs):
        yield {"type": "message_chunk", "content": "ok"}

    async def close(self) -> None:
        return None


class _CapturingMemoryService:
    instances: list["_CapturingMemoryService"] = []

    def __init__(self, repository, **kwargs):
        self.repository = repository
        self.checkpointer = None
        self.extractions: list[tuple[str, int | None]] = []
        self.instances.append(self)

    async def extract_and_store_facts(
        self, thread_id: str, user_id: int | None = None
    ) -> int:
        self.extractions.append((thread_id, user_id))
        return 0


@pytest.mark.asyncio
async def test_delete_user_memory_removes_only_authenticated_users_rows(
    db_session,
):
    repo = SqlMemoryRepository(db_session)
    await repo.put_fact("shared", "a", "alice", 0.5, "test", user_id=1)
    await repo.put_fact("shared", "b", "bob", 0.5, "test", user_id=2)

    response = await delete_user_memory(
        kind=None,
        user=_user(1),
        db=db_session,
    )

    assert response["deleted"] == 1
    assert await repo.get_facts("shared", user_id=1) == []
    assert len(await repo.get_facts("shared", user_id=2)) == 1


@pytest.mark.asyncio
async def test_authenticated_chat_uses_request_scoped_sql_repository(
    monkeypatch, db_session
):
    monkeypatch.setenv("HARNESS_PRIMARY_DECISION_LOOP_ENABLED", "false")
    _CapturingMemoryService.instances.clear()
    monkeypatch.setattr(agent_api, "ChatWorkflow", _FakeWorkflow)
    monkeypatch.setattr(
        agent_api, "MemoryServiceImpl", _CapturingMemoryService
    )
    request = ChatRequest(
        model="test-model",
        messages=[Message(role="user", content="hello")],
        thread_id="thread-1",
    )

    response = await agent_api.chat_endpoint(
        request,
        x_api_key="test-key",
        x_base_url="https://api.openai.com/v1",
        user=_user(7),
        db=db_session,
    )
    body = "".join([chunk async for chunk in response.body_iterator])

    assert "event: error" not in body
    assert len(_CapturingMemoryService.instances) == 1
    service = _CapturingMemoryService.instances[0]
    assert isinstance(service.repository, SqlMemoryRepository)
    assert service.extractions == [("user:7:thread:thread-1", 7)]


@pytest.mark.asyncio
async def test_anonymous_chat_does_not_construct_durable_memory(
    monkeypatch, db_session
):
    monkeypatch.setenv("HARNESS_PRIMARY_DECISION_LOOP_ENABLED", "false")
    _CapturingMemoryService.instances.clear()
    monkeypatch.setattr(agent_api, "ChatWorkflow", _FakeWorkflow)
    monkeypatch.setattr(
        agent_api, "MemoryServiceImpl", _CapturingMemoryService
    )
    request = ChatRequest(
        model="test-model",
        messages=[Message(role="user", content="hello")],
    )

    response = await agent_api.chat_endpoint(
        request,
        x_api_key="test-key",
        x_base_url="https://api.openai.com/v1",
        user=None,
        db=db_session,
    )
    body = "".join([chunk async for chunk in response.body_iterator])

    assert "event: error" not in body
    assert _CapturingMemoryService.instances == []


@pytest.mark.asyncio
async def test_memory_delete_route_uses_authenticated_owner(db_session):
    repo = SqlMemoryRepository(db_session)
    await repo.put_fact("shared", "a", "alice", 0.5, "test", user_id=1)
    await repo.put_fact("shared", "b", "bob", 0.5, "test", user_id=2)
    await repo.commit()

    async def override_user():
        return _user(1)

    async def override_session():
        yield db_session

    app.dependency_overrides[get_current_user] = override_user
    app.dependency_overrides[get_session] = override_session
    try:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://test",
        ) as client:
            response = await client.delete("/api/v1/memory?kind=episodic")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["deleted"] == 1
    assert await repo.get_facts("shared", user_id=1) == []
    assert len(await repo.get_facts("shared", user_id=2)) == 1


@pytest.mark.asyncio
async def test_memory_delete_route_rejects_invalid_kind(db_session):
    async def override_user():
        return _user(1)

    async def override_session():
        yield db_session

    app.dependency_overrides[get_current_user] = override_user
    app.dependency_overrides[get_session] = override_session
    try:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://test",
        ) as client:
            response = await client.delete("/api/v1/memory?kind=invalid")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 422

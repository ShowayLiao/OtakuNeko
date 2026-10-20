"""End-to-end HTTP certification for Anime action identity boundaries."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path
from typing import Any

import pytest
from app.core.security import create_access_token
from app.harness.model_types import ModelCallResult
from app.models.agent_run import AgentInvocation, AgentRun
from app.models.agent_trace import AgentTraceModel
from app.models.user import User
from app.schemas.user import UserRead
from httpx import AsyncClient
from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select


_CHAT_PATH = "/api/v1/chat"
_RUN_PATH = "/api/v1/runs/{run_id}"
_EVENTS_PATH = "/api/v1/runs/{run_id}/events"
_TRACE_PATH = "/api/v1/trace/{trace_id}"
_SYNTHETIC_API_KEY = "synthetic-test-key"
_HTTP_EVIDENCE = (
    Path(__file__).resolve().parents[2]
    / ".runtime/capability-contracts/anime-http.json"
)


@dataclass
class _GatewayCalls:
    constructors: int = 0
    inferences: int = 0


def _gateway_for(capability: str, calls: _GatewayCalls) -> type:
    """Return a deterministic structured gateway with no provider client."""

    class _FakeGateway:
        def __init__(self, **kwargs: Any) -> None:
            calls.constructors += 1
            self.model = str(kwargs["model"])
            self._proposed = False

        async def infer(self, **kwargs: Any) -> ModelCallResult:
            del kwargs
            calls.inferences += 1
            if not self._proposed:
                self._proposed = True
                decision = {
                    "schema_version": "v1",
                    "decision_id": f"synthetic-invoke-{calls.inferences}",
                    "action": "invoke",
                    "capability": capability,
                    "capability_version": "v1",
                    "arguments": {},
                }
            else:
                decision = {
                    "schema_version": "v1",
                    "decision_id": f"synthetic-respond-{calls.inferences}",
                    "action": "respond",
                    "content": "Synthetic safe completion.",
                }
            return ModelCallResult(
                provider="synthetic",
                model=self.model,
                operation="infer",
                status="completed",
                decision=decision,
                text=json.dumps(decision),
            )

        async def close(self) -> None:
            return None

    return _FakeGateway


async def _create_user(
    db: AsyncSession, username: str, *, bangumi_name: str | None = None
) -> UserRead:
    user = User(username=username, bangumi_name=bangumi_name)
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return UserRead.model_validate(user)


def _token(user_id: int) -> str:
    return create_access_token({"sub": str(user_id)})


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _sse_frames(body: str) -> list[dict[str, Any]]:
    frames: list[dict[str, Any]] = []
    for raw_frame in body.split("\n\n"):
        if not raw_frame.strip():
            continue
        frame: dict[str, Any] = {"data": {}}
        data_lines: list[str] = []
        for line in raw_frame.splitlines():
            if line.startswith("event:"):
                frame["event"] = line.removeprefix("event:").strip()
            elif line.startswith("id:"):
                frame["id"] = line.removeprefix("id:").strip()
            elif line.startswith("data:"):
                data_lines.append(line.removeprefix("data:").strip())
        if data_lines:
            frame["data"] = json.loads("\n".join(data_lines))
        frames.append(frame)
    return frames


async def _chat(client: AsyncClient, *, token: str | None, content: str):
    headers = {"X-Api-Key": _SYNTHETIC_API_KEY}
    if token is not None:
        headers.update(_auth(token))
    return await client.post(
        _CHAT_PATH,
        headers=headers,
        json={
            "model": "synthetic-model",
            "messages": [{"role": "user", "content": content}],
        },
    )


async def _row_count(db: AsyncSession, model: type[Any]) -> int:
    result = await db.execute(select(func.count()).select_from(model))
    return int(result.scalar_one())


async def _assert_successful_run_and_trace(
    client: AsyncClient,
    db: AsyncSession,
    *,
    owner: UserRead,
    token: str,
    response,
    evidence: list[dict[str, Any]],
) -> str:
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    frames = _sse_frames(response.text)
    terminal = [frame for frame in frames if frame.get("event") == "run_completed"]
    assert terminal
    run_id = terminal[-1]["data"]["run_id"]
    assert all(frame["data"]["durable"] is True for frame in frames)

    run = await client.get(_RUN_PATH.format(run_id=run_id), headers=_auth(token))
    assert run.status_code == 200
    assert run.json()["status"] == "succeeded"

    events_response = await client.get(
        _EVENTS_PATH.format(run_id=run_id), headers=_auth(token)
    )
    assert events_response.status_code == 200
    events = events_response.json()["events"]
    assert events[-1]["event_type"] == "run.succeeded"
    tool_ends = [event for event in events if event["event_type"] == "tool_call_end"]
    assert len(tool_ends) == 1
    assert tool_ends[0]["payload"]["status"] == "succeeded"
    invocation_id = tool_ends[0]["invocation_id"]
    invocation_result = await db.execute(
        select(AgentInvocation).where(
            AgentInvocation.run_id == run_id,
            AgentInvocation.invocation_id == invocation_id,
        )
    )
    invocation = invocation_result.scalar_one()
    assert invocation.status == "succeeded"

    trace = await client.get(_TRACE_PATH.format(trace_id=run_id), headers=_auth(token))
    assert trace.status_code == 200
    assert trace.json()["trace_id"] == run_id
    assert trace.json()["user_id"] == owner.id
    trace_events = [
        event for step in trace.json()["steps"] for event in step.get("events", [])
    ]
    assert any(event["event_type"] == "tool_call_end" for event in trace_events)
    evidence.append(
        {
            "run_id": run_id,
            "principal_id": owner.id,
            "run_status": run.json()["status"],
            "invocation_status": invocation.status,
            "canonical_event_types": [event["event_type"] for event in events],
            "trace_event_types": [event["event_type"] for event in trace_events],
            "trace_owner_matches": trace.json()["user_id"] == owner.id,
        }
    )
    _HTTP_EVIDENCE.parent.mkdir(parents=True, exist_ok=True)
    _HTTP_EVIDENCE.write_text(
        json.dumps(
            {
                "source": "real HTTP/JWT + synthetic provider dependencies",
                "runs": evidence,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return run_id


@pytest.mark.api
@pytest.mark.integration
async def test_authenticated_linked_bangumi_reads_use_each_owners_binding(
    api_client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch,
) -> None:
    from app.api.v1 import agent as agent_api
    from app.core.config import settings
    from app.capabilities import anime as anime_capability

    _HTTP_EVIDENCE.unlink(missing_ok=True)
    evidence: list[dict[str, Any]] = []

    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setattr(settings, "HARNESS_CHECKPOINT_ADAPTER", "disabled")

    owner_a = await _create_user(
        db_session, "anime-http-owner-a", bangumi_name="linked-anime-a"
    )
    owner_b = await _create_user(
        db_session, "anime-http-owner-b", bangumi_name="linked-anime-b"
    )
    token_a = _token(owner_a.id)
    token_b = _token(owner_b.id)
    calls = _GatewayCalls()
    monkeypatch.setattr(
        agent_api, "OpenAIModelGateway", _gateway_for("get_bangumi_user_info", calls)
    )

    bangumi_calls: list[str] = []

    async def _get_user_info(username: str) -> dict[str, Any]:
        bangumi_calls.append(username)
        return {"id": len(bangumi_calls), "username": username}

    monkeypatch.setattr(anime_capability, "get_bangumi_user_info", _get_user_info)

    response_a = await _chat(
        api_client, token=token_a, content="Read my linked public profile."
    )
    run_a = await _assert_successful_run_and_trace(
        api_client,
        db_session,
        owner=owner_a,
        token=token_a,
        response=response_a,
        evidence=evidence,
    )
    assert bangumi_calls == ["linked-anime-a"]

    model_calls_before_foreign_read = calls.inferences
    bangumi_calls_before_foreign_read = list(bangumi_calls)
    foreign_run = await api_client.get(
        _RUN_PATH.format(run_id=run_a), headers=_auth(token_b)
    )
    foreign_trace = await api_client.get(
        _TRACE_PATH.format(trace_id=run_a), headers=_auth(token_b)
    )
    assert foreign_run.status_code == 404
    assert foreign_trace.status_code == 404
    assert calls.inferences == model_calls_before_foreign_read
    assert bangumi_calls == bangumi_calls_before_foreign_read

    response_b = await _chat(
        api_client, token=token_b, content="Read my linked public profile."
    )
    await _assert_successful_run_and_trace(
        api_client,
        db_session,
        owner=owner_b,
        token=token_b,
        response=response_b,
        evidence=evidence,
    )
    assert bangumi_calls == ["linked-anime-a", "linked-anime-b"]
    assert calls.constructors == 2


@pytest.mark.api
@pytest.mark.integration
async def test_anonymous_public_calendar_is_ephemeral_and_keeps_root_array(
    api_client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch,
) -> None:
    from app.api.v1 import agent as agent_api
    from app.core.config import settings
    from app.capabilities import anime as anime_capability

    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setattr(settings, "HARNESS_CHECKPOINT_ADAPTER", "disabled")
    calls = _GatewayCalls()
    monkeypatch.setattr(
        agent_api, "OpenAIModelGateway", _gateway_for("get_bangumi_calendar", calls)
    )
    calendar = [
        {
            "weekday": {"en": "Monday"},
            "items": [{"id": 41001, "name": "Synthetic public anime"}],
        }
    ]
    dependency_calls = 0

    async def _get_calendar() -> list[dict[str, Any]]:
        nonlocal dependency_calls
        dependency_calls += 1
        return calendar

    monkeypatch.setattr(anime_capability, "get_bangumi_calendar", _get_calendar)

    runs_before = await _row_count(db_session, AgentRun)
    traces_before = await _row_count(db_session, AgentTraceModel)
    response = await _chat(
        api_client, token=None, content="Show the public broadcast calendar."
    )
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    frames = _sse_frames(response.text)
    terminal = [frame for frame in frames if frame.get("event") == "run_completed"]
    assert terminal
    assert all(frame["data"]["durable"] is False for frame in frames)
    tool_ends = [frame for frame in frames if frame.get("event") == "tool_call_end"]
    assert len(tool_ends) == 1
    assert tool_ends[0]["data"]["status"] == "succeeded"
    assert tool_ends[0]["data"]["output"]["calendar"] == calendar
    assert dependency_calls == 1
    assert calls.constructors == 1
    assert calls.inferences == 2
    assert await _row_count(db_session, AgentRun) == runs_before
    assert await _row_count(db_session, AgentTraceModel) == traces_before


@pytest.mark.api
@pytest.mark.integration
async def test_anonymous_linked_profile_proposal_is_denied_before_bangumi_call(
    api_client: AsyncClient,
    monkeypatch,
) -> None:
    from app.api.v1 import agent as agent_api
    from app.core.config import settings
    from app.capabilities import anime as anime_capability

    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setattr(settings, "HARNESS_CHECKPOINT_ADAPTER", "disabled")
    calls = _GatewayCalls()
    monkeypatch.setattr(
        agent_api, "OpenAIModelGateway", _gateway_for("get_bangumi_user_info", calls)
    )
    bangumi_calls: list[str] = []

    async def _get_user_info(username: str) -> dict[str, Any]:
        bangumi_calls.append(username)
        return {"id": 1, "username": username}

    monkeypatch.setattr(anime_capability, "get_bangumi_user_info", _get_user_info)

    response = await _chat(
        api_client, token=None, content="Read the linked account profile."
    )
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    frames = _sse_frames(response.text)
    tool_ends = [frame for frame in frames if frame.get("event") == "tool_call_end"]
    failed = [frame for frame in frames if frame.get("event") == "run_failed"]
    assert len(tool_ends) == 1
    assert tool_ends[0]["data"]["status"] == "denied"
    assert tool_ends[0]["data"]["error_code"] == "unauthorized"
    assert failed
    assert all(frame["data"]["durable"] is False for frame in frames)
    assert bangumi_calls == []
    assert calls.constructors == 1
    assert calls.inferences == 1


@pytest.mark.api
@pytest.mark.integration
async def test_invalid_bearers_stop_before_gateway_or_anime_dependency(
    api_client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch,
) -> None:
    from app.api.v1 import agent as agent_api
    from app.capabilities import anime as anime_capability

    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    calls = _GatewayCalls()
    monkeypatch.setattr(
        agent_api, "OpenAIModelGateway", _gateway_for("get_bangumi_user_info", calls)
    )
    bangumi_calls: list[str] = []

    async def _get_user_info(username: str) -> dict[str, Any]:
        bangumi_calls.append(username)
        return {"id": 1, "username": username}

    monkeypatch.setattr(anime_capability, "get_bangumi_user_info", _get_user_info)

    owner = await _create_user(
        db_session, "anime-http-expired-token-owner", bangumi_name="linked-anime"
    )
    expired = create_access_token(
        {"sub": str(owner.id)}, expires_delta=timedelta(seconds=-1)
    )
    unknown = create_access_token({"sub": "99999999"})
    for token in ("invalid.synthetic.token", expired, unknown):
        response = await _chat(
            api_client, token=token, content="Read my linked public profile."
        )
        assert response.status_code == 401
        assert response.json() == {"detail": "Invalid authentication credentials"}
        assert response.headers.get("www-authenticate") == "Bearer"

    assert calls.constructors == 0
    assert calls.inferences == 0
    assert bangumi_calls == []


@pytest.mark.api
@pytest.mark.integration
async def test_authenticated_user_without_binding_returns_not_configured(
    api_client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch,
) -> None:
    from app.api.v1 import agent as agent_api
    from app.core.config import settings
    from app.capabilities import anime as anime_capability

    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setattr(settings, "HARNESS_CHECKPOINT_ADAPTER", "disabled")
    calls = _GatewayCalls()
    monkeypatch.setattr(
        agent_api, "OpenAIModelGateway", _gateway_for("get_bangumi_user_info", calls)
    )
    bangumi_calls: list[str] = []

    async def _get_user_info(username: str) -> dict[str, Any]:
        bangumi_calls.append(username)
        return {"id": 1, "username": username}

    monkeypatch.setattr(anime_capability, "get_bangumi_user_info", _get_user_info)
    owner = await _create_user(db_session, "anime-http-unlinked-owner")

    response = await _chat(
        api_client,
        token=_token(owner.id),
        content="Read my linked public profile.",
    )
    assert response.status_code == 200
    frames = _sse_frames(response.text)
    tool_ends = [frame for frame in frames if frame.get("event") == "tool_call_end"]
    assert len(tool_ends) == 1
    assert tool_ends[0]["data"]["status"] == "denied"
    assert tool_ends[0]["data"]["error_code"] == "not_configured"
    assert bangumi_calls == []
    assert calls.constructors == 1
    assert calls.inferences == 1

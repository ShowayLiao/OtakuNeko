"""HTTP contracts for chat, durable Runs, replay events, and trace queries."""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from typing import Any, ClassVar, Literal

import pytest
from app.core.security import create_access_token
from app.harness.contracts import RunEvent
from app.harness.model_types import ModelCallResult
from app.harness.persistence.event_store import EventStore
from app.harness.persistence.run_store import RunStore
from app.models.agent_run import AgentRun
from app.models.user import User
from app.schemas.user import UserRead
from app.trace import AgentTrace, TraceStep
from app.trace.sql_store import SqlTraceStore
from fastapi import FastAPI
from fastapi.routing import APIRoute
from httpx import AsyncClient, Response
from sqlalchemy.ext.asyncio import AsyncSession


_RUN_PATH = "/api/v1/runs/{run_id}"
_EVENTS_PATH = "/api/v1/runs/{run_id}/events"
_CANCEL_PATH = "/api/v1/runs/{run_id}/cancel"
_TRACE_PATH = "/api/v1/trace/{trace_id}"
_TRACE_LIST_PATH = "/api/v1/trace/"
_CHAT_PATH = "/api/v1/chat"


class _FakeGateway:
    """Replace only the external model gateway; keep the HTTP Runtime and SQL live."""

    result_status: ClassVar[Literal["completed", "failed"]] = "completed"

    def __init__(self, **kwargs: Any) -> None:
        self.model = kwargs["model"]

    async def infer(self, **kwargs: Any) -> ModelCallResult:
        messages = kwargs.get("messages") or []
        user_text = next(
            (
                str(message.get("content", ""))
                for message in reversed(messages)
                if isinstance(message, dict) and message.get("role") == "user"
            ),
            "",
        )
        decision = {
            "schema_version": "v1",
            "decision_id": "http-contract-decision",
            "action": "respond",
            "content": f"answer:{user_text}",
        }
        return ModelCallResult(
            provider="fake",
            model=self.model,
            operation="infer",
            status=self.result_status,
            decision=decision if self.result_status == "completed" else None,
            text=json.dumps(decision) if self.result_status == "completed" else "",
            error_code="permanent" if self.result_status == "failed" else None,
        )

    async def close(self) -> None:
        return None


async def _create_user(db: AsyncSession, username: str) -> UserRead:
    user = User(username=username)
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return UserRead.model_validate(user)


def _token(user_id: int) -> str:
    return create_access_token({"sub": str(user_id)})


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _record_response(
    record_property, name: str, method: str, path: str, response: Response
) -> None:
    """Keep failure evidence useful while omitting request inputs and headers."""
    body = response.json()
    detail = body.get("detail") if isinstance(body, dict) else None
    if isinstance(detail, list):
        detail = [
            {key: item[key] for key in ("loc", "msg", "type") if key in item}
            for item in detail
            if isinstance(item, dict)
        ]
    record_property(
        name,
        json.dumps(
            {
                "method": method,
                "path": path,
                "status": response.status_code,
                "body": {"detail": detail},
            },
            ensure_ascii=False,
            sort_keys=True,
        ),
    )


async def _seed_run(
    db: AsyncSession,
    *,
    run_id: str,
    user_id: int,
    status: str = "queued",
    thread_id: str | None = None,
) -> None:
    await RunStore(db).create(
        AgentRun(
            run_id=run_id,
            user_id=user_id,
            thread_id=thread_id or f"user:{user_id}:thread:contract-thread",
            status=status,
            goal_hash="safe-goal-hash",
            model="contract-model",
        )
    )


async def _seed_event(
    db: AsyncSession,
    *,
    run_id: str,
    sequence: int,
    event_type: str,
    payload: dict[str, Any] | None = None,
) -> None:
    await EventStore(db).append(
        RunEvent(
            run_id=run_id,
            sequence=sequence,
            event_type=event_type,
            payload=payload or {},
        )
    )


async def _seed_trace(
    db: AsyncSession,
    *,
    trace_id: str,
    user_id: int,
    status: str = "completed",
) -> AgentTrace:
    trace = AgentTrace(
        trace_id=trace_id,
        run_id=f"run-{trace_id}",
        user_id=user_id,
        agent_name="contract-agent",
        goal="safe trace goal",
        status=status,
        steps=[
            TraceStep(
                step_index=0,
                step_label="decision",
                agent_name="contract-agent",
                status="completed",
            )
        ],
    )
    await SqlTraceStore(db).record(trace)
    return trace


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


@pytest.mark.api
@pytest.mark.integration
async def test_real_app_and_fixture_publish_same_target_openapi(
    api_app: FastAPI,
) -> None:
    from app.main import app as production_app

    expected = {
        _CHAT_PATH: {"post"},
        _RUN_PATH: {"get"},
        _EVENTS_PATH: {"get"},
        _CANCEL_PATH: {"post"},
        _TRACE_PATH: {"get"},
        _TRACE_LIST_PATH: {"get"},
    }
    production_openapi = production_app.openapi()["paths"]
    fixture_openapi = api_app.openapi()["paths"]
    for path, methods in expected.items():
        assert methods <= production_openapi[path].keys()
        assert methods <= fixture_openapi[path].keys()
        for method in methods:
            production_operation = production_openapi[path][method]
            fixture_operation = fixture_openapi[path][method]
            for key in ("parameters", "requestBody", "responses", "security"):
                assert production_operation.get(key) == fixture_operation.get(key)

    production_routes = {
        (route.path, method.lower())
        for route in production_app.routes
        if isinstance(route, APIRoute)
        for method in route.methods
    }
    fixture_routes = {
        (route.path, method.lower())
        for route in api_app.routes
        if isinstance(route, APIRoute)
        for method in route.methods
    }
    assert {
        (path, method) for path, methods in expected.items() for method in methods
    } <= production_routes
    assert {
        (path, method) for path, methods in expected.items() for method in methods
    } <= fixture_routes


@pytest.mark.api
@pytest.mark.integration
async def test_run_http_contract_is_authenticated_owner_scoped_and_replayable(
    api_client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch,
    record_property,
) -> None:
    from app.core.config import settings

    owner = await _create_user(db_session, "run-contract-owner")
    other = await _create_user(db_session, "run-contract-other")
    await _seed_run(db_session, run_id="run-owned", user_id=owner.id)
    await _seed_run(db_session, run_id="run-foreign", user_id=owner.id)
    await _seed_event(
        db_session,
        run_id="run-owned",
        sequence=1,
        event_type="run.started",
        payload={"source": "test"},
    )
    await _seed_event(
        db_session,
        run_id="run-owned",
        sequence=2,
        event_type="run.progress",
        payload={"step": 1},
    )

    no_auth = await api_client.get(_RUN_PATH.format(run_id="run-owned"))
    _record_response(record_property, "run_missing_auth", "GET", _RUN_PATH, no_auth)
    assert no_auth.status_code == 401
    assert no_auth.json() == {"detail": "Not authenticated"}
    assert no_auth.headers.get("www-authenticate") == "Bearer"

    bad_auth = await api_client.get(
        _RUN_PATH.format(run_id="run-owned"),
        headers=_auth("invalid.synthetic.token"),
    )
    assert bad_auth.status_code == 401
    assert bad_auth.json() == {"detail": "无法验证凭据"}
    assert bad_auth.headers.get("www-authenticate") == "Bearer"

    owner_response = await api_client.get(
        _RUN_PATH.format(run_id="run-owned"), headers=_auth(_token(owner.id))
    )
    assert owner_response.status_code == 200
    assert owner_response.headers["content-type"].startswith("application/json")
    run_body = owner_response.json()
    assert set(run_body) == {
        "run_id",
        "status",
        "last_sequence",
        "error_code",
        "started_at",
        "finished_at",
    }
    assert run_body == {
        "run_id": "run-owned",
        "status": "queued",
        "last_sequence": 2,
        "error_code": None,
        "started_at": None,
        "finished_at": None,
    }

    foreign = await api_client.get(
        _RUN_PATH.format(run_id="run-owned"), headers=_auth(_token(other.id))
    )
    missing = await api_client.get(
        _RUN_PATH.format(run_id="run-missing"), headers=_auth(_token(owner.id))
    )
    _record_response(record_property, "run_foreign_404", "GET", _RUN_PATH, foreign)
    _record_response(record_property, "run_missing_404", "GET", _RUN_PATH, missing)
    assert foreign.status_code == missing.status_code == 404
    assert foreign.json() == missing.json() == {"detail": "Run not found"}

    wrong_thread = await api_client.get(
        _RUN_PATH.format(run_id="run-owned"),
        params={"thread_id": "wrong-thread"},
        headers=_auth(_token(owner.id)),
    )
    assert wrong_thread.status_code == 404
    assert wrong_thread.json() == missing.json()

    no_events_auth = await api_client.get(_EVENTS_PATH.format(run_id="run-owned"))
    assert no_events_auth.status_code == 401
    assert no_events_auth.json() == {"detail": "Not authenticated"}
    assert no_events_auth.headers.get("www-authenticate") == "Bearer"
    events_url = _EVENTS_PATH.format(run_id="run-owned")
    fallback = await api_client.get(
        events_url,
        headers={**_auth(_token(owner.id)), "Last-Event-ID": "1"},
    )
    assert fallback.status_code == 200
    assert fallback.headers["content-type"].startswith("application/json")
    fallback_body = fallback.json()
    assert set(fallback_body) == {"run_id", "after", "events"}
    assert fallback_body["after"] == 1
    assert [event["sequence"] for event in fallback_body["events"]] == [2]
    event = fallback_body["events"][0]
    assert set(event) == {
        "event_id",
        "run_id",
        "sequence",
        "event_type",
        "invocation_id",
        "payload",
        "occurred_at",
    }
    assert event["run_id"] == "run-owned"
    assert event["event_type"] == "run.progress"
    assert event["payload"] == {"step": 1}
    assert isinstance(event["event_id"], str)
    assert datetime.fromisoformat(event["occurred_at"])

    precedence = await api_client.get(
        events_url,
        params={"after": "0"},
        headers={**_auth(_token(owner.id)), "Last-Event-ID": "1"},
    )
    assert precedence.status_code == 200
    assert precedence.json()["after"] == 0
    assert [item["sequence"] for item in precedence.json()["events"]] == [1, 2]

    invalid_cursor = await api_client.get(
        events_url,
        params={"after": "bad"},
        headers=_auth(_token(owner.id)),
    )
    _record_response(
        record_property, "event_cursor_400", "GET", _EVENTS_PATH, invalid_cursor
    )
    assert invalid_cursor.status_code == 400
    assert invalid_cursor.json() == {"detail": "invalid event cursor"}
    out_of_range = await api_client.get(
        events_url,
        params={"after": "1000000001"},
        headers=_auth(_token(owner.id)),
    )
    assert out_of_range.status_code == 400
    assert out_of_range.json() == {"detail": "event cursor out of range"}

    foreign_events = await api_client.get(
        _EVENTS_PATH.format(run_id="run-owned"), headers=_auth(_token(other.id))
    )
    missing_events = await api_client.get(
        _EVENTS_PATH.format(run_id="run-missing"), headers=_auth(_token(owner.id))
    )
    assert foreign_events.status_code == missing_events.status_code == 404
    assert foreign_events.json() == missing_events.json() == {"detail": "Run not found"}

    cancel_auth = await api_client.post(_CANCEL_PATH.format(run_id="run-foreign"))
    assert cancel_auth.status_code == 401
    assert cancel_auth.json() == {"detail": "Not authenticated"}
    assert cancel_auth.headers.get("www-authenticate") == "Bearer"
    cancel_foreign = await api_client.post(
        _CANCEL_PATH.format(run_id="run-foreign"), headers=_auth(_token(other.id))
    )
    cancel_missing = await api_client.post(
        _CANCEL_PATH.format(run_id="run-missing"), headers=_auth(_token(owner.id))
    )
    assert cancel_foreign.status_code == cancel_missing.status_code == 404
    assert cancel_foreign.json() == cancel_missing.json() == {"detail": "Run not found"}

    monkeypatch.setattr(settings, "HARNESS_CHECKPOINT_ADAPTER", "disabled")
    cancelled = await api_client.post(
        _CANCEL_PATH.format(run_id="run-foreign"), headers=_auth(_token(owner.id))
    )
    assert cancelled.status_code == 200
    assert cancelled.headers["content-type"].startswith("application/json")
    assert cancelled.json() == {
        "run_id": "run-foreign",
        "status": "queued",
        "error_code": None,
        "cancellation_requested": True,
        "last_sequence": 1,
    }
    persisted_cancel = await api_client.get(
        _EVENTS_PATH.format(run_id="run-foreign"), headers=_auth(_token(owner.id))
    )
    assert persisted_cancel.json()["events"][0]["event_type"] == "run.cancel_requested"


@pytest.mark.api
@pytest.mark.integration
async def test_trace_http_schema_is_authenticated_owner_scoped_and_validated(
    api_client: AsyncClient,
    db_session: AsyncSession,
    record_property,
) -> None:
    owner = await _create_user(db_session, "trace-contract-owner")
    other = await _create_user(db_session, "trace-contract-other")
    await _seed_trace(db_session, trace_id="trace-owned", user_id=owner.id)
    await _seed_trace(db_session, trace_id="trace-foreign", user_id=other.id)

    missing_auth = await api_client.get(_TRACE_PATH.format(trace_id="trace-owned"))
    _record_response(
        record_property, "trace_missing_auth", "GET", _TRACE_PATH, missing_auth
    )
    assert missing_auth.status_code == 401
    assert missing_auth.json() == {"detail": "Not authenticated"}
    assert missing_auth.headers.get("www-authenticate") == "Bearer"

    invalid_auth = await api_client.get(
        _TRACE_PATH.format(trace_id="trace-owned"),
        headers=_auth("invalid.synthetic.token"),
    )
    assert invalid_auth.status_code == 401
    assert invalid_auth.json() == {"detail": "无法验证凭据"}
    assert invalid_auth.headers.get("www-authenticate") == "Bearer"

    owned = await api_client.get(
        _TRACE_PATH.format(trace_id="trace-owned"), headers=_auth(_token(owner.id))
    )
    assert owned.status_code == 200
    assert owned.headers["content-type"].startswith("application/json")
    trace = owned.json()
    assert trace["schema_version"] == 2
    assert trace["trace_id"] == "trace-owned"
    assert trace["user_id"] == owner.id
    assert trace["status"] == "completed"
    assert isinstance(trace["started_at"], str)
    assert isinstance(trace["steps"], list)
    assert trace["steps"][0]["step_index"] == 0

    foreign = await api_client.get(
        _TRACE_PATH.format(trace_id="trace-owned"), headers=_auth(_token(other.id))
    )
    missing = await api_client.get(
        _TRACE_PATH.format(trace_id="trace-missing"), headers=_auth(_token(owner.id))
    )
    _record_response(record_property, "trace_foreign_404", "GET", _TRACE_PATH, foreign)
    assert foreign.status_code == missing.status_code == 404
    assert foreign.json() == missing.json() == {"detail": "Trace not found"}

    list_missing_auth = await api_client.get(_TRACE_LIST_PATH)
    assert list_missing_auth.status_code == 401
    assert list_missing_auth.json() == {"detail": "Not authenticated"}
    assert list_missing_auth.headers.get("www-authenticate") == "Bearer"

    listed = await api_client.get(
        _TRACE_LIST_PATH,
        params={"user_id": other.id, "status": "completed", "limit": 10},
        headers=_auth(_token(owner.id)),
    )
    assert listed.status_code == 200
    assert listed.headers["content-type"].startswith("application/json")
    assert set(listed.json()) == {"traces", "total", "next_cursor"}
    assert listed.json()["total"] == 1
    assert [item["trace_id"] for item in listed.json()["traces"]] == ["trace-owned"]
    assert listed.json()["next_cursor"] is None

    for name, params, field in (
        ("trace_invalid_limit_422", {"limit": 0}, "limit"),
        ("trace_invalid_status_422", {"status": "unknown"}, "status"),
        (
            "trace_invalid_datetime_422",
            {"started_after": "not-a-datetime"},
            "started_after",
        ),
    ):
        invalid = await api_client.get(
            _TRACE_LIST_PATH,
            params=params,
            headers=_auth(_token(owner.id)),
        )
        _record_response(record_property, name, "GET", _TRACE_LIST_PATH, invalid)
        assert invalid.status_code == 422
        details = invalid.json()["detail"]
        assert isinstance(details, list)
        assert any(field in item.get("loc", []) for item in details)


@pytest.mark.api
@pytest.mark.integration
async def test_chat_http_validation_auth_byok_and_sse_runtime_persistence(
    api_client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch,
    record_property,
) -> None:
    from app.api.v1 import agent as agent_api

    owner = await _create_user(db_session, "chat-contract-owner")
    owner_token = _token(owner.id)
    monkeypatch.setattr(agent_api, "OpenAIModelGateway", _FakeGateway)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    missing_model = await api_client.post(
        _CHAT_PATH,
        json={"messages": [{"role": "user", "content": "hello"}]},
    )
    assert missing_model.status_code == 422
    empty_messages = await api_client.post(
        _CHAT_PATH,
        json={"model": "contract-model", "messages": []},
    )
    assert empty_messages.status_code == 422
    wrong_message_shape = await api_client.post(
        _CHAT_PATH,
        json={"model": "contract-model", "messages": [{"content": "hello"}]},
    )
    assert wrong_message_shape.status_code == 422

    missing_key = await api_client.post(
        _CHAT_PATH,
        json={
            "model": "contract-model",
            "messages": [{"role": "user", "content": "hello"}],
        },
    )
    _record_response(
        record_property, "chat_missing_byok_401", "POST", _CHAT_PATH, missing_key
    )
    assert missing_key.status_code == 401
    assert missing_key.json() == {"detail": "Missing API Key"}

    expired_token = create_access_token(
        {"sub": str(owner.id)}, expires_delta=timedelta(seconds=-1)
    )
    unknown_subject = create_access_token({"sub": "99999999"})
    for token in ("invalid.synthetic.token", expired_token, unknown_subject):
        rejected = await api_client.post(
            _CHAT_PATH,
            headers={**_auth(token), "X-Api-Key": "synthetic-test-key"},
            json={
                "model": "contract-model",
                "messages": [{"role": "user", "content": "hello"}],
            },
        )
        assert rejected.status_code == 401
        assert rejected.json() == {"detail": "Invalid authentication credentials"}
        assert rejected.headers.get("www-authenticate") == "Bearer"

    payload = {
        "model": "contract-model",
        "thread_id": "http-contract-thread",
        "messages": [{"role": "user", "content": "hello through http"}],
    }
    success = await api_client.post(
        _CHAT_PATH,
        headers={**_auth(owner_token), "X-Api-Key": "synthetic-test-key"},
        json=payload,
    )
    assert success.status_code == 200
    assert success.headers["content-type"].startswith("text/event-stream")
    frames = _sse_frames(success.text)
    chunks = [frame for frame in frames if frame.get("event") == "message_chunk"]
    completed = [frame for frame in frames if frame.get("event") == "run_completed"]
    assert chunks and chunks[0]["data"]["content"] == "answer:hello through http"
    assert completed
    run_id = completed[-1]["data"]["run_id"]
    assert isinstance(run_id, str) and run_id
    assert all(frame["data"]["durable"] is True for frame in frames)
    assert all(frame["data"]["run_id"] == run_id for frame in frames)
    assert all(isinstance(frame.get("id"), str) for frame in frames)

    persisted_run = await api_client.get(
        _RUN_PATH.format(run_id=run_id), headers=_auth(owner_token)
    )
    assert persisted_run.status_code == 200
    assert persisted_run.json()["status"] == "succeeded"
    persisted_events = await api_client.get(
        _EVENTS_PATH.format(run_id=run_id), headers=_auth(owner_token)
    )
    assert persisted_events.status_code == 200
    canonical_events = persisted_events.json()["events"]
    last_sequence = persisted_run.json()["last_sequence"]
    assert [event["sequence"] for event in canonical_events] == list(
        range(1, last_sequence + 1)
    )
    assert int(frames[-1]["id"]) == last_sequence
    assert {int(frame["id"]) for frame in frames} <= {
        event["sequence"] for event in canonical_events
    }
    assert persisted_events.json()["events"][-1]["event_type"] == "run.succeeded"

    anonymous = await api_client.post(
        _CHAT_PATH,
        headers={"X-Api-Key": "synthetic-test-key"},
        json={
            "model": "contract-model",
            "messages": [{"role": "user", "content": "anonymous"}],
        },
    )
    assert anonymous.status_code == 200
    assert anonymous.headers["content-type"].startswith("text/event-stream")
    anonymous_frames = _sse_frames(anonymous.text)
    assert anonymous_frames
    assert all(frame["data"]["durable"] is False for frame in anonymous_frames)
    anonymous_run_id = anonymous_frames[-1]["data"].get("run_id")
    assert isinstance(anonymous_run_id, str) and anonymous_run_id
    absent_run = await api_client.get(
        _RUN_PATH.format(run_id=anonymous_run_id), headers=_auth(owner_token)
    )
    assert absent_run.status_code == 404

    _FakeGateway.result_status = "failed"
    try:
        failed = await api_client.post(
            _CHAT_PATH,
            headers={**_auth(owner_token), "X-Api-Key": "synthetic-test-key"},
            json={
                "model": "contract-model",
                "messages": [{"role": "user", "content": "provider failure path"}],
            },
        )
    finally:
        _FakeGateway.result_status = "completed"
    assert failed.status_code == 200
    assert failed.headers["content-type"].startswith("text/event-stream")
    failed_frames = _sse_frames(failed.text)
    failure_events = [
        frame for frame in failed_frames if frame.get("event") == "run_failed"
    ]
    assert failure_events
    assert failure_events[-1]["data"].get("error_code") == "provider_error"
    failed_run_id = failure_events[-1]["data"]["run_id"]
    assert all(frame["data"]["durable"] is True for frame in failed_frames)
    failed_projection = await api_client.get(
        _RUN_PATH.format(run_id=failed_run_id), headers=_auth(owner_token)
    )
    assert failed_projection.status_code == 200
    assert failed_projection.json()["status"] == "failed"
    assert failed_projection.json()["error_code"] == "provider_error"

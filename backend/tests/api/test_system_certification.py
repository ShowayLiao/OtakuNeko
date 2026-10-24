"""HTTP/JWT certification for the single System capability action."""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timedelta
from typing import Any
from uuid import uuid4

import pytest
from sqlmodel import col, select

from app.capabilities.system import SystemCapability
from app.core.security import create_access_token
from app.harness.authority import RUNTIME_OWNED_FIELDS
from app.harness.model_types import ModelCallResult
from app.models import Collection, Schedule, Subject, User
from app.models.agent_run import AgentInvocation, AgentRun, AgentRunEvent
from app.models.agent_trace import AgentTraceModel, TraceEventModel
from tests.capabilities.contracts.system_support import capture_application_logs

_ACTION = "get_current_time"
_DESCRIPTOR_NAME = "current_time"
_CHAT_PATH = "/api/v1/chat"
_TERMINAL_SSE_EVENTS = {
    "run_completed",
    "run_failed",
    "run_cancelled",
    "run_timeout",
}
_RAW_ERROR = "system-private-provider-diagnostic-sentinel"
_AUTHORITY_SENTINEL = "system-private-authority-sentinel"
_OUTPUT_FIELDS = {
    "current_time",
    "current_date",
    "current_year",
    "current_month",
    "current_day",
    "current_hour",
    "current_minute",
    "current_second",
    "weekday",
    "weekday_cn",
    "timestamp",
    "timezone",
}
_WEEKDAY_NAMES = (
    "星期一",
    "星期二",
    "星期三",
    "星期四",
    "星期五",
    "星期六",
    "星期日",
)
_VALID_PAYLOAD = {
    "current_time": "2026-01-02 03:04:05",
    "current_date": "2026-01-02",
    "current_year": 2026,
    "current_month": 1,
    "current_day": 2,
    "current_hour": 3,
    "current_minute": 4,
    "current_second": 5,
    "weekday": 4,
    "weekday_cn": "星期五",
    "timestamp": 1767323045.0,
    "timezone": "本地时间",
}
_AUTHORITY_VALUES = {
    "user_id": 999999,
    "principal_id": 999999,
    "tenant_id": "system-private-tenant",
    "role": "system-private-role",
    "scope": ["system-private-scope"],
    "db": "system-private-db-handle",
    "token": _AUTHORITY_SENTINEL,
    "approval_state": {"approved": True},
}


class _GatewayCalls:
    def __init__(self) -> None:
        self.decision_ids: list[str] = []
        self.requests: list[str] = []


def _gateway(arguments: dict[str, Any], calls: _GatewayCalls):
    class _FakeGateway:
        def __init__(self, **kwargs: Any) -> None:
            self.model = str(kwargs["model"])
            self.proposed = False

        async def infer(self, **kwargs: Any) -> ModelCallResult:
            calls.requests.append(repr(kwargs))
            decision_id = f"system-{uuid4().hex}"
            calls.decision_ids.append(decision_id)
            if not self.proposed:
                self.proposed = True
                decision = {
                    "schema_version": "v1",
                    "decision_id": decision_id,
                    "action": "invoke",
                    "capability": _ACTION,
                    "capability_version": "v1",
                    "arguments": arguments,
                }
            else:
                decision = {
                    "schema_version": "v1",
                    "decision_id": decision_id,
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


def _frames(text: str) -> list[dict[str, Any]]:
    frames: list[dict[str, Any]] = []
    event_type = "message"
    data_lines: list[str] = []

    def flush() -> None:
        nonlocal event_type, data_lines
        if data_lines:
            frame = json.loads("\n".join(data_lines))
            frame["_event_type"] = event_type
            frames.append(frame)
        event_type = "message"
        data_lines = []

    for line in text.replace("\r\n", "\n").splitlines():
        if not line:
            flush()
        elif line.startswith("event:"):
            event_type = line.removeprefix("event:").strip()
        elif line.startswith("data:"):
            data_lines.append(line.removeprefix("data:").strip())
    flush()
    return frames


def _auth(user_id: int | None) -> dict[str, str]:
    assert user_id is not None
    return {
        "Authorization": f"Bearer {create_access_token({'sub': str(user_id)})}",
        "X-Api-Key": "synthetic-test-key",
    }


def _prepare_runtime(monkeypatch) -> None:
    from app.core.config import settings

    monkeypatch.setattr(settings, "HARNESS_CHECKPOINT_ADAPTER", "disabled")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)


async def _seed_users(db) -> tuple[User, User]:
    suffix = uuid4().hex[:12]
    users = [User(username=f"system-owner-{label}-{suffix}") for label in ("a", "b")]
    db.add_all(users)
    await db.commit()
    return users[0], users[1]


async def _business_snapshot(db) -> dict[str, tuple[int, str]]:
    """Hash all row fields without putting user/business values in test output."""
    result: dict[str, tuple[int, str]] = {}
    for model in (User, Subject, Collection, Schedule):
        rows = (
            (
                await db.execute(
                    select(model)
                    .order_by(col(model.id))
                    .execution_options(populate_existing=True)
                )
            )
            .scalars()
            .all()
        )
        payload = [row.model_dump(mode="json") for row in rows]
        encoded = json.dumps(
            payload,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        result[str(model.__tablename__)] = (
            len(rows),
            hashlib.sha256(encoded).hexdigest(),
        )
    return result


async def _agent_row_counts(db) -> dict[str, int]:
    counts: dict[str, int] = {}
    for model in (
        AgentRun,
        AgentInvocation,
        AgentRunEvent,
        AgentTraceModel,
        TraceEventModel,
    ):
        counts[str(model.__tablename__)] = len(
            (await db.execute(select(model))).scalars().all()
        )
    return counts


async def _chat(
    api_client,
    monkeypatch,
    user: User | None,
    arguments: dict[str, Any],
) -> tuple[list[dict[str, Any]], dict[str, Any] | None, _GatewayCalls]:
    from app.api.v1 import agent as agent_api

    calls = _GatewayCalls()
    monkeypatch.setattr(agent_api, "OpenAIModelGateway", _gateway(arguments, calls))
    headers = (
        _auth(user.id) if user is not None else {"X-Api-Key": "synthetic-test-key"}
    )
    response = await api_client.post(
        _CHAT_PATH,
        headers=headers,
        json={
            "model": "synthetic-model",
            "messages": [{"role": "user", "content": "What time is it?"}],
        },
    )
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    frames = _frames(response.text)
    tool_ends = [
        frame for frame in frames if frame.get("_event_type") == "tool_call_end"
    ]
    assert len(tool_ends) <= 1
    assert len(calls.decision_ids) == len(set(calls.decision_ids))
    return frames, tool_ends[0] if tool_ends else None, calls


def _run_id(frames: list[dict[str, Any]]) -> str:
    run_ids = {frame.get("run_id") for frame in frames if frame.get("run_id")}
    assert len(run_ids) == 1
    return str(run_ids.pop())


def _terminal_frames(frames: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        frame for frame in frames if frame.get("_event_type") in _TERMINAL_SSE_EVENTS
    ]


async def _assert_run_records(
    api_client,
    db,
    *,
    frames: list[dict[str, Any]],
    owner: User,
    other_owner: User,
    action: str,
    expected_run_status: str,
    expected_sse_terminal: str,
    expected_invocation_status: str,
    expected_invocation_code: str | None = None,
) -> tuple[str, dict[str, Any], dict[str, Any]]:
    run_id = _run_id(frames)
    terminal_frames = _terminal_frames(frames)
    assert [frame["_event_type"] for frame in terminal_frames] == [
        expected_sse_terminal
    ]
    assert all(frame.get("durable") is True for frame in frames)
    assert {frame.get("run_id") for frame in terminal_frames} == {run_id}

    headers = _auth(owner.id)
    run_response = await api_client.get(f"/api/v1/runs/{run_id}", headers=headers)
    assert run_response.status_code == 200
    run_body = run_response.json()
    assert run_body["run_id"] == run_id
    assert run_body["status"] == expected_run_status

    run_row = (
        await db.execute(select(AgentRun).where(AgentRun.run_id == run_id))
    ).scalar_one()
    assert run_row.user_id == owner.id
    assert run_row.status == expected_run_status

    invocations = (
        (
            await db.execute(
                select(AgentInvocation).where(AgentInvocation.run_id == run_id)
            )
        )
        .scalars()
        .all()
    )
    assert len(invocations) == 1
    invocation = invocations[0]
    assert invocation.capability == action
    assert invocation.status == expected_invocation_status

    tool_end_frames = [
        frame for frame in frames if frame.get("_event_type") == "tool_call_end"
    ]
    assert len(tool_end_frames) == 1
    tool_end = tool_end_frames[0]
    assert tool_end["capability"] == action
    assert tool_end["invocation_id"] == invocation.invocation_id
    assert tool_end["run_id"] == run_id
    if expected_invocation_code is not None:
        assert tool_end["error_code"] == expected_invocation_code

    event_response = await api_client.get(
        f"/api/v1/runs/{run_id}/events", headers=headers
    )
    assert event_response.status_code == 200
    event_body = event_response.json()
    assert event_body["run_id"] == run_id
    events = event_body["events"]
    sequences = [event["sequence"] for event in events]
    assert sequences == sorted(set(sequences))
    event_rows = (
        (
            await db.execute(
                select(AgentRunEvent)
                .where(AgentRunEvent.run_id == run_id)
                .order_by(col(AgentRunEvent.sequence))
            )
        )
        .scalars()
        .all()
    )
    assert [event["event_id"] for event in events] == [
        event.event_id for event in event_rows
    ]
    persisted_tool_ends = [
        event for event in events if event["event_type"] == "tool_call_end"
    ]
    assert len(persisted_tool_ends) == 1
    assert persisted_tool_ends[0]["invocation_id"] == invocation.invocation_id
    assert persisted_tool_ends[0]["payload"]["status"] == tool_end["status"]
    persisted_terminals = [
        event
        for event in events
        if event["event_type"]
        in {"run.succeeded", "run.failed", "run.cancelled", "run.abandoned"}
    ]
    expected_persisted_terminal = (
        "run.succeeded" if expected_run_status == "succeeded" else "run.failed"
    )
    assert [event["event_type"] for event in persisted_terminals] == [
        expected_persisted_terminal
    ]
    assert persisted_terminals[0]["run_id"] == run_id

    trace_response = await api_client.get(f"/api/v1/trace/{run_id}", headers=headers)
    assert trace_response.status_code == 200
    trace = trace_response.json()
    assert trace["trace_id"] == run_id
    assert trace["run_id"] == run_id
    assert trace["user_id"] == owner.id
    assert trace["status"] == (
        "completed" if expected_run_status == "succeeded" else "failed"
    )
    trace_row = (
        await db.execute(
            select(AgentTraceModel).where(AgentTraceModel.trace_id == run_id)
        )
    ).scalar_one()
    assert trace_row.user_id == owner.id
    assert trace_row.status == trace["status"]
    assert json.loads(trace_row.headers_json or "{}")["run_id"] == run_id
    trace_step_rows = (
        (
            await db.execute(
                select(TraceEventModel)
                .where(TraceEventModel.trace_id == run_id)
                .order_by(col(TraceEventModel.step_index))
            )
        )
        .scalars()
        .all()
    )
    assert trace_step_rows
    trace_events = [event for step in trace["steps"] for event in step["events"]]
    trace_tool_ends = [
        event for event in trace_events if event["event_type"] == "tool_call_end"
    ]
    assert len(trace_tool_ends) == 1
    assert trace_tool_ends[0]["run_id"] == run_id
    assert trace_tool_ends[0]["invocation_id"] == invocation.invocation_id
    assert trace_tool_ends[0]["status"] == (
        "completed" if expected_run_status == "succeeded" else "failed"
    )
    assert any(event["event_type"] == "model_call" for event in trace_events)
    stored_trace_steps = [json.loads(row.step_json or "{}") for row in trace_step_rows]
    stored_trace_events = [
        event for step in stored_trace_steps for event in step.get("events", [])
    ]
    assert any(
        event.get("invocation_id") == invocation.invocation_id
        and event.get("event_type") == "tool_call_end"
        for event in stored_trace_events
    )

    other_headers = _auth(other_owner.id)
    for path in (
        f"/api/v1/runs/{run_id}",
        f"/api/v1/runs/{run_id}/events",
        f"/api/v1/trace/{run_id}",
    ):
        assert (await api_client.get(path, headers=other_headers)).status_code == 404
    return run_id, tool_end, trace


@pytest.mark.api
@pytest.mark.integration
async def test_system_http_certification_uses_runtime_and_returns_typed_time(
    api_client, db_session, monkeypatch
):
    from app.capabilities.factory import build_capability_registry

    _prepare_runtime(monkeypatch)
    owners = await _seed_users(db_session)
    registry = build_capability_registry()
    registered = registry.find_action(_ACTION)
    assert registered is not None
    capability, descriptor = registered
    assert capability.name == "system"
    assert descriptor.name == _DESCRIPTOR_NAME
    assert descriptor.public_name == _ACTION
    assert descriptor.version == "v1"
    assert descriptor.is_side_effect is False
    assert descriptor.approval_required is False
    assert descriptor.idempotency_mode == "none"
    assert descriptor.requires_auth is False
    assert descriptor.input_schema == {
        "type": "object",
        "properties": {},
        "additionalProperties": False,
    }
    assert descriptor.output_schema["additionalProperties"] is False
    assert set(descriptor.output_schema["required"]) == _OUTPUT_FIELDS
    business_before = await _business_snapshot(db_session)

    before = datetime.now()
    frames, tool_end, gateway_calls = await _chat(
        api_client, monkeypatch, owners[0], {}
    )
    after = datetime.now()
    assert tool_end is not None
    assert tool_end["status"] == "succeeded"
    assert tool_end["error_code"] is None
    assert tool_end["retryable"] is False
    output = tool_end["output"]
    assert output["success"] is True
    run_id = _run_id(frames)
    assert output["run_id"] == run_id
    assert set(output) == _OUTPUT_FIELDS | {
        "success",
        "run_id",
        "decision_id",
        "invocation_id",
        "trace_id",
        "latency_ms",
    }
    assert not set(output) & RUNTIME_OWNED_FIELDS
    observed = datetime.strptime(output["current_time"], "%Y-%m-%d %H:%M:%S")
    assert before.replace(microsecond=0) <= observed <= after
    assert abs(datetime.fromtimestamp(output["timestamp"]) - observed) <= timedelta(
        seconds=1
    )
    assert output["current_date"] == observed.strftime("%Y-%m-%d")
    assert output["current_year"] == observed.year
    assert output["current_month"] == observed.month
    assert output["current_day"] == observed.day
    assert output["current_hour"] == observed.hour
    assert output["current_minute"] == observed.minute
    assert output["current_second"] == observed.second
    assert output["weekday"] == observed.weekday()
    assert output["weekday_cn"] == _WEEKDAY_NAMES[observed.weekday()]
    assert output["timezone"] == "本地时间"
    assert isinstance(output["timestamp"], (int, float))
    assert not isinstance(output["timestamp"], bool)
    assert output["timestamp"] > 0

    await _assert_run_records(
        api_client,
        db_session,
        frames=frames,
        owner=owners[0],
        other_owner=owners[1],
        action=_ACTION,
        expected_run_status="succeeded",
        expected_sse_terminal="run_completed",
        expected_invocation_status="succeeded",
    )
    assert await _business_snapshot(db_session) == business_before
    assert len(gateway_calls.decision_ids) >= 2


@pytest.mark.api
@pytest.mark.integration
@pytest.mark.parametrize("field", sorted(RUNTIME_OWNED_FIELDS))
async def test_system_http_rejects_model_supplied_authority_fields(
    api_client, db_session, monkeypatch, caplog, field: str
):
    _prepare_runtime(monkeypatch)
    owners = await _seed_users(db_session)
    business_before = await _business_snapshot(db_session)
    assert set(_AUTHORITY_VALUES) == RUNTIME_OWNED_FIELDS
    forged = {field: _AUTHORITY_VALUES[field]}

    with capture_application_logs(caplog):
        logging.getLogger("app.harness.runtime").debug(
            "system-certification-log-capture-probe"
        )
        frames, tool_end, _ = await _chat(api_client, monkeypatch, owners[1], forged)
        assert "system-certification-log-capture-probe" in caplog.text

    assert tool_end is None
    assert not any(
        frame.get("_event_type") in {"tool_call_start", "tool_call_end"}
        for frame in frames
    )
    assert [
        frame["_event_type"]
        for frame in frames
        if frame.get("_event_type") in _TERMINAL_SSE_EVENTS
    ] == ["run_failed"]
    run_id = _run_id(frames)
    run_row = (
        await db_session.execute(select(AgentRun).where(AgentRun.run_id == run_id))
    ).scalar_one()
    assert run_row.user_id == owners[1].id
    assert run_row.status == "failed"
    invocations = (
        (
            await db_session.execute(
                select(AgentInvocation).where(AgentInvocation.run_id == run_id)
            )
        )
        .scalars()
        .all()
    )
    assert invocations == []
    event_response = await api_client.get(
        f"/api/v1/runs/{run_id}/events", headers=_auth(owners[1].id)
    )
    assert event_response.status_code == 200
    terminal_events = [
        event
        for event in event_response.json()["events"]
        if event["event_type"] in {"run.succeeded", "run.failed", "run.cancelled"}
    ]
    assert [event["event_type"] for event in terminal_events] == ["run.failed"]
    trace_response = await api_client.get(
        f"/api/v1/trace/{run_id}", headers=_auth(owners[1].id)
    )
    assert trace_response.status_code == 200
    trace = trace_response.json()
    assert trace["run_id"] == run_id
    assert trace["user_id"] == owners[1].id
    assert trace["status"] == "failed"
    assert (
        await api_client.get(f"/api/v1/trace/{run_id}", headers=_auth(owners[0].id))
    ).status_code == 404

    serialized = json.dumps(
        {
            "frames": frames,
            "events": event_response.json(),
            "trace": trace,
        },
        ensure_ascii=False,
        allow_nan=False,
    )
    authority_sentinels = (
        _AUTHORITY_SENTINEL,
        "system-private-tenant",
        "system-private-role",
        "system-private-scope",
        "system-private-db-handle",
    )
    for sentinel in authority_sentinels:
        assert sentinel not in serialized
        assert sentinel not in caplog.text
        assert all(sentinel not in repr(item.exc_info) for item in caplog.records)
    assert await _business_snapshot(db_session) == business_before


@pytest.mark.api
@pytest.mark.integration
async def test_system_http_unknown_arguments_return_structured_denial(
    api_client, db_session, monkeypatch
):
    _prepare_runtime(monkeypatch)
    owners = await _seed_users(db_session)
    business_before = await _business_snapshot(db_session)
    arguments = {
        "host": "https://untrusted.synthetic.invalid",
        "timezone": "UTC",
        "password": _RAW_ERROR,
    }

    frames, tool_end, _ = await _chat(api_client, monkeypatch, owners[0], arguments)

    assert tool_end is not None
    assert tool_end["status"] == "denied"
    assert tool_end["error_code"] == "invalid_request"
    assert tool_end["retryable"] is False
    output = tool_end["output"]
    assert set(output) == {"error_type", "message"}
    assert output["error_type"] == "invalid_request"
    assert (
        output["message"]
        == "Capability arguments did not match the declared input contract"
    )
    assert not {"host", "timezone", "password"} & set(output)
    assert not set(output) & RUNTIME_OWNED_FIELDS
    run_id, failure_event, trace = await _assert_run_records(
        api_client,
        db_session,
        frames=frames,
        owner=owners[0],
        other_owner=owners[1],
        action=_ACTION,
        expected_run_status="failed",
        expected_sse_terminal="run_failed",
        expected_invocation_status="denied",
        expected_invocation_code="invalid_request",
    )
    serialized = json.dumps(
        {"frames": frames, "failure": failure_event, "trace": trace},
        ensure_ascii=False,
        allow_nan=False,
    )
    assert _RAW_ERROR not in serialized
    assert "untrusted.synthetic.invalid" not in serialized
    event_response = await api_client.get(
        f"/api/v1/runs/{run_id}/events", headers=_auth(owners[0].id)
    )
    assert _RAW_ERROR not in event_response.text
    assert "untrusted.synthetic.invalid" not in event_response.text
    assert await _business_snapshot(db_session) == business_before


@pytest.mark.api
@pytest.mark.integration
async def test_system_http_exception_is_contained_and_not_persisted(
    api_client, db_session, monkeypatch, caplog
):
    from app.capabilities import system as system_capability

    class _RaisingDateTime(datetime):
        @classmethod
        def now(cls, tz: Any = None) -> "_RaisingDateTime":
            raise RuntimeError(_RAW_ERROR)

    _prepare_runtime(monkeypatch)
    owners = await _seed_users(db_session)
    monkeypatch.setattr(system_capability, "datetime", _RaisingDateTime)
    business_before = await _business_snapshot(db_session)

    with capture_application_logs(caplog):
        logging.getLogger("app.harness.runtime").error(
            "system-certification-log-capture-probe"
        )
        frames, tool_end, calls = await _chat(api_client, monkeypatch, owners[0], {})
        assert "system-certification-log-capture-probe" in caplog.text

    assert tool_end is not None
    assert tool_end["status"] == "failed"
    assert tool_end["error_code"] == "internal"
    assert tool_end["retryable"] is False
    assert tool_end["output"]["error_type"] == "internal"
    assert tool_end["output"]["message"] == "Capability execution failed"
    run_id, failure_event, trace = await _assert_run_records(
        api_client,
        db_session,
        frames=frames,
        owner=owners[0],
        other_owner=owners[1],
        action=_ACTION,
        expected_run_status="failed",
        expected_sse_terminal="run_failed",
        expected_invocation_status="failed",
        expected_invocation_code="internal",
    )
    serialized = json.dumps(
        {
            "frames": frames,
            "failure": failure_event,
            "trace": trace,
            "gateway_requests": calls.requests,
        },
        ensure_ascii=False,
        allow_nan=False,
    )
    assert _RAW_ERROR not in serialized
    assert _RAW_ERROR not in caplog.text
    assert all(_RAW_ERROR not in repr(item.exc_info) for item in caplog.records)
    event_response = await api_client.get(
        f"/api/v1/runs/{run_id}/events", headers=_auth(owners[0].id)
    )
    assert _RAW_ERROR not in event_response.text
    assert await _business_snapshot(db_session) == business_before


@pytest.mark.api
@pytest.mark.integration
async def test_system_http_output_contract_violation_is_contained(
    api_client, db_session, monkeypatch
):
    _prepare_runtime(monkeypatch)
    owners = await _seed_users(db_session)

    async def leaky_execute(self, action: str, **kwargs: Any) -> dict[str, Any]:
        return {"success": True, **_VALID_PAYLOAD, "leaked": _RAW_ERROR}

    monkeypatch.setattr(SystemCapability, "execute", leaky_execute)
    business_before = await _business_snapshot(db_session)

    frames, tool_end, _ = await _chat(api_client, monkeypatch, owners[0], {})

    assert tool_end is not None
    assert tool_end["status"] == "failed"
    assert tool_end["error_code"] == "invalid_output"
    assert tool_end["retryable"] is False
    assert tool_end["output"]["error_type"] == "invalid_output"
    assert (
        tool_end["output"]["message"]
        == "Capability output did not match its declared contract"
    )
    run_id, failure_event, trace = await _assert_run_records(
        api_client,
        db_session,
        frames=frames,
        owner=owners[0],
        other_owner=owners[1],
        action=_ACTION,
        expected_run_status="failed",
        expected_sse_terminal="run_failed",
        expected_invocation_status="failed",
        expected_invocation_code="invalid_output",
    )
    serialized = json.dumps(
        {"frames": frames, "failure": failure_event, "trace": trace},
        ensure_ascii=False,
        allow_nan=False,
    )
    assert _RAW_ERROR not in serialized
    event_response = await api_client.get(
        f"/api/v1/runs/{run_id}/events", headers=_auth(owners[0].id)
    )
    assert _RAW_ERROR not in event_response.text
    assert await _business_snapshot(db_session) == business_before


@pytest.mark.api
@pytest.mark.integration
async def test_system_http_identity_boundaries_and_anonymous_ephemerality(
    api_client, db_session, monkeypatch
):
    _prepare_runtime(monkeypatch)
    await _seed_users(db_session)
    business_before = await _business_snapshot(db_session)
    counts_before = await _agent_row_counts(db_session)

    payload = {
        "model": "synthetic-model",
        "messages": [{"role": "user", "content": "What time is it?"}],
    }
    missing_key = await api_client.post(_CHAT_PATH, json=payload)
    assert missing_key.status_code == 401
    invalid_token = await api_client.post(
        _CHAT_PATH,
        headers={
            "Authorization": "Bearer not-a-token",
            "X-Api-Key": "synthetic-test-key",
        },
        json=payload,
    )
    assert invalid_token.status_code == 401

    frames, tool_end, calls = await _chat(api_client, monkeypatch, None, {})
    assert tool_end is not None
    assert tool_end["status"] == "succeeded"
    assert tool_end["error_code"] is None
    assert tool_end["output"]["success"] is True
    assert tool_end["output"]["current_date"]
    assert not set(tool_end["output"]) & RUNTIME_OWNED_FIELDS
    assert all(frame.get("durable") is False for frame in frames)
    assert await _agent_row_counts(db_session) == counts_before
    assert await _business_snapshot(db_session) == business_before
    assert len(calls.decision_ids) >= 2


def test_system_action_is_not_exposed_over_mcp():
    from app.mcp_server.entry import build_exposure, build_registry

    registry = build_registry()
    assert registry.find_action(_ACTION) is not None
    assert "system" not in build_exposure(registry).capabilities

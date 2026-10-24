"""HTTP/JWT certification for the three existing Media read actions."""

from __future__ import annotations

import copy
import hashlib
import json
import logging
from typing import Any
from uuid import uuid4

import pytest
from sqlmodel import col, select

from app.core.security import create_access_token
from app.harness.model_types import ModelCallResult
from app.models import Collection, Schedule, Subject, User
from app.models.agent_run import AgentInvocation, AgentRun, AgentRunEvent
from app.models.agent_trace import AgentTraceModel, TraceEventModel
from app.schemas.rss import RssRule, TorrentParams


_ACTIONS = ("library_status", "list_rss_feeds", "list_rss_rules")
_QB_ACTIONS = ("list_rss_feeds", "list_rss_rules")
_REST_PATHS = ("/api/v1/rss/list", "/api/v1/rss/rules")
_CHAT_PATH = "/api/v1/chat"
_TERMINAL_SSE_EVENTS = {
    "run_completed",
    "run_failed",
    "run_cancelled",
    "run_timeout",
}
_RAW_ERROR = "synthetic-qb-provider-diagnostic-private"
_SYNTHETIC_HOST = "https://qb.synthetic.invalid"
_SYNTHETIC_USERNAME = "synthetic-qb-user"
_SYNTHETIC_PASSWORD = "synthetic-qb-password-private"


def _feed_state() -> dict[str, dict[str, str]]:
    return {
        "shared-feed": {
            "uid": "shared-feed-uid",
            "url": "https://feeds.example.invalid/anime.xml",
        }
    }


def _rule_state() -> dict[str, dict[str, Any]]:
    rule = RssRule(
        affectedFeeds=["https://feeds.example.invalid/anime.xml"],
        assignedCategory="anime",
        enabled=True,
        episodeFilter="",
        ignoreDays=0,
        mustContain="anime",
        mustNotContain="",
        previouslyMatchedEpisodes=[],
        priority=1,
        savePath="synthetic-download-root",
        smartFilter=False,
        torrentParams=TorrentParams(
            category="anime",
            download_limit=0,
            download_path="synthetic-download-root",
            inactive_seeding_time_limit=0,
            operating_mode="auto",
            ratio_limit=-1,
            save_path="synthetic-download-root",
            seeding_time_limit=0,
            share_limit_action="default",
            skip_checking=False,
            ssl_certificate="",
            ssl_dh_params="",
            ssl_private_key="",
            tags=[],
            upload_limit=0,
        ),
        useRegex=False,
    )
    return {"synthetic-rule": rule.model_dump(mode="json", by_alias=True)}


class _RecordingQBClient:
    """SDK-boundary fake; the production QBService still owns conversion/errors."""

    def __init__(self, factory: _RecordingQBFactory) -> None:
        self.factory = factory
        self.calls: list[str] = []

    def _record(self, operation: str) -> None:
        self.calls.append(operation)
        self.factory.calls.append(operation)
        if self.factory.failure and self.factory.failure[0] == operation:
            raise self.factory.failure[1]

    def auth_log_in(self) -> None:
        self._record("auth_log_in")

    def rss_items(self) -> dict[str, dict[str, str]]:
        self._record("rss_items")
        return copy.deepcopy(self.factory.feeds)

    def rss_rules(self) -> dict[str, dict[str, Any]]:
        self._record("rss_rules")
        return copy.deepcopy(self.factory.rules)

    def _write(self, operation: str) -> None:
        self.calls.append(operation)
        self.factory.calls.append(operation)
        self.factory.write_calls.append(operation)
        raise AssertionError("A Media read attempted a qBittorrent write")

    def rss_add_feed(self, *args: Any, **kwargs: Any) -> None:
        self._write("rss_add_feed")

    def rss_remove_item(self, *args: Any, **kwargs: Any) -> None:
        self._write("rss_remove_item")

    def rss_set_rule(self, *args: Any, **kwargs: Any) -> None:
        self._write("rss_set_rule")

    def rss_remove_rule(self, *args: Any, **kwargs: Any) -> None:
        self._write("rss_remove_rule")


class _RecordingQBFactory:
    def __init__(self) -> None:
        self.feeds = _feed_state()
        self.rules = _rule_state()
        self.failure: tuple[str, Exception] | None = None
        self.clients: list[_RecordingQBClient] = []
        self.configurations: list[dict[str, Any]] = []
        self.calls: list[str] = []
        self.write_calls: list[str] = []

    def __call__(self, **kwargs: Any) -> _RecordingQBClient:
        self.configurations.append(dict(kwargs))
        client = _RecordingQBClient(self)
        self.clients.append(client)
        return client

    def assert_read_only(self) -> None:
        assert self.write_calls == []
        assert set(self.calls) <= {"auth_log_in", "rss_items", "rss_rules"}


class _GatewayCalls:
    def __init__(self) -> None:
        self.decision_ids: list[str] = []
        self.requests: list[str] = []


def _gateway(action: str, arguments: dict[str, Any], calls: _GatewayCalls):
    class _FakeGateway:
        def __init__(self, **kwargs: Any) -> None:
            self.model = str(kwargs["model"])
            self.proposed = False

        async def infer(self, **kwargs: Any) -> ModelCallResult:
            calls.requests.append(repr(kwargs))
            decision_id = f"media-read-{uuid4().hex}"
            calls.decision_ids.append(decision_id)
            if not self.proposed:
                self.proposed = True
                decision = {
                    "schema_version": "v1",
                    "decision_id": decision_id,
                    "action": "invoke",
                    "capability": action,
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


def _configure_qb(monkeypatch, factory: _RecordingQBFactory) -> None:
    import qbittorrentapi

    from app.core.config import settings

    monkeypatch.setattr(settings, "ENABLE_QB_PROXY", True)
    monkeypatch.setattr(settings, "QB_HOST", _SYNTHETIC_HOST)
    monkeypatch.setattr(settings, "QB_USERNAME", _SYNTHETIC_USERNAME)
    monkeypatch.setattr(settings, "QB_PASSWORD", _SYNTHETIC_PASSWORD)
    monkeypatch.setattr(settings, "QB_ALLOWED_USER_IDS", "")
    monkeypatch.setattr(qbittorrentapi, "Client", factory)


async def _seed_users(db) -> tuple[User, User]:
    suffix = uuid4().hex[:12]
    users = [
        User(username=f"media-read-owner-{label}-{suffix}") for label in ("a", "b")
    ]
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


async def _chat(
    api_client,
    monkeypatch,
    user: User,
    action: str,
    arguments: dict[str, Any],
) -> tuple[list[dict[str, Any]], dict[str, Any] | None, _GatewayCalls]:
    from app.api.v1 import agent as agent_api

    calls = _GatewayCalls()
    monkeypatch.setattr(
        agent_api, "OpenAIModelGateway", _gateway(action, arguments, calls)
    )
    response = await api_client.post(
        _CHAT_PATH,
        headers=_auth(user.id),
        json={
            "model": "synthetic-model",
            "messages": [{"role": "user", "content": "Read the RSS configuration."}],
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
    terminal_frames = [
        frame for frame in frames if frame.get("_event_type") in _TERMINAL_SSE_EVENTS
    ]
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


def _assert_rule_has_no_torrent_params(output: dict[str, Any]) -> None:
    assert "rules" in output
    rules = output["rules"]
    assert set(rules) == {"synthetic-rule"}
    rule = rules["synthetic-rule"]
    assert rule["assignedCategory"] == "anime"
    assert "torrentParams" not in rule


@pytest.mark.api
@pytest.mark.integration
async def test_media_read_http_certification_uses_runtime_and_real_qb_service(
    api_client, db_session, monkeypatch
):
    from app.capabilities.factory import build_capability_registry

    _prepare_runtime(monkeypatch)
    factory = _RecordingQBFactory()
    _configure_qb(monkeypatch, factory)
    owners = await _seed_users(db_session)
    from app.core.config import settings

    monkeypatch.setattr(
        settings, "QB_ALLOWED_USER_IDS", f"{owners[0].id},{owners[1].id}"
    )
    registry = build_capability_registry()
    for action in _ACTIONS:
        registered = registry.find_action(action)
        assert registered is not None
        capability, descriptor = registered
        assert capability.name == "media"
        assert descriptor.name == action
        assert descriptor.public_name == action
        assert descriptor.version == "v1"
        assert descriptor.is_side_effect is False
        assert descriptor.approval_required is False
        assert descriptor.idempotency_mode == "none"
        assert descriptor.requires_auth is (action != "library_status")
    business_before = await _business_snapshot(db_session)
    provider_before = (copy.deepcopy(factory.feeds), copy.deepcopy(factory.rules))

    actions = (
        ("library_status", owners[0]),
        ("list_rss_feeds", owners[0]),
        ("list_rss_rules", owners[1]),
    )
    for action, owner in actions:
        frames, tool_end, gateway_calls = await _chat(
            api_client, monkeypatch, owner, action, {}
        )
        assert tool_end is not None
        assert tool_end["status"] == "succeeded"
        assert tool_end["error_code"] is None
        assert tool_end["retryable"] is False
        output = tool_end["output"]
        assert output["success"] is True
        assert output["run_id"] == _run_id(frames)

        if action == "library_status":
            assert output["configured"] is True
            assert output["provider"] == "qbittorrent"
            assert not {"connected", "healthy", "connection_status"}.intersection(
                output
            )
        elif action == "list_rss_feeds":
            assert output["configured"] is True
            assert output["feeds"] == factory.feeds
        else:
            _assert_rule_has_no_torrent_params(output)

        await _assert_run_records(
            api_client,
            db_session,
            frames=frames,
            owner=owner,
            other_owner=owners[1] if owner is owners[0] else owners[0],
            action=action,
            expected_run_status="succeeded",
            expected_sse_terminal="run_completed",
            expected_invocation_status="succeeded",
        )
        assert await _business_snapshot(db_session) == business_before

        assert len(gateway_calls.decision_ids) >= 2
        assert "synthetic-qb-password-private" not in "".join(gateway_calls.requests)

    assert factory.clients
    assert factory.calls.count("rss_items") == 1
    assert factory.calls.count("rss_rules") == 1
    assert all(
        config
        == {
            "host": _SYNTHETIC_HOST,
            "username": _SYNTHETIC_USERNAME,
            "password": _SYNTHETIC_PASSWORD,
        }
        for config in factory.configurations
    )
    factory.assert_read_only()
    assert (factory.feeds, factory.rules) == provider_before
    assert await _business_snapshot(db_session) == business_before


@pytest.mark.api
@pytest.mark.integration
@pytest.mark.parametrize(
    ("enabled", "host", "username", "expected_configured", "expected_provider"),
    [
        (True, _SYNTHETIC_HOST, _SYNTHETIC_USERNAME, True, "qbittorrent"),
        (False, _SYNTHETIC_HOST, _SYNTHETIC_USERNAME, False, None),
        (True, "", _SYNTHETIC_USERNAME, False, None),
    ],
)
async def test_library_status_reports_local_configuration_without_sdk_health_probe(
    api_client,
    db_session,
    monkeypatch,
    enabled: bool,
    host: str,
    username: str,
    expected_configured: bool,
    expected_provider: str | None,
):
    _prepare_runtime(monkeypatch)
    factory = _RecordingQBFactory()
    _configure_qb(monkeypatch, factory)
    owners = await _seed_users(db_session)
    from app.core.config import settings

    monkeypatch.setattr(settings, "ENABLE_QB_PROXY", enabled)
    monkeypatch.setattr(settings, "QB_HOST", host)
    monkeypatch.setattr(settings, "QB_USERNAME", username)
    monkeypatch.setattr(settings, "QB_ALLOWED_USER_IDS", "")
    business_before = await _business_snapshot(db_session)

    frames, tool_end, _ = await _chat(
        api_client, monkeypatch, owners[0], "library_status", {}
    )
    assert tool_end is not None
    assert tool_end["status"] == "succeeded"
    output = tool_end["output"]
    assert output["configured"] is expected_configured
    assert output["provider"] == expected_provider
    assert not {"connected", "healthy", "connection_status"}.intersection(output)
    assert factory.clients == []
    assert factory.calls == []
    await _assert_run_records(
        api_client,
        db_session,
        frames=frames,
        owner=owners[0],
        other_owner=owners[1],
        action="library_status",
        expected_run_status="succeeded",
        expected_sse_terminal="run_completed",
        expected_invocation_status="succeeded",
    )
    assert await _business_snapshot(db_session) == business_before


@pytest.mark.api
@pytest.mark.integration
@pytest.mark.parametrize(
    ("scenario", "expected_code", "expected_tool_status", "expected_invocation_status"),
    [
        ("empty_allowlist", "forbidden", "failed", "failed"),
        ("invalid_allowlist", "forbidden", "failed", "failed"),
        ("disabled", "not_configured", "denied", "denied"),
        ("not_allowlisted", "forbidden", "failed", "failed"),
    ],
)
@pytest.mark.parametrize("action", _QB_ACTIONS)
async def test_media_http_read_refusal_precedes_sdk_client_creation(
    api_client,
    db_session,
    monkeypatch,
    scenario: str,
    expected_code: str,
    expected_tool_status: str,
    expected_invocation_status: str,
    action: str,
):
    _prepare_runtime(monkeypatch)
    factory = _RecordingQBFactory()
    _configure_qb(monkeypatch, factory)
    owners = await _seed_users(db_session)
    from app.core.config import settings

    if scenario == "empty_allowlist":
        monkeypatch.setattr(settings, "QB_ALLOWED_USER_IDS", "")
        request_owner = owners[0]
    elif scenario == "invalid_allowlist":
        monkeypatch.setattr(settings, "QB_ALLOWED_USER_IDS", "7,,not-an-id")
        request_owner = owners[0]
    elif scenario == "disabled":
        monkeypatch.setattr(settings, "ENABLE_QB_PROXY", False)
        monkeypatch.setattr(settings, "QB_ALLOWED_USER_IDS", str(owners[0].id))
        request_owner = owners[0]
    else:
        monkeypatch.setattr(settings, "QB_ALLOWED_USER_IDS", str(owners[0].id))
        request_owner = owners[1]

    business_before = await _business_snapshot(db_session)
    frames, tool_end, calls = await _chat(
        api_client, monkeypatch, request_owner, action, {}
    )
    assert tool_end is not None
    assert tool_end["status"] == expected_tool_status
    assert tool_end["error_code"] == expected_code
    assert tool_end["retryable"] is False
    assert factory.clients == []
    assert factory.configurations == []
    assert factory.calls == []
    factory.assert_read_only()
    await _assert_run_records(
        api_client,
        db_session,
        frames=frames,
        owner=request_owner,
        other_owner=owners[0] if request_owner is owners[1] else owners[1],
        action=action,
        expected_run_status="failed",
        expected_sse_terminal="run_failed",
        expected_invocation_status=expected_invocation_status,
        expected_invocation_code=expected_code,
    )
    assert await _business_snapshot(db_session) == business_before
    assert _SYNTHETIC_PASSWORD not in "".join(calls.requests)


@pytest.mark.api
@pytest.mark.integration
@pytest.mark.parametrize("action", _QB_ACTIONS)
@pytest.mark.parametrize("forged_field", ["user_id", "host"])
async def test_model_supplied_identity_or_qb_host_is_rejected_before_sdk(
    api_client, db_session, monkeypatch, action: str, forged_field: str
):
    _prepare_runtime(monkeypatch)
    factory = _RecordingQBFactory()
    _configure_qb(monkeypatch, factory)
    owners = await _seed_users(db_session)
    from app.core.config import settings

    monkeypatch.setattr(settings, "QB_ALLOWED_USER_IDS", str(owners[0].id))
    principal = owners[1] if forged_field == "user_id" else owners[0]
    arguments = (
        {"user_id": owners[0].id}
        if forged_field == "user_id"
        else {"host": "https://untrusted.synthetic.invalid"}
    )
    business_before = await _business_snapshot(db_session)

    frames, tool_end, _ = await _chat(
        api_client, monkeypatch, principal, action, arguments
    )
    assert not any(frame.get("_event_type") == "run_completed" for frame in frames)
    assert factory.clients == []
    assert factory.configurations == []
    assert factory.calls == []
    assert factory.write_calls == []
    if forged_field == "user_id":
        assert tool_end is None
        assert not any(
            frame.get("_event_type") in {"tool_call_start", "tool_call_end"}
            for frame in frames
        )
    else:
        assert tool_end is not None
        assert tool_end["status"] == "denied"
        assert tool_end["error_code"] == "invalid_request"

    run_id = _run_id(frames)
    assert [
        frame["_event_type"]
        for frame in frames
        if frame.get("_event_type") in _TERMINAL_SSE_EVENTS
    ] == ["run_failed"]
    run = (
        await db_session.execute(select(AgentRun).where(AgentRun.run_id == run_id))
    ).scalar_one()
    assert run.user_id == principal.id
    assert run.status == "failed"
    invocations = (
        (
            await db_session.execute(
                select(AgentInvocation).where(AgentInvocation.run_id == run_id)
            )
        )
        .scalars()
        .all()
    )
    if forged_field == "user_id":
        assert invocations == []
    else:
        assert len(invocations) == 1
        assert invocations[0].status == "denied"
        assert invocations[0].capability == action
    event_response = await api_client.get(
        f"/api/v1/runs/{run_id}/events", headers=_auth(principal.id)
    )
    assert event_response.status_code == 200
    terminal_events = [
        event
        for event in event_response.json()["events"]
        if event["event_type"] in {"run.succeeded", "run.failed", "run.cancelled"}
    ]
    assert [event["event_type"] for event in terminal_events] == ["run.failed"]
    trace_response = await api_client.get(
        f"/api/v1/trace/{run_id}", headers=_auth(principal.id)
    )
    assert trace_response.status_code == 200
    trace = trace_response.json()
    assert trace["run_id"] == run_id
    assert trace["user_id"] == principal.id
    assert trace["status"] == "failed"
    foreign_owner = owners[0] if principal is owners[1] else owners[1]
    assert (
        await api_client.get(f"/api/v1/trace/{run_id}", headers=_auth(foreign_owner.id))
    ).status_code == 404
    assert await _business_snapshot(db_session) == business_before


@pytest.mark.api
@pytest.mark.integration
@pytest.mark.parametrize("action", _QB_ACTIONS)
@pytest.mark.parametrize(
    ("fault_name", "expected_code"),
    [
        ("connection", "qb_connection_error"),
        ("login", "qb_authentication_failed"),
        ("login_server", "qb_server_error"),
        ("server", "qb_server_error"),
        ("unknown", "qb_operation_failed"),
    ],
)
async def test_media_http_sdk_read_faults_are_safe_and_terminal(
    api_client,
    db_session,
    monkeypatch,
    caplog,
    action: str,
    fault_name: str,
    expected_code: str,
):
    import qbittorrentapi

    _prepare_runtime(monkeypatch)
    factory = _RecordingQBFactory()
    exception_type = {
        "connection": qbittorrentapi.APIConnectionError,
        "login": qbittorrentapi.LoginFailed,
        "login_server": qbittorrentapi.HTTP5XXError,
        "server": qbittorrentapi.HTTP5XXError,
        "unknown": RuntimeError,
    }[fault_name]
    operation = (
        "auth_log_in"
        if fault_name in {"login", "login_server"}
        else ("rss_items" if action == "list_rss_feeds" else "rss_rules")
    )
    factory.failure = (operation, exception_type(_RAW_ERROR))
    _configure_qb(monkeypatch, factory)
    owners = await _seed_users(db_session)
    from app.core.config import settings

    monkeypatch.setattr(settings, "QB_ALLOWED_USER_IDS", str(owners[0].id))
    before = await _business_snapshot(db_session)
    provider_before = (copy.deepcopy(factory.feeds), copy.deepcopy(factory.rules))

    with caplog.at_level(logging.ERROR):
        frames, tool_end, calls = await _chat(
            api_client, monkeypatch, owners[0], action, {}
        )
    assert tool_end is not None
    assert tool_end["status"] == "failed"
    assert tool_end["error_code"] == expected_code
    # The current Dispatcher deliberately does not enable automatic retries for
    # these adapter-specific error codes, even when QBService marks a connection
    # failure retryable for a caller that owns an explicit retry policy.
    assert tool_end["retryable"] is False
    assert len(factory.clients) == 1
    assert factory.calls[0] == "auth_log_in"
    assert factory.write_calls == []
    factory.assert_read_only()

    run_id, failure_event, trace = await _assert_run_records(
        api_client,
        db_session,
        frames=frames,
        owner=owners[0],
        other_owner=owners[1],
        action=action,
        expected_run_status="failed",
        expected_sse_terminal="run_failed",
        expected_invocation_status="failed",
        expected_invocation_code=expected_code,
    )
    assert failure_event["retryable"] is False
    serialized = json.dumps(
        {
            "frames": frames,
            "failure": failure_event,
            "trace": trace,
            "gateway_requests": calls.requests,
            "logs": caplog.text,
        },
        ensure_ascii=False,
        allow_nan=False,
    )
    assert _RAW_ERROR not in serialized
    assert _SYNTHETIC_PASSWORD not in serialized
    event_response = await api_client.get(
        f"/api/v1/runs/{run_id}/events", headers=_auth(owners[0].id)
    )
    assert _RAW_ERROR not in event_response.text
    assert _SYNTHETIC_PASSWORD not in event_response.text
    assert (factory.feeds, factory.rules) == provider_before
    assert await _business_snapshot(db_session) == before


@pytest.mark.api
@pytest.mark.integration
@pytest.mark.parametrize("path", _REST_PATHS)
async def test_rest_rss_gets_safely_classify_login_http_5xx(
    api_client, db_session, monkeypatch, path: str
):
    import qbittorrentapi

    factory = _RecordingQBFactory()
    factory.failure = ("auth_log_in", qbittorrentapi.HTTP5XXError(_RAW_ERROR))
    _configure_qb(monkeypatch, factory)
    owners = await _seed_users(db_session)
    from app.core.config import settings

    monkeypatch.setattr(settings, "QB_ALLOWED_USER_IDS", str(owners[0].id))
    business_before = await _business_snapshot(db_session)

    response = await api_client.get(path, headers=_auth(owners[0].id))

    assert response.status_code == 502
    assert response.json() == {
        "error_code": "qb_server_error",
        "message": "qBittorrent returned a server error.",
        "retryable": False,
    }
    assert _RAW_ERROR not in response.text
    assert _SYNTHETIC_PASSWORD not in response.text
    assert len(factory.clients) == 1
    assert factory.calls == ["auth_log_in"]
    factory.assert_read_only()
    assert await _business_snapshot(db_session) == business_before


@pytest.mark.api
@pytest.mark.integration
async def test_rest_rss_gets_preserve_dtos_and_share_allowed_server_resources(
    api_client, db_session, monkeypatch
):
    _prepare_runtime(monkeypatch)
    factory = _RecordingQBFactory()
    _configure_qb(monkeypatch, factory)
    owners = await _seed_users(db_session)
    from app.core.config import settings

    monkeypatch.setattr(
        settings, "QB_ALLOWED_USER_IDS", f"{owners[0].id},{owners[1].id}"
    )
    business_before = await _business_snapshot(db_session)
    provider_before = (copy.deepcopy(factory.feeds), copy.deepcopy(factory.rules))

    payloads: dict[str, list[dict[str, Any]]] = {path: [] for path in _REST_PATHS}
    for path in _REST_PATHS:
        for owner in owners:
            response = await api_client.get(path, headers=_auth(owner.id))
            assert response.status_code == 200
            payload = response.json()
            payloads[path].append(payload)
            if path.endswith("/list"):
                assert set(payload) == {"items"}
                assert payload["items"] == factory.feeds
            else:
                assert set(payload) == {"rules"}
                rule = payload["rules"]["synthetic-rule"]
                assert rule["assignedCategory"] == "anime"
                assert isinstance(rule.get("torrentParams"), dict)

    assert payloads[_REST_PATHS[0]][0] == payloads[_REST_PATHS[0]][1]
    assert payloads[_REST_PATHS[1]][0] == payloads[_REST_PATHS[1]][1]
    assert factory.calls.count("rss_items") == 2
    assert factory.calls.count("rss_rules") == 2
    factory.assert_read_only()
    assert (factory.feeds, factory.rules) == provider_before
    assert await _business_snapshot(db_session) == business_before


@pytest.mark.api
@pytest.mark.integration
@pytest.mark.parametrize("path", _REST_PATHS)
@pytest.mark.parametrize("access", ["anonymous", "disabled", "not_allowlisted"])
async def test_rest_rss_gets_enforce_real_auth_and_qb_access_before_client(
    api_client, db_session, monkeypatch, path: str, access: str
):
    _prepare_runtime(monkeypatch)
    factory = _RecordingQBFactory()
    _configure_qb(monkeypatch, factory)
    owners = await _seed_users(db_session)
    from app.core.config import settings

    headers: dict[str, str] = _auth(owners[0].id)
    monkeypatch.setattr(settings, "QB_ALLOWED_USER_IDS", str(owners[0].id))
    if access == "anonymous":
        headers = {}
    elif access == "disabled":
        monkeypatch.setattr(settings, "ENABLE_QB_PROXY", False)
    else:
        headers = _auth(owners[1].id)

    business_before = await _business_snapshot(db_session)
    response = await api_client.get(path, headers=headers)
    assert response.status_code in {401, 403}
    assert factory.clients == []
    assert factory.configurations == []
    assert factory.calls == []
    assert factory.write_calls == []
    assert await _business_snapshot(db_session) == business_before

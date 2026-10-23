"""Real HTTP/JWT certification for Media writes through Agent and REST paths."""

from __future__ import annotations

import copy
import hashlib
import json
from typing import Any
from uuid import uuid4

import pytest
from sqlmodel import col, select

from app.core.security import create_access_token
from app.harness.model_types import ModelCallResult
from app.models import Collection, Schedule, Subject, User
from app.models.agent_run import AgentInvocation, AgentRun, AgentRunEvent
from app.models.agent_trace import AgentTraceModel


_ACTIONS = (
    "add_rss_feed",
    "upsert_rss_feed",
    "remove_rss_feed",
    "set_rss_rule",
    "remove_rss_rule",
)
_REST_ROUTES = {
    "add_rss_feed": ("POST", "/api/v1/rss/add"),
    "upsert_rss_feed": ("POST", "/api/v1/rss/upsert"),
    "remove_rss_feed": ("DELETE", "/api/v1/rss/remove"),
    "set_rss_rule": ("POST", "/api/v1/rss/set-rule"),
    "remove_rss_rule": ("DELETE", "/api/v1/rss/remove-rule"),
}
_REST_OPERATIONS = {
    "add_rss_feed": "rss.add",
    "upsert_rss_feed": "rss.upsert",
    "remove_rss_feed": "rss.remove",
    "set_rss_rule": "rss.set_rule",
    "remove_rss_rule": "rss.remove_rule",
}
_SYNTHETIC_HOST = "https://qb.synthetic.invalid"
_SYNTHETIC_PASSWORD = "synthetic-qb-password-private"
_RAW_ERROR = "synthetic-private-provider-diagnostic"
_FEED_URL = "https://feeds.example.invalid/anime.xml"


def _rule() -> dict[str, Any]:
    return {
        "affectedFeeds": [_FEED_URL],
        "assignedCategory": "anime",
        "enabled": True,
        "episodeFilter": "",
        "ignoreDays": 0,
        "mustContain": "anime",
        "mustNotContain": "",
        "previouslyMatchedEpisodes": [],
        "priority": 1,
        "savePath": "synthetic-download-root",
        "smartFilter": False,
        "useRegex": False,
    }


def _arguments(action: str, key: str, *, url: str = _FEED_URL) -> dict[str, Any]:
    if action in {"add_rss_feed", "upsert_rss_feed"}:
        return {"url": url, "name": "synthetic-feed", "idempotency_key": key}
    if action == "remove_rss_feed":
        return {"item_path": "synthetic-feed", "idempotency_key": key}
    if action == "set_rss_rule":
        return {
            "rule_name": "synthetic-rule",
            "rule": _rule(),
            "idempotency_key": key,
        }
    if action == "remove_rss_rule":
        return {"rule_name": "synthetic-rule", "idempotency_key": key}
    raise AssertionError(f"Unknown action {action}")


class _RecordingQBClient:
    """Fake only at qbittorrentapi.Client; QBService remains real."""

    def __init__(self, factory: _RecordingQBFactory) -> None:
        self.factory = factory

    def _record(
        self, operation: str, *, write: bool = False, defer_failure: bool = False
    ) -> Exception | None:
        self.factory.calls.append(operation)
        if write:
            self.factory.write_calls.append(operation)
        if self.factory.failure and self.factory.failure[0] == operation:
            if not defer_failure:
                raise self.factory.failure[1]
            return self.factory.failure[1]
        return None

    def auth_log_in(self) -> None:
        self._record("auth_log_in")

    def rss_items(self, **kwargs: Any) -> dict[str, Any]:
        del kwargs
        self._record("rss_items")
        return copy.deepcopy(self.factory.feeds)

    def rss_add_feed(self, *, url: str, item_path: str | None = None) -> None:
        import qbittorrentapi

        failure = self.factory.failure
        defer_failure = bool(
            failure
            and failure[0] == "rss_add_feed"
            and not isinstance(failure[1], qbittorrentapi.HTTP4XXError)
        )
        deferred_error = self._record(
            "rss_add_feed", write=True, defer_failure=defer_failure
        )
        self.factory.feeds[item_path or url] = {
            "uid": f"uid-{item_path or 'feed'}",
            "url": url,
        }
        if deferred_error is not None:
            raise deferred_error

    def rss_remove_item(self, *, item_path: str) -> None:
        self._record("rss_remove_item", write=True)
        self.factory.feeds.pop(item_path, None)

    def rss_set_rule(self, *, rule_name: str, rule_def: dict[str, Any]) -> None:
        self._record("rss_set_rule", write=True)
        self.factory.rules[rule_name] = copy.deepcopy(rule_def)

    def rss_remove_rule(self, *, rule_name: str) -> None:
        self._record("rss_remove_rule", write=True)
        self.factory.rules.pop(rule_name, None)


class _RecordingQBFactory:
    def __init__(self) -> None:
        self.feeds: dict[str, dict[str, str]] = {}
        self.rules: dict[str, dict[str, Any]] = {}
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


class _GatewayCalls:
    def __init__(self) -> None:
        self.decision_ids: list[str] = []
        self.requests: list[str] = []
        self.proposed = False


def _gateway(action: str, arguments: dict[str, Any], calls: _GatewayCalls):
    class _FakeGateway:
        def __init__(self, **kwargs: Any) -> None:
            self.model = str(kwargs["model"])

        async def infer(self, **kwargs: Any) -> ModelCallResult:
            calls.requests.append(repr(kwargs))
            decision_id = f"media-write-{uuid4().hex}"
            calls.decision_ids.append(decision_id)
            if not calls.proposed:
                calls.proposed = True
                decision: dict[str, Any] = {
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
    for line in text.replace("\r\n", "\n").splitlines():
        if line.startswith("event:"):
            event_type = line.removeprefix("event:").strip()
        elif line.startswith("data:"):
            frame = json.loads(line.removeprefix("data:").strip())
            frame["_event_type"] = event_type
            frames.append(frame)
    return frames


def _headers(user_id: int | None) -> dict[str, str]:
    assert user_id is not None
    return {
        "Authorization": f"Bearer {create_access_token({'sub': str(user_id)})}",
        "X-Api-Key": "synthetic-test-key",
    }


def _configure_qb(monkeypatch, factory: _RecordingQBFactory) -> None:
    import qbittorrentapi

    from app.core.config import settings

    monkeypatch.setattr(settings, "ENABLE_QB_PROXY", True)
    monkeypatch.setattr(settings, "QB_HOST", _SYNTHETIC_HOST)
    monkeypatch.setattr(settings, "QB_USERNAME", "synthetic-qb-user")
    monkeypatch.setattr(settings, "QB_PASSWORD", _SYNTHETIC_PASSWORD)
    monkeypatch.setattr(qbittorrentapi, "Client", factory)


async def _seed_users(db) -> tuple[User, User]:
    suffix = uuid4().hex[:12]
    owners = [User(username=f"media-write-{label}-{suffix}") for label in ("a", "b")]
    db.add_all(owners)
    await db.commit()
    return owners[0], owners[1]


async def _business_snapshot(db) -> dict[str, tuple[int, str]]:
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
    checkpoint_path: Any,
) -> tuple[dict[str, str], str, list[dict[str, Any]], _GatewayCalls]:
    from app.api.v1 import agent as agent_api
    from app.core.config import settings

    assert user.id is not None
    calls = _GatewayCalls()
    monkeypatch.setattr(settings, "HARNESS_CHECKPOINT_ADAPTER", "sqlite")
    monkeypatch.setattr(settings, "CHECKPOINT_DB_PATH", str(checkpoint_path))
    monkeypatch.setattr(
        agent_api, "OpenAIModelGateway", _gateway(action, arguments, calls)
    )
    thread_id = f"media-write-{action}-{uuid4().hex}"
    headers = _headers(user.id)
    response = await api_client.post(
        "/api/v1/chat",
        headers=headers,
        json={
            "model": "synthetic-model",
            "thread_id": thread_id,
            "messages": [{"role": "user", "content": "Update synthetic RSS settings."}],
        },
    )
    assert response.status_code == 200, response.text
    assert response.headers["content-type"].startswith("text/event-stream")
    frames = _frames(response.text)
    assert len(calls.decision_ids) == len(set(calls.decision_ids))
    return headers, thread_id, frames, calls


def _run_id(frames: list[dict[str, Any]]) -> str:
    run_ids = {frame.get("run_id") for frame in frames if frame.get("run_id")}
    assert len(run_ids) == 1
    return str(run_ids.pop())


def _resume_params(thread_id: str, run_id: str, decision: str) -> dict[str, str]:
    return {"thread_id": thread_id, "run_id": run_id, "decision": decision}


async def _start_approved_action(
    api_client,
    monkeypatch,
    owner: User,
    action: str,
    arguments: dict[str, Any],
    checkpoint_path: Any,
) -> tuple[dict[str, str], str, str, list[dict[str, Any]], _GatewayCalls]:
    headers, thread_id, frames, calls = await _chat(
        api_client, monkeypatch, owner, action, arguments, checkpoint_path
    )
    approvals = [
        frame for frame in frames if frame.get("_event_type") == "approval_required"
    ]
    assert len(approvals) == 1
    run_id = _run_id(frames)
    assert approvals[0]["capability"] == action
    assert approvals[0]["run_id"] == run_id
    return headers, thread_id, run_id, frames, calls


async def _rest_call(api_client, owner: User, action: str, arguments: dict[str, Any]):
    assert owner.id is not None
    method, path = _REST_ROUTES[action]
    headers = {"Authorization": f"Bearer {create_access_token({'sub': str(owner.id)})}"}
    return await api_client.request(method, path, headers=headers, json=arguments)


def _rest_scope(action: str, owner_id: int, arguments: dict[str, Any]) -> str:
    if action in {"add_rss_feed", "upsert_rss_feed"}:
        resource = arguments.get("name") or arguments["url"]
    elif action == "remove_rss_feed":
        resource = arguments["item_path"]
    else:
        resource = arguments["rule_name"]
    resource_hash = hashlib.sha256(resource.encode("utf-8")).hexdigest()
    return (
        f"principal:{owner_id}|operation:{_REST_OPERATIONS[action]}|"
        f"resource:{resource_hash}"
    )


def _rest_run_id(scope: str, key: str) -> str:
    canonical = json.dumps(
        {"scope": scope, "key": key},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return f"idem-{hashlib.sha256(canonical).hexdigest()}"


@pytest.mark.api
@pytest.mark.integration
@pytest.mark.parametrize("action", _ACTIONS)
async def test_media_write_chat_requires_owner_approval_and_records_private_run_trace(
    action: str, api_client, db_session, monkeypatch, tmp_path
) -> None:
    from app.capabilities.factory import build_capability_registry
    from app.core.config import settings

    owners = await _seed_users(db_session)
    assert owners[0].id is not None and owners[1].id is not None
    monkeypatch.setattr(
        settings, "QB_ALLOWED_USER_IDS", f"{owners[0].id},{owners[1].id}"
    )
    factory = _RecordingQBFactory()
    _configure_qb(monkeypatch, factory)
    registry = build_capability_registry()
    registered = registry.find_action(action)
    assert registered is not None
    capability, descriptor = registered
    assert capability.name == "media"
    assert descriptor.public_name == action
    assert descriptor.requires_auth is True
    assert descriptor.is_side_effect is True
    assert descriptor.approval_required is True
    assert descriptor.idempotency_mode == "required"

    arguments = _arguments(action, f"agent-{uuid4().hex}")
    before = await _business_snapshot(db_session)
    headers, thread_id, run_id, initial, gateway_calls = await _start_approved_action(
        api_client,
        monkeypatch,
        owners[0],
        action,
        arguments,
        tmp_path / f"{action}-approved.db",
    )
    assert not any(frame.get("_event_type") == "run_completed" for frame in initial)
    assert factory.clients == []
    assert await _business_snapshot(db_session) == before

    paused = await api_client.get(f"/api/v1/runs/{run_id}", headers=headers)
    assert paused.status_code == 200
    assert paused.json()["status"] == "paused"
    run_row = (
        await db_session.execute(select(AgentRun).where(AgentRun.run_id == run_id))
    ).scalar_one()
    assert run_row.user_id == owners[0].id
    assert run_row.status == "paused"

    foreign = await api_client.post(
        "/api/v1/chat/resume",
        params=_resume_params(thread_id, run_id, "approve"),
        headers=_headers(owners[1].id),
    )
    assert foreign.status_code == 404
    assert factory.clients == []
    assert (await api_client.get(f"/api/v1/runs/{run_id}", headers=headers)).json()[
        "status"
    ] == "paused"

    approved = await api_client.post(
        "/api/v1/chat/resume",
        params=_resume_params(thread_id, run_id, "approve"),
        headers=headers,
    )
    assert approved.status_code == 200, approved.text
    approved_frames = _frames(approved.text)
    ends = [
        frame
        for frame in approved_frames
        if frame.get("_event_type") == "tool_call_end"
        and frame.get("status") == "succeeded"
    ]
    assert len(ends) == 1
    assert ends[0]["capability"] == action
    assert ends[0]["status"] == "succeeded"
    assert ends[0]["output"]["success"] is True
    assert ends[0]["output"]["operation"]["status"] == "succeeded"
    assert factory.write_calls == [
        {
            "add_rss_feed": "rss_add_feed",
            "upsert_rss_feed": "rss_add_feed",
            "remove_rss_feed": "rss_remove_item",
            "set_rss_rule": "rss_set_rule",
            "remove_rss_rule": "rss_remove_rule",
        }[action]
    ]
    assert len(factory.clients) == 1
    assert all(
        config
        == {
            "host": _SYNTHETIC_HOST,
            "username": "synthetic-qb-user",
            "password": _SYNTHETIC_PASSWORD,
        }
        for config in factory.configurations
    )
    assert await _business_snapshot(db_session) == before

    run_response = await api_client.get(f"/api/v1/runs/{run_id}", headers=headers)
    assert run_response.status_code == 200
    assert run_response.json()["status"] == "succeeded"
    run_row = (
        await db_session.execute(select(AgentRun).where(AgentRun.run_id == run_id))
    ).scalar_one()
    assert run_row.user_id == owners[0].id
    assert run_row.status == "succeeded"
    invocations = (
        (
            await db_session.execute(
                select(AgentInvocation).where(AgentInvocation.run_id == run_id)
            )
        )
        .scalars()
        .all()
    )
    assert len(invocations) == 1
    assert invocations[0].capability == action
    assert invocations[0].status == "succeeded"

    event_response = await api_client.get(
        f"/api/v1/runs/{run_id}/events", headers=headers
    )
    assert event_response.status_code == 200
    event_ids = [event["event_id"] for event in event_response.json()["events"]]
    event_rows = (
        (
            await db_session.execute(
                select(AgentRunEvent)
                .where(AgentRunEvent.run_id == run_id)
                .order_by(col(AgentRunEvent.sequence))
            )
        )
        .scalars()
        .all()
    )
    assert event_ids == [event.event_id for event in event_rows]
    assert {event.event_type for event in event_rows} >= {
        "run.paused",
        "tool_call_end",
        "run.succeeded",
    }

    trace_response = await api_client.get(f"/api/v1/trace/{run_id}", headers=headers)
    assert trace_response.status_code == 200
    trace = trace_response.json()
    assert trace["trace_id"] == run_id
    assert trace["run_id"] == run_id
    assert trace["user_id"] == owners[0].id
    trace_row = (
        await db_session.execute(
            select(AgentTraceModel).where(AgentTraceModel.trace_id == run_id)
        )
    ).scalar_one()
    assert trace_row.user_id == owners[0].id
    assert trace_row.status == "completed"
    for path in (
        f"/api/v1/runs/{run_id}",
        f"/api/v1/runs/{run_id}/events",
        f"/api/v1/trace/{run_id}",
    ):
        assert (
            await api_client.get(path, headers=_headers(owners[1].id))
        ).status_code == 404

    repeated = await api_client.post(
        "/api/v1/chat/resume",
        params=_resume_params(thread_id, run_id, "approve"),
        headers=headers,
    )
    assert repeated.status_code == 409
    assert factory.write_calls == [
        {
            "add_rss_feed": "rss_add_feed",
            "upsert_rss_feed": "rss_add_feed",
            "remove_rss_feed": "rss_remove_item",
            "set_rss_rule": "rss_set_rule",
            "remove_rss_rule": "rss_remove_rule",
        }[action]
    ]
    assert len(gateway_calls.decision_ids) == len(set(gateway_calls.decision_ids))


@pytest.mark.api
@pytest.mark.integration
@pytest.mark.parametrize("action", _ACTIONS)
async def test_media_write_chat_rejects_approval_without_sdk_call(
    action: str, api_client, db_session, monkeypatch, tmp_path
) -> None:
    owners = await _seed_users(db_session)
    factory = _RecordingQBFactory()
    _configure_qb(monkeypatch, factory)
    from app.core.config import settings

    assert owners[0].id is not None and owners[1].id is not None
    monkeypatch.setattr(settings, "QB_ALLOWED_USER_IDS", f"{owners[0].id}")
    before = await _business_snapshot(db_session)
    headers, thread_id, run_id, _, _ = await _start_approved_action(
        api_client,
        monkeypatch,
        owners[0],
        action,
        _arguments(action, f"reject-{uuid4().hex}"),
        tmp_path / f"{action}-rejected.db",
    )
    assert factory.clients == []
    invalid_decision = await api_client.post(
        "/api/v1/chat/resume",
        params=_resume_params(thread_id, run_id, "approve:remove_rss_rule"),
        headers=headers,
    )
    assert invalid_decision.status_code == 400
    still_paused = await api_client.get(f"/api/v1/runs/{run_id}", headers=headers)
    assert still_paused.status_code == 200
    assert still_paused.json()["status"] == "paused"

    rejected = await api_client.post(
        "/api/v1/chat/resume",
        params=_resume_params(thread_id, run_id, "reject"),
        headers=headers,
    )
    assert rejected.status_code == 200, rejected.text
    frames = _frames(rejected.text)
    assert any(frame.get("_event_type") == "run_failed" for frame in frames)
    assert (await api_client.get(f"/api/v1/runs/{run_id}", headers=headers)).json()[
        "status"
    ] == "failed"
    assert factory.clients == []
    assert factory.write_calls == []
    assert await _business_snapshot(db_session) == before


@pytest.mark.api
@pytest.mark.integration
@pytest.mark.parametrize("action", _ACTIONS)
@pytest.mark.parametrize("forged_field", ["user_id", "approval_state"])
async def test_media_write_chat_rejects_forged_runtime_authority_before_sdk(
    action: str,
    forged_field: str,
    api_client,
    db_session,
    monkeypatch,
    tmp_path,
) -> None:
    owners = await _seed_users(db_session)
    factory = _RecordingQBFactory()
    _configure_qb(monkeypatch, factory)
    from app.core.config import settings

    assert owners[0].id is not None and owners[1].id is not None
    monkeypatch.setattr(settings, "QB_ALLOWED_USER_IDS", f"{owners[0].id}")
    arguments = _arguments(action, f"forged-{uuid4().hex}")
    arguments[forged_field] = (
        owners[0].id
        if forged_field == "user_id"
        else {"approved": True, "principal_id": owners[0].id}
    )
    before = await _business_snapshot(db_session)
    _, _, frames, gateway_calls = await _chat(
        api_client,
        monkeypatch,
        owners[1],
        action,
        arguments,
        tmp_path / f"{action}-{forged_field}.db",
    )
    assert not any(frame.get("_event_type") == "run_completed" for frame in frames)
    assert not any(frame.get("_event_type") == "approval_required" for frame in frames)
    assert factory.clients == []
    assert factory.configurations == []
    assert factory.calls == []
    assert factory.write_calls == []
    assert await _business_snapshot(db_session) == before
    assert _SYNTHETIC_PASSWORD not in "".join(gateway_calls.requests)


@pytest.mark.api
@pytest.mark.integration
async def test_media_chat_anonymous_is_refused_before_gateway_or_sdk(
    api_client, db_session, monkeypatch
) -> None:
    from app.api.v1 import agent as agent_api

    factory = _RecordingQBFactory()
    _configure_qb(monkeypatch, factory)
    calls = _GatewayCalls()
    monkeypatch.setattr(
        agent_api,
        "OpenAIModelGateway",
        _gateway("add_rss_feed", _arguments("add_rss_feed", "anonymous-key"), calls),
    )
    before = await _business_snapshot(db_session)
    response = await api_client.post(
        "/api/v1/chat",
        headers={"X-Api-Key": "synthetic-test-key"},
        json={
            "model": "synthetic-model",
            "messages": [{"role": "user", "content": "write"}],
        },
    )
    assert response.status_code == 200
    frames = _frames(response.text)
    assert not any(frame.get("_event_type") == "approval_required" for frame in frames)
    assert not any(
        frame.get("_event_type") == "tool_call_end"
        and frame.get("status") == "succeeded"
        for frame in frames
    )
    assert factory.clients == []
    assert factory.write_calls == []
    assert await _business_snapshot(db_session) == before


@pytest.mark.api
@pytest.mark.integration
@pytest.mark.parametrize("action", _ACTIONS)
@pytest.mark.parametrize(
    "access", ["anonymous", "disabled", "invalid_allowlist", "not_allowlisted"]
)
async def test_media_rest_write_refusal_precedes_sdk_creation(
    action: str, access: str, api_client, db_session, monkeypatch
) -> None:
    from app.core.config import settings

    owners = await _seed_users(db_session)
    assert owners[0].id is not None and owners[1].id is not None
    factory = _RecordingQBFactory()
    _configure_qb(monkeypatch, factory)
    monkeypatch.setattr(settings, "QB_ALLOWED_USER_IDS", str(owners[0].id))
    arguments = _arguments(action, f"rest-refusal-{uuid4().hex}")
    headers: dict[str, str] = {}
    if access == "disabled":
        monkeypatch.setattr(settings, "ENABLE_QB_PROXY", False)
        headers = {
            "Authorization": f"Bearer {create_access_token({'sub': str(owners[0].id)})}"
        }
    elif access == "invalid_allowlist":
        monkeypatch.setattr(settings, "QB_ALLOWED_USER_IDS", "7,,invalid")
        headers = {
            "Authorization": f"Bearer {create_access_token({'sub': str(owners[0].id)})}"
        }
    elif access == "not_allowlisted":
        headers = {
            "Authorization": f"Bearer {create_access_token({'sub': str(owners[1].id)})}"
        }

    method, path = _REST_ROUTES[action]
    before = await _business_snapshot(db_session)
    response = await api_client.request(method, path, headers=headers, json=arguments)
    assert response.status_code in {401, 403}
    assert factory.clients == []
    assert factory.configurations == []
    assert factory.calls == []
    assert factory.write_calls == []
    assert await _business_snapshot(db_session) == before


@pytest.mark.api
@pytest.mark.integration
@pytest.mark.parametrize("action", _ACTIONS)
async def test_media_rest_writes_preserve_routes_and_sql_idempotency_replay(
    action: str, api_client, db_session, monkeypatch
) -> None:
    from app.core.config import settings

    owners = await _seed_users(db_session)
    assert owners[0].id is not None and owners[1].id is not None
    monkeypatch.setattr(
        settings, "QB_ALLOWED_USER_IDS", f"{owners[0].id},{owners[1].id}"
    )
    factory = _RecordingQBFactory()
    _configure_qb(monkeypatch, factory)
    key = f"rest-{action}-{uuid4().hex}"
    arguments = _arguments(action, key)
    before = await _business_snapshot(db_session)

    first = await _rest_call(api_client, owners[0], action, arguments)
    assert first.status_code == 200, first.text
    first_body = first.json()
    assert first_body["idempotency_status"] == "executed"
    assert first_body["status"] == "succeeded"
    assert isinstance(first_body["message"], str)
    assert _SYNTHETIC_PASSWORD not in first.text
    assert factory.write_calls == [
        {
            "add_rss_feed": "rss_add_feed",
            "upsert_rss_feed": "rss_add_feed",
            "remove_rss_feed": "rss_remove_item",
            "set_rss_rule": "rss_set_rule",
            "remove_rss_rule": "rss_remove_rule",
        }[action]
    ]

    scope = _rest_scope(action, owners[0].id, arguments)
    run_id = _rest_run_id(scope, key)
    run_row = await db_session.get(AgentRun, run_id)
    assert run_row is not None
    assert run_row.thread_id == scope
    assert run_row.goal_hash is not None
    assert run_row.status == "succeeded"
    invocations = (
        (
            await db_session.execute(
                select(AgentInvocation).where(AgentInvocation.run_id == run_id)
            )
        )
        .scalars()
        .all()
    )
    assert len(invocations) == 1
    assert invocations[0].idempotency_key == key
    result_events = (
        (
            await db_session.execute(
                select(AgentRunEvent).where(
                    AgentRunEvent.run_id == run_id,
                    AgentRunEvent.event_type == "idempotency.result",
                )
            )
        )
        .scalars()
        .all()
    )
    assert len(result_events) == 1

    replay = await _rest_call(api_client, owners[0], action, arguments)
    assert replay.status_code == 200, replay.text
    replay_body = replay.json()
    assert replay_body["idempotency_status"] == "replayed"
    assert {
        key: value for key, value in replay_body.items() if key != "idempotency_status"
    } == {
        key: value for key, value in first_body.items() if key != "idempotency_status"
    }
    assert factory.write_calls == [
        {
            "add_rss_feed": "rss_add_feed",
            "upsert_rss_feed": "rss_add_feed",
            "remove_rss_feed": "rss_remove_item",
            "set_rss_rule": "rss_set_rule",
            "remove_rss_rule": "rss_remove_rule",
        }[action]
    ]
    assert await _business_snapshot(db_session) == before


@pytest.mark.api
@pytest.mark.integration
@pytest.mark.parametrize("action", ["add_rss_feed", "upsert_rss_feed", "set_rss_rule"])
async def test_media_rest_same_key_changed_payload_conflicts_without_second_write(
    action: str, api_client, db_session, monkeypatch
) -> None:
    from app.core.config import settings

    owner, _ = await _seed_users(db_session)
    assert owner.id is not None
    monkeypatch.setattr(settings, "QB_ALLOWED_USER_IDS", str(owner.id))
    factory = _RecordingQBFactory()
    _configure_qb(monkeypatch, factory)
    key = f"rest-conflict-{uuid4().hex}"
    original = _arguments(action, key)
    changed = _arguments(action, key, url="https://feeds.example.invalid/changed.xml")
    if action == "set_rss_rule":
        changed["rule"]["priority"] = 2

    first = await _rest_call(api_client, owner, action, original)
    assert first.status_code == 200, first.text
    before_conflict = await _business_snapshot(db_session)
    conflict = await _rest_call(api_client, owner, action, changed)
    assert conflict.status_code == 409, conflict.text
    assert conflict.json()["error_code"] == "idempotency_conflict"
    assert factory.write_calls == [
        "rss_set_rule" if action == "set_rss_rule" else "rss_add_feed"
    ]
    assert await _business_snapshot(db_session) == before_conflict


@pytest.mark.api
@pytest.mark.integration
@pytest.mark.parametrize(
    ("fault", "operation", "status_code", "error_code"),
    [
        ("login", "auth_log_in", 401, "qb_authentication_failed"),
        ("login_http4", "auth_log_in", 502, "qb_request_rejected"),
        ("login_http5", "auth_log_in", 502, "qb_server_error"),
        ("http4", "rss_add_feed", 502, "qb_request_rejected"),
        ("http5", "rss_add_feed", 409, "operation_state_unknown"),
    ],
)
async def test_media_rest_write_faults_are_safe_and_sql_key_is_not_reexecuted(
    fault: str,
    operation: str,
    status_code: int,
    error_code: str,
    api_client,
    db_session,
    monkeypatch,
) -> None:
    import qbittorrentapi

    from app.core.config import settings

    owner, _ = await _seed_users(db_session)
    assert owner.id is not None
    monkeypatch.setattr(settings, "QB_ALLOWED_USER_IDS", str(owner.id))
    factory = _RecordingQBFactory()
    error_class = {
        "login": qbittorrentapi.LoginFailed,
        "login_http4": qbittorrentapi.HTTP4XXError,
        "login_http5": qbittorrentapi.HTTP5XXError,
        "http4": qbittorrentapi.HTTP4XXError,
        "http5": qbittorrentapi.HTTP5XXError,
    }[fault]
    factory.failure = (operation, error_class(_RAW_ERROR))
    _configure_qb(monkeypatch, factory)
    arguments = _arguments("add_rss_feed", f"fault-{uuid4().hex}")

    first = await _rest_call(api_client, owner, "add_rss_feed", arguments)
    assert first.status_code == status_code, first.text
    body = first.json()
    assert body["error_code"] == error_code
    assert body["retryable"] is False
    assert _RAW_ERROR not in first.text
    assert _SYNTHETIC_PASSWORD not in first.text
    expected_writes = (
        [] if fault in {"login", "login_http4", "login_http5"} else ["rss_add_feed"]
    )
    assert factory.write_calls == expected_writes
    first_client_count = len(factory.clients)
    assert first_client_count == 1

    replay = await _rest_call(api_client, owner, "add_rss_feed", arguments)
    assert replay.status_code == status_code
    assert replay.json()["error_code"] == error_code
    assert _RAW_ERROR not in replay.text
    assert factory.write_calls == expected_writes
    assert len(factory.clients) == first_client_count


@pytest.mark.api
@pytest.mark.integration
async def test_media_rest_post_write_connection_uncertainty_is_attention_and_not_retried(
    api_client, db_session, monkeypatch
) -> None:
    import qbittorrentapi

    from app.core.config import settings

    owner, _ = await _seed_users(db_session)
    assert owner.id is not None
    monkeypatch.setattr(settings, "QB_ALLOWED_USER_IDS", str(owner.id))
    factory = _RecordingQBFactory()
    factory.failure = (
        "rss_add_feed",
        qbittorrentapi.APIConnectionError(_RAW_ERROR),
    )
    _configure_qb(monkeypatch, factory)
    arguments = _arguments("add_rss_feed", f"unknown-{uuid4().hex}")

    first = await _rest_call(api_client, owner, "add_rss_feed", arguments)
    assert first.status_code == 409, first.text
    assert first.json()["status"] == "attention_required"
    assert first.json()["retryable"] is False
    assert _RAW_ERROR not in first.text
    assert factory.write_calls == ["rss_add_feed"]

    replay = await _rest_call(api_client, owner, "add_rss_feed", arguments)
    assert replay.status_code == 409, replay.text
    assert replay.json()["status"] == "attention_required"
    assert factory.write_calls == ["rss_add_feed"]
    assert len(factory.clients) == 1


@pytest.mark.api
@pytest.mark.integration
async def test_media_agent_idempotency_replay_and_payload_conflict_use_sql_store(
    api_client, db_session, monkeypatch, tmp_path
) -> None:
    from app.core.config import settings

    owner, _ = await _seed_users(db_session)
    assert owner.id is not None
    monkeypatch.setattr(settings, "QB_ALLOWED_USER_IDS", str(owner.id))
    factory = _RecordingQBFactory()
    _configure_qb(monkeypatch, factory)
    key = f"agent-idempotency-{uuid4().hex}"
    arguments = _arguments("add_rss_feed", key)

    headers, thread_id, run_id, _, _ = await _start_approved_action(
        api_client,
        monkeypatch,
        owner,
        "add_rss_feed",
        arguments,
        tmp_path / "agent-idempotency-first.db",
    )
    first = await api_client.post(
        "/api/v1/chat/resume",
        params=_resume_params(thread_id, run_id, "approve"),
        headers=headers,
    )
    assert first.status_code == 200, first.text
    assert factory.write_calls == ["rss_add_feed"]

    replay_headers, replay_thread, replay_run, _, _ = await _start_approved_action(
        api_client,
        monkeypatch,
        owner,
        "add_rss_feed",
        arguments,
        tmp_path / "agent-idempotency-replay.db",
    )
    replay = await api_client.post(
        "/api/v1/chat/resume",
        params=_resume_params(replay_thread, replay_run, "approve"),
        headers=replay_headers,
    )
    assert replay.status_code == 200, replay.text
    replay_ends = [
        frame
        for frame in _frames(replay.text)
        if frame.get("_event_type") == "tool_call_end"
        and frame.get("status") == "succeeded"
    ]
    assert len(replay_ends) == 1
    assert factory.write_calls == ["rss_add_feed"]

    changed_arguments = _arguments(
        "add_rss_feed",
        key,
        url="https://feeds.example.invalid/changed.xml",
    )
    (
        conflict_headers,
        conflict_thread,
        conflict_run,
        _,
        _,
    ) = await _start_approved_action(
        api_client,
        monkeypatch,
        owner,
        "add_rss_feed",
        changed_arguments,
        tmp_path / "agent-idempotency-conflict.db",
    )
    conflict = await api_client.post(
        "/api/v1/chat/resume",
        params=_resume_params(conflict_thread, conflict_run, "approve"),
        headers=conflict_headers,
    )
    assert conflict.status_code == 200, conflict.text
    conflict_ends = [
        frame
        for frame in _frames(conflict.text)
        if frame.get("_event_type") == "tool_call_end"
    ]
    assert len(conflict_ends) == 1
    assert conflict_ends[0]["status"] == "denied"
    assert conflict_ends[0]["error_code"] == "idempotency_conflict"
    assert factory.write_calls == ["rss_add_feed"]


@pytest.mark.api
@pytest.mark.integration
async def test_media_agent_post_write_connection_uncertainty_replays_attention_once(
    api_client, db_session, monkeypatch, tmp_path
) -> None:
    import qbittorrentapi

    from app.core.config import settings

    owner, _ = await _seed_users(db_session)
    assert owner.id is not None
    monkeypatch.setattr(settings, "QB_ALLOWED_USER_IDS", str(owner.id))
    factory = _RecordingQBFactory()
    factory.failure = (
        "rss_add_feed",
        qbittorrentapi.APIConnectionError(_RAW_ERROR),
    )
    _configure_qb(monkeypatch, factory)
    key = f"agent-unknown-{uuid4().hex}"
    arguments = _arguments("add_rss_feed", key)
    before = await _business_snapshot(db_session)

    headers, thread_id, run_id, _, _ = await _start_approved_action(
        api_client,
        monkeypatch,
        owner,
        "add_rss_feed",
        arguments,
        tmp_path / "agent-unknown-first.db",
    )
    first = await api_client.post(
        "/api/v1/chat/resume",
        params=_resume_params(thread_id, run_id, "approve"),
        headers=headers,
    )
    assert first.status_code == 200, first.text
    first_frames = _frames(first.text)
    first_ends = [
        frame for frame in first_frames if frame.get("_event_type") == "tool_call_end"
    ]
    assert len(first_ends) == 1
    assert first_ends[0]["status"] == "failed"
    assert first_ends[0]["error_code"] == "attention_required"
    assert first_ends[0]["retryable"] is False
    assert _RAW_ERROR not in json.dumps(first_frames, ensure_ascii=False)
    assert factory.write_calls == ["rss_add_feed"]

    retry_headers, retry_thread, retry_run, _, _ = await _start_approved_action(
        api_client,
        monkeypatch,
        owner,
        "add_rss_feed",
        arguments,
        tmp_path / "agent-unknown-retry.db",
    )
    retry = await api_client.post(
        "/api/v1/chat/resume",
        params=_resume_params(retry_thread, retry_run, "approve"),
        headers=retry_headers,
    )
    assert retry.status_code == 200, retry.text
    retry_ends = [
        frame
        for frame in _frames(retry.text)
        if frame.get("_event_type") == "tool_call_end"
    ]
    assert len(retry_ends) == 1
    assert retry_ends[0]["status"] == "failed"
    assert retry_ends[0]["error_code"] == "attention_required"
    assert retry_ends[0]["retryable"] is False
    assert _RAW_ERROR not in retry.text
    assert factory.write_calls == ["rss_add_feed"]
    assert len(factory.clients) == 1
    assert await _business_snapshot(db_session) == before


@pytest.mark.api
@pytest.mark.integration
async def test_media_write_approval_projection_redacts_feed_url_credentials(
    api_client, db_session, monkeypatch, tmp_path
) -> None:
    from app.core.config import settings

    owner, _ = await _seed_users(db_session)
    assert owner.id is not None
    monkeypatch.setattr(settings, "QB_ALLOWED_USER_IDS", str(owner.id))
    factory = _RecordingQBFactory()
    _configure_qb(monkeypatch, factory)
    secrets = ("approval-feed-user", "approval-feed-password", "approval-feed-token")
    secret_url = (
        "https://approval-feed-user:approval-feed-password@feeds.example.invalid/rss"
        "?token=approval-feed-token"
    )
    _, _, frames, _ = await _chat(
        api_client,
        monkeypatch,
        owner,
        "add_rss_feed",
        _arguments("add_rss_feed", f"approval-secret-{uuid4().hex}", url=secret_url),
        tmp_path / "approval-secret.db",
    )
    approvals = [
        frame for frame in frames if frame.get("_event_type") == "approval_required"
    ]
    assert len(approvals) == 1
    run_id = _run_id(frames)
    evidence = json.dumps(frames, ensure_ascii=False)
    run_events = (
        (
            await db_session.execute(
                select(AgentRunEvent).where(AgentRunEvent.run_id == run_id)
            )
        )
        .scalars()
        .all()
    )
    evidence += json.dumps([event.payload for event in run_events], ensure_ascii=False)
    assert all(secret not in evidence for secret in secrets)
    assert secret_url not in evidence
    assert factory.clients == []

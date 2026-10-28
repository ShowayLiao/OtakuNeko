"""HTTP/JWT and direct SQL certification for Recommendation and Stats actions."""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, replace
from pathlib import Path
from types import ModuleType
from typing import Any
from uuid import uuid4

import pytest
from sqlmodel import col, select

from app.core.security import create_access_token
from app.harness.model_types import ModelCallResult
from app.models import Collection, CollectionStatus, Subject, SubjectType, User
from app.models.agent_run import AgentInvocation, AgentRun
from app.models.agent_trace import AgentTraceModel


_CHAT_PATH = "/api/v1/chat"
_RUN_PATH = "/api/v1/runs/{run_id}"
_EVENTS_PATH = "/api/v1/runs/{run_id}/events"
_TRACE_PATH = "/api/v1/trace/{trace_id}"
_SYNTHETIC_API_KEY = "synthetic-test-key"
_HTTP_EVIDENCE = (
    Path(__file__).resolve().parents[2]
    / ".runtime/capability-contracts/profile-stats-http.json"
)
_ACTIONS = (
    ("recommendation", "generate_user_profile_tool"),
    ("recommendation", "analyse_taste"),
    ("stats", "get_user_stats"),
    ("stats", "get_collection_statistics"),
)
_ANIME_STATUSES = (
    (CollectionStatus.COLLECT, CollectionStatus.DO, CollectionStatus.ON_HOLD),
    (CollectionStatus.WISH, CollectionStatus.DROPPED),
)


@dataclass(frozen=True)
class _OwnerData:
    user_id: int
    anime_subject_ids: tuple[int, ...]
    all_subject_ids: tuple[int, ...]
    anime_count: int
    rated_count: int
    topic: str
    anime_rate: int
    book_subject_id: int | None = None


@dataclass
class _GatewayCalls:
    constructors: int = 0
    inferences: int = 0
    decision_ids: list[str] | None = None

    def record_decision(self, decision_id: str) -> None:
        if self.decision_ids is None:
            self.decision_ids = []
        self.decision_ids.append(decision_id)


def _gateway_for(
    capability: str,
    arguments: dict[str, Any],
    calls: _GatewayCalls,
) -> type:
    """Return a deterministic provider-boundary double for one HTTP run."""

    class _FakeGateway:
        def __init__(self, **kwargs: Any) -> None:
            calls.constructors += 1
            self.model = str(kwargs["model"])
            self._proposed = False

        async def infer(self, **kwargs: Any) -> ModelCallResult:
            del kwargs
            calls.inferences += 1
            decision_id = f"profile-stats-{uuid4().hex}"
            calls.record_decision(decision_id)
            if not self._proposed:
                self._proposed = True
                decision = {
                    "schema_version": "v1",
                    "decision_id": decision_id,
                    "action": "invoke",
                    "capability": capability,
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


def _forged_collections() -> list[dict[str, Any]]:
    """Model-proposed data has no runtime identity and must not replace SQL."""
    return [
        {
            "subject": {
                "id": 990_001 + index,
                "name": f"model-forged-subject-{index}",
                "tags": [{"name": "model-forged-topic"}],
            },
            "collection": {"rate": 10},
        }
        for index in range(2)
    ]


async def _seed(db) -> tuple[list[_OwnerData], list[User]]:
    suffix = uuid4().hex[:12]
    users = [
        User(username=f"profile-stats-owner-{label}-{suffix}") for label in ("a", "b")
    ]
    db.add_all(users)
    await db.commit()

    owners: list[_OwnerData] = []
    specs = (
        (3, 9, "owner-a-topic", True),
        (2, 5, "owner-b-topic", False),
    )
    for owner_index, (user, spec) in enumerate(zip(users, specs, strict=True)):
        anime_count, rate, topic, has_book = spec
        assert user.id is not None
        subject_ids: list[int] = []
        anime_ids: list[int] = []
        for index in range(anime_count):
            subject = Subject(
                source="bangumi",
                source_id=f"profile-stats-{suffix}-{owner_index}-anime-{index}",
                name=f"Synthetic {topic} anime {index}",
                type=SubjectType.ANIME,
                tags=[{"name": topic}],
                meta_tags=[],
            )
            db.add(subject)
            await db.flush()
            assert subject.id is not None
            anime_ids.append(subject.id)
            subject_ids.append(subject.id)
            db.add(
                Collection(
                    user_id=user.id,
                    source=subject.source,
                    source_id=subject.source_id,
                    type=_ANIME_STATUSES[owner_index][index],
                    rate=rate,
                    private=True,
                    subject_type=int(SubjectType.ANIME),
                )
            )

        book_subject_id: int | None = None
        if has_book:
            subject = Subject(
                source="bangumi",
                source_id=f"profile-stats-{suffix}-{owner_index}-book",
                name="Synthetic owner A book",
                type=SubjectType.BOOK,
                tags=[{"name": "owner-a-book-topic"}],
                meta_tags=[],
            )
            db.add(subject)
            await db.flush()
            assert subject.id is not None
            book_subject_id = subject.id
            subject_ids.append(subject.id)
            db.add(
                Collection(
                    user_id=user.id,
                    source=subject.source,
                    source_id=subject.source_id,
                    type=CollectionStatus.COLLECT,
                    rate=9,
                    private=True,
                    subject_type=int(SubjectType.BOOK),
                )
            )

        owners.append(
            _OwnerData(
                user_id=user.id,
                anime_subject_ids=tuple(anime_ids),
                all_subject_ids=tuple(subject_ids),
                anime_count=anime_count,
                rated_count=anime_count + int(has_book),
                topic=topic,
                anime_rate=rate,
                book_subject_id=book_subject_id,
            )
        )

    await db.commit()
    return owners, users


async def _business_snapshot(db) -> dict[str, list[dict[str, Any]]]:
    """Snapshot business rows only; Run and Trace persistence is expected."""
    subjects = (
        (
            await db.execute(
                select(Subject)
                .order_by(Subject.source, Subject.source_id)
                .execution_options(populate_existing=True)
            )
        )
        .scalars()
        .all()
    )
    collections = (
        (
            await db.execute(
                select(Collection)
                .order_by(
                    col(Collection.user_id),
                    col(Collection.source),
                    col(Collection.source_id),
                )
                .execution_options(populate_existing=True)
            )
        )
        .scalars()
        .all()
    )
    return {
        "subjects": [subject.model_dump(mode="json") for subject in subjects],
        "collections": [
            collection.model_dump(mode="json") for collection in collections
        ],
    }


def _write_evidence(runs: list[dict[str, Any]]) -> None:
    _HTTP_EVIDENCE.parent.mkdir(parents=True, exist_ok=True)
    _HTTP_EVIDENCE.write_text(
        json.dumps(
            {
                "source": "real HTTP/JWT + Runtime + real SQL/domain services",
                "runs": runs,
                "successful_run_count": len(runs),
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


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
            elif line.startswith("data:"):
                data_lines.append(line.removeprefix("data:").strip())
        if data_lines:
            frame["data"] = json.loads("\n".join(data_lines))
        frames.append(frame)
    return frames


def _auth(user_id: int) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token({'sub': str(user_id)})}"}


def _assert_profile(profile: dict[str, Any], owner: _OwnerData, other: _OwnerData):
    summary = profile["llm_summary"]
    assert set(profile["watched_ids"]) == set(owner.all_subject_ids)
    assert summary["total_rated"] == owner.rated_count
    assert summary["total_rated_items"] == owner.rated_count
    assert summary["taste_dictionary"][owner.topic] == [
        owner.anime_count,
        float(owner.anime_rate),
    ]
    assert other.topic not in summary["taste_dictionary"]
    assert "model-forged-topic" not in summary["taste_dictionary"]


def _assert_recommendation_output(
    action: str,
    output: dict[str, Any],
    owner: _OwnerData,
    other: _OwnerData,
) -> None:
    if action == "generate_user_profile_tool":
        _assert_profile(output["profile"], owner, other)
        return

    chart_tags = {entry["name"] for entry in output["chart_data"]["bar_count"]}
    quadrant_tags = {tag for values in output["quadrants"].values() for tag in values}
    assert owner.topic in chart_tags
    assert other.topic not in chart_tags | quadrant_tags
    assert "model-forged-topic" not in chart_tags | quadrant_tags
    assert output["evidence"]["total_tags_analysed"] == 1
    if owner.anime_rate >= 7.5:
        assert owner.topic in output["quadrants"]["core_favorites"]


def _assert_stats_output(
    action: str,
    output: dict[str, Any],
    owner: _OwnerData,
    *,
    subject_type: int = int(SubjectType.ANIME),
) -> None:
    if action == "get_user_stats":
        stats = output["stats"]
        expected = {
            "anime": owner.anime_count,
            "books": int(owner.book_subject_id is not None),
            "music": 0,
            "games": 0,
            "real": 0,
            "total": owner.rated_count,
        }
        assert stats == expected
        return

    statistics = output["statistics"]
    assert statistics["subject_type"] == subject_type
    if subject_type == int(SubjectType.BOOK):
        assert owner.book_subject_id is not None
        assert statistics["total"] == 1
        assert statistics["top_genres"] == [{"name": "owner-a-book-topic", "count": 1}]
        assert statistics["status_counts"]["watched"] == 1
        return

    assert statistics["total"] == owner.anime_count
    assert statistics["top_genres"] == [
        {"name": owner.topic, "count": owner.anime_count}
    ]
    assert statistics["genre_subject_count"] == owner.anime_count
    assert statistics["genre_complete"] is True
    expected_statuses = (
        {"wish": 0, "watched": 1, "watching": 1, "on_hold": 1, "dropped": 0}
        if owner.topic == "owner-a-topic"
        else {"wish": 1, "watched": 0, "watching": 0, "on_hold": 0, "dropped": 1}
    )
    assert statistics["status_counts"] == expected_statuses


async def _run_http_action(
    *,
    action: str,
    arguments: dict[str, Any],
    owner_index: int,
    owners: list[_OwnerData],
    users: list[User],
    api_client,
    db,
    monkeypatch,
    gateway_calls: _GatewayCalls,
    evidence: list[dict[str, Any]],
) -> dict[str, Any]:
    from app.api.v1 import agent as agent_api

    owner = owners[owner_index]
    other = owners[1 - owner_index]
    user = users[owner_index]
    assert user.id == owner.user_id
    before = await _business_snapshot(db)
    inferences_before = gateway_calls.inferences
    monkeypatch.setattr(
        agent_api,
        "OpenAIModelGateway",
        _gateway_for(
            action,
            arguments,
            gateway_calls,
        ),
    )
    response = await api_client.post(
        _CHAT_PATH,
        headers={
            **_auth(owner.user_id),
            "X-Api-Key": _SYNTHETIC_API_KEY,
        },
        json={
            "model": "synthetic-model",
            "messages": [{"role": "user", "content": "Read my profile and stats."}],
        },
    )
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    frames = _sse_frames(response.text)
    terminal = [frame for frame in frames if frame.get("event") == "run_completed"]
    tool_ends = [frame for frame in frames if frame.get("event") == "tool_call_end"]
    model_calls = [frame for frame in frames if frame.get("event") == "model_call"]
    assert terminal, json.dumps(frames, indent=2)
    assert len(tool_ends) == 1
    assert len(model_calls) == gateway_calls.inferences - inferences_before
    assert all(frame["data"]["durable"] is True for frame in frames)
    invocation_result = tool_ends[0]["data"]
    assert invocation_result["status"] == "succeeded", invocation_result
    output = invocation_result["output"]
    run_id = terminal[-1]["data"]["run_id"]

    run_response = await api_client.get(
        _RUN_PATH.format(run_id=run_id), headers=_auth(owner.user_id)
    )
    assert run_response.status_code == 200
    assert run_response.json()["status"] == "succeeded"
    run_row = (
        await db.execute(select(AgentRun).where(AgentRun.run_id == run_id))
    ).scalar_one()
    assert run_row.status == "succeeded"
    assert run_row.user_id == owner.user_id

    events_response = await api_client.get(
        _EVENTS_PATH.format(run_id=run_id), headers=_auth(owner.user_id)
    )
    assert events_response.status_code == 200
    event_types = [event["event_type"] for event in events_response.json()["events"]]
    assert event_types[-1] == "run.succeeded"
    invocation = (
        await db.execute(
            select(AgentInvocation).where(AgentInvocation.run_id == run_id)
        )
    ).scalar_one()
    assert invocation.status == "succeeded"
    assert invocation.capability == action

    trace_response = await api_client.get(
        _TRACE_PATH.format(trace_id=run_id), headers=_auth(owner.user_id)
    )
    assert trace_response.status_code == 200
    assert trace_response.json()["trace_id"] == run_id
    assert trace_response.json()["user_id"] == owner.user_id
    trace_row = (
        await db.execute(
            select(AgentTraceModel).where(AgentTraceModel.trace_id == run_id)
        )
    ).scalar_one()
    assert trace_row.user_id == owner.user_id

    for path in (
        _RUN_PATH.format(run_id=run_id),
        _TRACE_PATH.format(trace_id=run_id),
    ):
        foreign_response = await api_client.get(path, headers=_auth(other.user_id))
        assert foreign_response.status_code == 404

    after = await _business_snapshot(db)
    assert after == before
    evidence.append(
        {
            "action": action,
            "owner": f"owner_{owner_index}",
            "run_id": run_id,
            "run_status": run_response.json()["status"],
            "invocation_status": invocation.status,
            "model_call_events": len(model_calls),
            "trace_owner_matches": True,
            "foreign_run_and_trace_reads": 404,
        }
    )
    _write_evidence(evidence)
    return output


@pytest.mark.api
@pytest.mark.integration
async def test_profile_and_stats_http_actions_use_owned_sql_and_are_read_only(
    api_client, db_session, monkeypatch
):
    from app.core.config import settings

    _HTTP_EVIDENCE.unlink(missing_ok=True)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setattr(settings, "HARNESS_CHECKPOINT_ADAPTER", "disabled")
    owners, users = await _seed(db_session)
    gateway_calls = _GatewayCalls()
    evidence: list[dict[str, Any]] = []

    for capability, action in _ACTIONS:
        for owner_index, owner in enumerate(owners):
            arguments: dict[str, Any] = {}
            if capability == "recommendation":
                arguments["collections"] = _forged_collections()
            output = await _run_http_action(
                action=action,
                arguments=arguments,
                owner_index=owner_index,
                owners=owners,
                users=users,
                api_client=api_client,
                db=db_session,
                monkeypatch=monkeypatch,
                gateway_calls=gateway_calls,
                evidence=evidence,
            )
            if capability == "recommendation":
                _assert_recommendation_output(
                    action, output, owner, owners[1 - owner_index]
                )
            else:
                _assert_stats_output(action, output, owner)

            if action == "get_user_stats" and owner_index == 0:
                hot_output = await _run_http_action(
                    action=action,
                    arguments={},
                    owner_index=owner_index,
                    owners=owners,
                    users=users,
                    api_client=api_client,
                    db=db_session,
                    monkeypatch=monkeypatch,
                    gateway_calls=gateway_calls,
                    evidence=evidence,
                )
                assert hot_output["stats"] == output["stats"]

    book_output = await _run_http_action(
        action="get_collection_statistics",
        arguments={"subject_type": int(SubjectType.BOOK)},
        owner_index=0,
        owners=owners,
        users=users,
        api_client=api_client,
        db=db_session,
        monkeypatch=monkeypatch,
        gateway_calls=gateway_calls,
        evidence=evidence,
    )
    _assert_stats_output(
        "get_collection_statistics",
        book_output,
        owners[0],
        subject_type=int(SubjectType.BOOK),
    )

    assert len(evidence) == len(_ACTIONS) * len(owners) + 2
    decision_ids = gateway_calls.decision_ids or []
    assert gateway_calls.constructors == len(evidence)
    assert gateway_calls.inferences == sum(
        item["model_call_events"] for item in evidence
    )
    assert len(decision_ids) == len(set(decision_ids))


async def _run_http_failure_or_timeout(
    *,
    action: str,
    owner_index: int,
    outcome: str,
    owners: list[_OwnerData],
    users: list[User],
    api_client,
    db,
    monkeypatch,
    gateway_calls: _GatewayCalls,
) -> None:
    """Exercise real owned SQL reads followed by Dispatcher failure/deadline."""
    from app.api.v1 import agent as agent_api
    from app.capabilities import recommendation as recommendation_capability
    from app.capabilities import stats as stats_capability
    from app.capabilities.recommendation import RecommendationCapability
    from app.capabilities.stats import StatsCapability

    assert outcome in {"failure", "timeout"}
    owner = owners[owner_index]
    other = owners[1 - owner_index]
    user = users[owner_index]
    assert user.id == owner.user_id
    before = await _business_snapshot(db)

    service_module: ModuleType
    capability_class: Any
    if action in {"generate_user_profile_tool", "analyse_taste"}:
        service_module = recommendation_capability
        service_name = "get_user_collections"
        capability_class = RecommendationCapability
        arguments: dict[str, Any] = {"collections": _forged_collections()}
    elif action == "get_user_stats":
        service_module = stats_capability
        service_name = "get_user_stats"
        capability_class = StatsCapability
        arguments = {}
    else:
        assert action == "get_collection_statistics"
        service_module = stats_capability
        service_name = "get_collection_statistics"
        capability_class = StatsCapability
        arguments = {"subject_type": int(SubjectType.ANIME)}

    real_service = getattr(service_module, service_name)
    service_calls = 0
    sql_read_completed = asyncio.Event()
    cancellation_cleaned_up = asyncio.Event()
    fault_wait_returned = asyncio.Event()

    async def read_then_fault(*args: Any, **kwargs: Any) -> Any:
        nonlocal service_calls
        service_calls += 1
        result = await real_service(*args, **kwargs)
        sql_read_completed.set()
        if outcome == "failure":
            raise RuntimeError("synthetic post-read service failure")
        try:
            await asyncio.Event().wait()
            fault_wait_returned.set()
            return result
        finally:
            cancellation_cleaned_up.set()

    monkeypatch.setattr(service_module, service_name, read_then_fault)

    if outcome == "timeout":
        original_actions = capability_class.actions

        def actions_with_short_deadline(capability) -> list[Any]:
            return [
                replace(descriptor, timeout_seconds=0.1)
                if descriptor.public_name == action
                else descriptor
                for descriptor in original_actions(capability)
            ]

        monkeypatch.setattr(capability_class, "actions", actions_with_short_deadline)

    monkeypatch.setattr(
        agent_api,
        "OpenAIModelGateway",
        _gateway_for(action, arguments, gateway_calls),
    )
    response = await api_client.post(
        _CHAT_PATH,
        headers={
            **_auth(owner.user_id),
            "X-Api-Key": _SYNTHETIC_API_KEY,
        },
        json={
            "model": "synthetic-model",
            "messages": [{"role": "user", "content": "Read my profile and stats."}],
        },
    )
    assert response.status_code == 200
    frames = _sse_frames(response.text)
    expected_terminal = "run_timeout" if outcome == "timeout" else "run_failed"
    terminal_types = {
        "run_completed",
        "run_failed",
        "run_cancelled",
        "run_timeout",
    }
    terminals = [frame for frame in frames if frame.get("event") in terminal_types]
    assert [frame.get("event") for frame in terminals] == [expected_terminal]
    tool_ends = [frame for frame in frames if frame.get("event") == "tool_call_end"]
    assert len(tool_ends) == 1
    invocation_result = tool_ends[0]["data"]
    expected_invocation_status = "timeout" if outcome == "timeout" else "failed"
    assert invocation_result["status"] == expected_invocation_status
    run_id = terminals[0]["data"]["run_id"]

    assert service_calls == 1
    assert sql_read_completed.is_set()
    if outcome == "timeout":
        assert cancellation_cleaned_up.is_set()
        assert not fault_wait_returned.is_set()
        await asyncio.sleep(0)
        assert service_calls == 1

    run_response = await api_client.get(
        _RUN_PATH.format(run_id=run_id), headers=_auth(owner.user_id)
    )
    assert run_response.status_code == 200
    assert run_response.json()["status"] == "failed"
    run_row = (
        await db.execute(select(AgentRun).where(AgentRun.run_id == run_id))
    ).scalar_one()
    assert run_row.status == "failed"
    assert run_row.user_id == owner.user_id

    events_response = await api_client.get(
        _EVENTS_PATH.format(run_id=run_id), headers=_auth(owner.user_id)
    )
    assert events_response.status_code == 200
    event_types = [event["event_type"] for event in events_response.json()["events"]]
    terminal_event_types = {
        "run.succeeded",
        "run.failed",
        "run.cancelled",
        "run.paused",
    }
    assert event_types.count("run.failed") == 1
    assert event_types[-1] == "run.failed"
    assert sum(event_type in terminal_event_types for event_type in event_types) == 1

    invocation = (
        await db.execute(
            select(AgentInvocation).where(AgentInvocation.run_id == run_id)
        )
    ).scalar_one()
    assert invocation.status == ("timed_out" if outcome == "timeout" else "failed")
    assert invocation.capability == action

    trace_response = await api_client.get(
        _TRACE_PATH.format(trace_id=run_id), headers=_auth(owner.user_id)
    )
    assert trace_response.status_code == 200
    assert trace_response.json()["user_id"] == owner.user_id
    trace_row = (
        await db.execute(
            select(AgentTraceModel).where(AgentTraceModel.trace_id == run_id)
        )
    ).scalar_one()
    assert trace_row.user_id == owner.user_id

    for path in (
        _RUN_PATH.format(run_id=run_id),
        _TRACE_PATH.format(trace_id=run_id),
    ):
        foreign_response = await api_client.get(path, headers=_auth(other.user_id))
        assert foreign_response.status_code == 404

    assert await _business_snapshot(db) == before


@pytest.mark.api
@pytest.mark.integration
@pytest.mark.parametrize("outcome", ["failure", "timeout"])
@pytest.mark.parametrize("capability,action", _ACTIONS)
async def test_profile_and_stats_http_faults_preserve_business_rows(
    capability,
    action,
    outcome,
    api_client,
    db_session,
    monkeypatch,
):
    from app.core.config import settings

    assert (capability == "recommendation") == (
        action in {"generate_user_profile_tool", "analyse_taste"}
    )
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setattr(settings, "HARNESS_CHECKPOINT_ADAPTER", "disabled")
    owners, users = await _seed(db_session)
    await _run_http_failure_or_timeout(
        action=action,
        owner_index=0,
        outcome=outcome,
        owners=owners,
        users=users,
        api_client=api_client,
        db=db_session,
        monkeypatch=monkeypatch,
        gateway_calls=_GatewayCalls(),
    )


@pytest.mark.postgres
@pytest.mark.integration
async def test_postgres_profile_and_stats_capabilities_read_owned_data_without_writes(
    postgres_session, initialized_cache
):
    from app.capabilities.recommendation import RecommendationCapability
    from app.capabilities.stats import StatsCapability

    owners, _ = await _seed(postgres_session)
    recommendation = RecommendationCapability()
    stats = StatsCapability()

    for owner_index, owner in enumerate(owners):
        other = owners[1 - owner_index]
        for action in ("generate_profile", "analyse_taste"):
            before = await _business_snapshot(postgres_session)
            result = await recommendation.execute(
                action,
                db=postgres_session,
                user_id=owner.user_id,
                collections=_forged_collections(),
            )
            assert result["success"] is True, result
            if action == "generate_profile":
                _assert_profile(result["profile"], owner, other)
            else:
                _assert_recommendation_output("analyse_taste", result, owner, other)
            assert await _business_snapshot(postgres_session) == before

        for action in ("get_user_stats", "get_collection_statistics"):
            before = await _business_snapshot(postgres_session)
            result = await stats.execute(
                action,
                db=postgres_session,
                user_id=owner.user_id,
            )
            assert result["success"] is True, result
            _assert_stats_output(action, result, owner)
            assert await _business_snapshot(postgres_session) == before

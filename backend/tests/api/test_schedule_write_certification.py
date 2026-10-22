"""Real JWT/chat, approval, SQL, REST, and idempotency certification for schedule writes."""

from __future__ import annotations

import asyncio
from dataclasses import replace
from datetime import datetime, time, timezone
import hashlib
import json
from typing import Any
from uuid import uuid4

import pytest
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.security import create_access_token
from app.harness.model_types import ModelCallResult
from app.models import (
    AnimeBroadcastMetadata,
    Collection,
    Schedule,
    Subject,
    User,
)
from app.models.agent_run import AgentInvocation, AgentRun, AgentRunEvent
from app.models.enums import CollectionStatus, SubjectType, WatchType


ACTIONS = (
    "create_schedule",
    "update_schedule",
    "delete_schedule",
    "upsert_schedule",
    "bulk_upsert_schedules",
    "sync_bangumi_schedule",
)
SERVICE_METHODS = {
    "create_schedule": "create_schedule",
    "update_schedule": "update_schedule",
    "delete_schedule": "delete_schedule",
    "upsert_schedule": "upsert_schedule",
    "bulk_upsert_schedules": "bulk_upsert_schedules",
    "sync_bangumi_schedule": "sync_bangumi_calendar",
}
SOURCE = "bangumi"
SHARED_SOURCE_ID = "schedule-shared-501"
SYNC_SUBJECT_ID = 97400621
PRIVATE_COMMENTS = ("private-schedule-owner-a", "private-schedule-owner-b")
PRIVATE_TAGS = ("schedule-owner-a-tag", "schedule-owner-b-tag")
SENTINEL_ERROR = "synthetic-private-schedule-write-fault"


def _frames(text: str) -> list[dict[str, Any]]:
    event_type = "message"
    frames = []
    for line in text.splitlines():
        if line.startswith("event:"):
            event_type = line[6:].strip()
        elif line.startswith("data:"):
            frame = json.loads(line[5:].strip())
            frame["_event_type"] = event_type
            frames.append(frame)
    return frames


def _calendar_payload(subject_id: int) -> list[dict[str, Any]]:
    return [
        {
            "weekday": {"id": weekday},
            "items": (
                [
                    {
                        "id": subject_id,
                        "name": "Synthetic schedule calendar subject",
                        "name_cn": "Synthetic calendar title",
                        "type": 2,
                        "air_date": datetime.now(timezone.utc).date().isoformat(),
                        "air_weekday": weekday,
                    }
                ]
                if weekday == 4
                else []
            ),
        }
        for weekday in range(1, 8)
    ]


def _install_calendar_http(external_http: Any) -> None:
    external_http.respond(
        "GET",
        "https://api.bgm.tv/calendar",
        json=_calendar_payload(SYNC_SUBJECT_ID),
    )


async def _seed(
    db: AsyncSession,
) -> tuple[User, User, Schedule, Schedule]:
    suffix = uuid4().hex[:10]
    owner = User(username=f"schedule-write-owner-a-{suffix}")
    foreign = User(username=f"schedule-write-owner-b-{suffix}")
    db.add_all([owner, foreign])
    await db.commit()
    assert owner.id is not None and foreign.id is not None

    broadcast_at = datetime.now(timezone.utc).replace(
        hour=9, minute=30, second=0, microsecond=0
    )
    metadata = AnimeBroadcastMetadata(
        bangumi_id=SYNC_SUBJECT_ID,
        title="Synthetic broadcast metadata",
        broadcast_begin=broadcast_at,
        broadcast_tz="Asia/Tokyo",
        year=broadcast_at.year,
        season=((broadcast_at.month - 1) // 3) * 3 + 1,
    )
    subject = Subject(
        source=SOURCE,
        source_id=SHARED_SOURCE_ID,
        name="Shared schedule subject",
        type=SubjectType.ANIME,
    )
    owner_schedule = Schedule(
        user_id=owner.id,
        source=SOURCE,
        source_id=SHARED_SOURCE_ID,
        day_of_week=1,
        start_time=time(19, 30),
        watch_day=5,
        watch_time=time(21, 0),
        duration=7,
        watch_type=WatchType.NEW,
    )
    foreign_schedule = Schedule(
        user_id=foreign.id,
        source=SOURCE,
        source_id=SHARED_SOURCE_ID,
        day_of_week=1,
        start_time=time(20, 30),
        watch_day=6,
        watch_time=time(22, 0),
        duration=8,
        watch_type=WatchType.NEW,
    )
    collections = [
        Collection(
            user_id=user.id,
            source=SOURCE,
            source_id=SHARED_SOURCE_ID,
            type=CollectionStatus.DO,
            subject_type=int(SubjectType.ANIME),
            private=True,
            comment=PRIVATE_COMMENTS[index],
            rate=8 + index,
            tags=[PRIVATE_TAGS[index]],
        )
        for index, user in enumerate((owner, foreign))
    ]
    db.add_all([metadata, subject, owner_schedule, foreign_schedule, *collections])
    await db.commit()
    await db.refresh(owner_schedule)
    await db.refresh(foreign_schedule)
    assert owner_schedule.id is not None and foreign_schedule.id is not None
    return owner, foreign, owner_schedule, foreign_schedule


async def _business_snapshot(db: AsyncSession) -> dict[str, list[dict[str, Any]]]:
    schedules = (
        await db.execute(
            select(Schedule)
            .order_by(col(Schedule.user_id), col(Schedule.id))
            .execution_options(populate_existing=True)
        )
    ).scalars()
    subjects = (
        await db.execute(
            select(Subject)
            .order_by(col(Subject.source), col(Subject.source_id))
            .execution_options(populate_existing=True)
        )
    ).scalars()
    collections = (
        await db.execute(
            select(Collection)
            .order_by(
                col(Collection.user_id),
                col(Collection.source),
                col(Collection.source_id),
            )
            .execution_options(populate_existing=True)
        )
    ).scalars()
    metadata = (
        await db.execute(
            select(AnimeBroadcastMetadata)
            .order_by(col(AnimeBroadcastMetadata.bangumi_id))
            .execution_options(populate_existing=True)
        )
    ).scalars()
    return {
        "schedules": [item.model_dump(mode="json") for item in schedules],
        "subjects": [item.model_dump(mode="json") for item in subjects],
        "collections": [item.model_dump(mode="json") for item in collections],
        "anime_broadcast_metadata": [item.model_dump(mode="json") for item in metadata],
    }


def _arguments(
    action: str,
    owner_schedule_id: int,
    *,
    key: str | None = None,
) -> dict[str, Any]:
    idempotency_key = key or f"schedule-write-{uuid4().hex}"
    if action == "create_schedule":
        return {
            "source": SOURCE,
            "source_id": f"sc{uuid4().hex[:8]}",
            "day_of_week": 3,
            "start_time": "18:45:00",
            "watch_day": 4,
            "watch_time": "20:10:00",
            "duration": 7,
            "watch_type": int(WatchType.NEW),
            "idempotency_key": idempotency_key,
        }
    if action == "update_schedule":
        return {
            "schedule_id": owner_schedule_id,
            "day_of_week": 2,
            "start_time": "22:15:00",
            "watch_day": 3,
            "watch_time": "23:00:00",
            "duration": 9,
            "watch_type": int(WatchType.LEISURE),
            "idempotency_key": idempotency_key,
        }
    if action == "delete_schedule":
        return {
            "schedule_id": owner_schedule_id,
            "idempotency_key": idempotency_key,
        }
    if action == "upsert_schedule":
        return {
            "source": SOURCE,
            "source_id": f"su{uuid4().hex[:8]}",
            "day_of_week": 4,
            "start_time": "20:15:00",
            "watch_day": 4,
            "watch_time": "21:15:00",
            "duration": 8,
            "watch_type": int(WatchType.NEW),
            "idempotency_key": idempotency_key,
        }
    if action == "bulk_upsert_schedules":
        return {
            "items": [
                {
                    "source": SOURCE,
                    "source_id": f"sb{uuid4().hex[:8]}",
                    "day_of_week": 5,
                    "start_time": "17:00:00",
                    "watch_day": 5,
                    "watch_time": "18:00:00",
                    "duration": 7,
                    "watch_type": int(WatchType.NEW),
                },
                {
                    "source": SOURCE,
                    "source_id": f"sb{uuid4().hex[:8]}",
                    "day_of_week": 6,
                    "start_time": "18:00:00",
                    "watch_day": 6,
                    "watch_time": "19:00:00",
                    "duration": 7,
                    "watch_type": int(WatchType.NEW),
                },
            ],
            "idempotency_key": idempotency_key,
        }
    if action == "sync_bangumi_schedule":
        return {"idempotency_key": idempotency_key}
    raise AssertionError(f"Unknown action {action}")


def _gateway(
    action: str,
    arguments: dict[str, Any],
    decision_ids: list[str],
    gateway_calls: list[int],
):
    class Gateway:
        def __init__(self, **kwargs: Any) -> None:
            self.model = kwargs["model"]

        async def infer(self, **kwargs: Any) -> ModelCallResult:
            del kwargs
            gateway_calls.append(len(gateway_calls) + 1)
            decision_id = uuid4().hex
            decision_ids.append(decision_id)
            decision: dict[str, Any] = {
                "schema_version": "v1",
                "decision_id": decision_id,
            }
            if len(gateway_calls) == 1:
                decision.update(
                    action="invoke",
                    capability=action,
                    capability_version="v1",
                    arguments=arguments,
                )
            else:
                decision.update(action="respond", content="Synthetic completion")
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

    return Gateway


async def _chat(
    api_client: Any,
    owner: User,
    action: str,
    arguments: dict[str, Any],
    checkpoint_path: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[dict[str, str], str, list[dict[str, Any]], list[str], list[int]]:
    from app.api.v1 import agent as agent_api
    from app.core.config import settings

    assert owner.id is not None
    decision_ids: list[str] = []
    gateway_calls: list[int] = []
    monkeypatch.setattr(settings, "HARNESS_CHECKPOINT_ADAPTER", "sqlite")
    monkeypatch.setattr(settings, "CHECKPOINT_DB_PATH", str(checkpoint_path))
    monkeypatch.setattr(
        agent_api,
        "OpenAIModelGateway",
        _gateway(action, arguments, decision_ids, gateway_calls),
    )
    thread_id = f"schedule-write-{action}-{uuid4().hex}"
    headers = {
        "Authorization": f"Bearer {create_access_token({'sub': str(owner.id)})}",
        "X-Api-Key": "synthetic-test-key",
    }
    response = await api_client.post(
        "/api/v1/chat",
        headers=headers,
        json={
            "model": "synthetic-model",
            "thread_id": thread_id,
            "messages": [{"role": "user", "content": "Update my synthetic schedule"}],
        },
    )
    assert response.status_code == 200, response.text
    frames = _frames(response.text)
    assert len(decision_ids) == len(set(decision_ids))
    return headers, thread_id, frames, decision_ids, gateway_calls


def _resume_params(thread_id: str, run_id: str, decision: str) -> dict[str, str]:
    return {"thread_id": thread_id, "run_id": run_id, "decision": decision}


async def _read_run(api_client: Any, run_id: str, headers: dict[str, str]):
    response = await api_client.get(f"/api/v1/runs/{run_id}", headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


def _run_id_from_frames(frames: list[dict[str, Any]]) -> str:
    run_ids = {frame.get("run_id") for frame in frames if frame.get("run_id")}
    assert len(run_ids) == 1, json.dumps(frames, indent=2)
    return str(run_ids.pop())


def _assert_schedule_result(action: str, output: dict[str, Any], owner_id: int) -> None:
    assert output.get("success") is True
    encoded = json.dumps(output, allow_nan=False)
    assert PRIVATE_COMMENTS[0] not in encoded
    assert PRIVATE_COMMENTS[1] not in encoded
    assert PRIVATE_TAGS[0] not in encoded
    assert PRIVATE_TAGS[1] not in encoded
    if action in {"create_schedule", "update_schedule", "upsert_schedule"}:
        schedule = output["schedule"]
        assert schedule["user_id"] == owner_id
        assert isinstance(schedule["id"], int)
        assert schedule["source"] == SOURCE
        assert isinstance(schedule["source_id"], str)
        assert 0 <= schedule["day_of_week"] <= 6
    elif action == "delete_schedule":
        assert output.get("deleted") is True
    elif action == "bulk_upsert_schedules":
        schedules = output["schedules"]
        assert output["count"] == len(schedules)
        assert len(schedules) == 3
        assert all(item["user_id"] == owner_id for item in schedules)
    elif action == "sync_bangumi_schedule":
        schedules = output["schedules"]
        assert output["count"] == len(schedules) == 1
        item = schedules[0]
        assert item["collection"] is None
        assert item["subject"]["id"] == 0
        assert item["subject"]["source"] == SOURCE
        assert item["subject"]["source_id"] == str(SYNC_SUBJECT_ID)
        assert item["subject"]["name"] == "Synthetic schedule calendar subject"
    else:
        raise AssertionError(f"Unknown action {action}")


def _assert_business_write(
    action: str,
    arguments: dict[str, Any],
    owner_id: int,
    foreign_id: int,
    before: dict[str, list[dict[str, Any]]],
    after: dict[str, list[dict[str, Any]]],
) -> None:
    before_owner = [row for row in before["schedules"] if row["user_id"] == owner_id]
    after_owner = [row for row in after["schedules"] if row["user_id"] == owner_id]
    before_foreign = [
        row for row in before["schedules"] if row["user_id"] == foreign_id
    ]
    after_foreign = [row for row in after["schedules"] if row["user_id"] == foreign_id]
    assert before_foreign == after_foreign

    if action == "sync_bangumi_schedule":
        assert after["schedules"] == before["schedules"]
        assert after["collections"] == before["collections"]
        assert after["anime_broadcast_metadata"] == before["anime_broadcast_metadata"]
        before_subjects = {row["source_id"] for row in before["subjects"]}
        after_subjects = {row["source_id"] for row in after["subjects"]}
        assert after_subjects == before_subjects | {str(SYNC_SUBJECT_ID)}
        subject = next(
            row for row in after["subjects"] if row["source_id"] == str(SYNC_SUBJECT_ID)
        )
        assert subject["name"] == "Synthetic schedule calendar subject"
        return

    assert after["subjects"] == before["subjects"]
    assert after["collections"] == before["collections"]
    assert after["anime_broadcast_metadata"] == before["anime_broadcast_metadata"]
    schedule_id = arguments.get("schedule_id")
    if action == "create_schedule":
        matches = [
            row for row in after_owner if row["source_id"] == arguments["source_id"]
        ]
        assert len(matches) == 1
        assert len(after_owner) == len(before_owner) + 1
        assert matches[0]["day_of_week"] == arguments["day_of_week"]
    elif action == "update_schedule":
        updated = next(row for row in after_owner if row["id"] == schedule_id)
        assert len(after_owner) == len(before_owner)
        assert updated["day_of_week"] == arguments["day_of_week"]
        assert updated["start_time"] == arguments["start_time"]
    elif action == "delete_schedule":
        assert all(row["id"] != schedule_id for row in after_owner)
        assert len(after_owner) == len(before_owner) - 1
    elif action == "upsert_schedule":
        matches = [
            row for row in after_owner if row["source_id"] == arguments["source_id"]
        ]
        assert len(matches) == 1
        assert len(after_owner) == len(before_owner) + 1
    elif action == "bulk_upsert_schedules":
        source_ids = {item["source_id"] for item in arguments["items"]}
        assert source_ids.issubset({row["source_id"] for row in after_owner})
        assert len(after_owner) == len(before_owner) + len(source_ids)
    else:
        raise AssertionError(f"Unknown action {action}")


async def _assert_success_run_records(
    api_client: Any,
    db: AsyncSession,
    *,
    run_id: str,
    owner: User,
    foreign: User,
    action: str,
) -> None:
    assert owner.id is not None and foreign.id is not None
    owner_headers = {
        "Authorization": f"Bearer {create_access_token({'sub': str(owner.id)})}"
    }
    run = await _read_run(api_client, run_id, owner_headers)
    assert run["status"] == "succeeded"

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
    assert invocation.status == "succeeded"
    assert invocation.finished_at is not None

    events = (
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
    assert len({event.sequence for event in events}) == len(events)
    terminal = [
        event
        for event in events
        if event.event_type in {"run.succeeded", "run.failed", "run.cancelled"}
    ]
    assert len(terminal) == 1
    assert terminal[0].event_type == "run.succeeded"
    tool_ends = [
        event
        for event in events
        if event.event_type == "tool_call_end"
        and event.invocation_id == invocation.invocation_id
        and event.payload.get("status") == "succeeded"
    ]
    assert len(tool_ends) == 1

    trace = await api_client.get(f"/api/v1/trace/{run_id}", headers=owner_headers)
    assert trace.status_code == 200
    assert trace.json()["user_id"] == owner.id
    foreign_headers = {
        "Authorization": f"Bearer {create_access_token({'sub': str(foreign.id)})}"
    }
    for path in (f"/api/v1/runs/{run_id}", f"/api/v1/trace/{run_id}"):
        assert (await api_client.get(path, headers=foreign_headers)).status_code == 404


def _track_service(action: str, monkeypatch: pytest.MonkeyPatch) -> list[str]:
    from app.services.schedule_service import ScheduleService

    method_name = SERVICE_METHODS[action]
    real_service = getattr(ScheduleService, method_name)
    calls: list[str] = []

    async def tracked_service(*args: Any, **kwargs: Any) -> Any:
        calls.append(action)
        return await real_service(*args, **kwargs)

    monkeypatch.setattr(ScheduleService, method_name, tracked_service)
    return calls


def _install_after_service_fault(
    action: str,
    fault: str,
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[list[str], dict[str, bool]]:
    from app.services.schedule_service import ScheduleService

    method_name = SERVICE_METHODS[action]
    real_service = getattr(ScheduleService, method_name)
    calls: list[str] = []
    state = {"entered": False, "real_service_returned": False, "finalized": False}

    async def fault_after_real_service(*args: Any, **kwargs: Any) -> Any:
        calls.append(action)
        state["entered"] = True
        try:
            result = await real_service(*args, **kwargs)
            state["real_service_returned"] = True
            if fault == "raise":
                raise RuntimeError(SENTINEL_ERROR)
            await asyncio.Event().wait()
            return result
        finally:
            state["finalized"] = True

    monkeypatch.setattr(ScheduleService, method_name, fault_after_real_service)
    if fault == "timeout":
        from app.capabilities.schedule import ScheduleCapability

        original_actions = ScheduleCapability.actions

        def short_timeout_actions(self: Any):
            return [
                replace(item, timeout_seconds=0.2) if item.name == action else item
                for item in original_actions(self)
            ]

        monkeypatch.setattr(ScheduleCapability, "actions", short_timeout_actions)
    return calls, state


@pytest.mark.api
@pytest.mark.integration
@pytest.mark.parametrize("action", ACTIONS)
async def test_schedule_write_http_approval_certification(
    action: str,
    api_client: Any,
    db_session: AsyncSession,
    external_http: Any,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Any,
) -> None:
    from app.capabilities.factory import build_capability_registry

    owner, foreign, owner_schedule, _ = await _seed(db_session)
    assert owner.id is not None and foreign.id is not None
    assert owner_schedule.id is not None
    registry = build_capability_registry()
    descriptor_owner = registry.find_action(action)
    assert descriptor_owner is not None
    capability, descriptor = descriptor_owner
    assert capability.name == "schedule"
    assert descriptor.public_name == action
    assert descriptor.version == "v1"
    assert descriptor.requires_auth is True
    assert descriptor.is_side_effect is True
    assert descriptor.approval_required is True
    assert descriptor.risk_level == "medium"
    assert descriptor.idempotency_mode == "required"

    service_calls = _track_service(action, monkeypatch)
    arguments = _arguments(action, owner_schedule.id)
    if action == "sync_bangumi_schedule":
        _install_calendar_http(external_http)
    before = await _business_snapshot(db_session)
    headers, thread_id, initial_frames, decision_ids, gateway_calls = await _chat(
        api_client,
        owner,
        action,
        arguments,
        tmp_path / f"{action}-approval-checkpoint.db",
        monkeypatch,
    )
    approval_frames = [
        frame
        for frame in initial_frames
        if frame.get("_event_type") == "approval_required"
    ]
    assert len(approval_frames) == 1, json.dumps(initial_frames, indent=2)
    approval = approval_frames[0]
    assert approval["capability"] == action
    run_id = _run_id_from_frames(initial_frames)
    assert approval["run_id"] == run_id
    assert await _business_snapshot(db_session) == before
    assert service_calls == []
    assert external_http.requests == []
    paused_run = await _read_run(api_client, run_id, headers)
    assert paused_run["status"] == "paused"

    foreign_headers = {
        "Authorization": f"Bearer {create_access_token({'sub': str(foreign.id)})}"
    }
    hidden = await api_client.post(
        "/api/v1/chat/resume",
        params=_resume_params(thread_id, run_id, "approve"),
        headers=foreign_headers,
    )
    assert hidden.status_code == 404
    assert await _business_snapshot(db_session) == before
    continued = await api_client.post(
        "/api/v1/chat/resume",
        params=_resume_params(thread_id, run_id, "continue"),
        headers=headers,
    )
    assert continued.status_code == 409
    assert await _read_run(api_client, run_id, headers) == paused_run
    assert await _business_snapshot(db_session) == before
    assert service_calls == []

    approved = await api_client.post(
        "/api/v1/chat/resume",
        params=_resume_params(thread_id, run_id, "approve"),
        headers=headers,
    )
    assert approved.status_code == 200, approved.text
    approved_frames = _frames(approved.text)
    successful_ends = [
        frame
        for frame in approved_frames
        if frame.get("_event_type") == "tool_call_end"
        and frame.get("status") == "succeeded"
    ]
    assert len(successful_ends) == 1, json.dumps(approved_frames, indent=2)
    end = successful_ends[0]
    assert end["capability"] == action
    _assert_schedule_result(action, end["output"], owner.id)
    assert service_calls == [action]
    if action == "sync_bangumi_schedule":
        assert [
            (request.method, str(request.url)) for request in external_http.requests
        ] == [("GET", "https://api.bgm.tv/calendar")]
    else:
        assert external_http.requests == []

    after = await _business_snapshot(db_session)
    _assert_business_write(action, arguments, owner.id, foreign.id, before, after)
    await _assert_success_run_records(
        api_client,
        db_session,
        run_id=run_id,
        owner=owner,
        foreign=foreign,
        action=action,
    )
    assert len(decision_ids) == len(set(decision_ids))
    assert len(gateway_calls) >= 1

    repeated_approval = await api_client.post(
        "/api/v1/chat/resume",
        params=_resume_params(thread_id, run_id, "approve"),
        headers=headers,
    )
    assert repeated_approval.status_code == 409
    assert (await _read_run(api_client, run_id, headers))["status"] == "succeeded"
    assert await _business_snapshot(db_session) == after
    assert service_calls == [action]
    assert len(external_http.requests) == (
        1 if action == "sync_bangumi_schedule" else 0
    )

    reject_arguments = _arguments(
        action, owner_schedule.id, key=f"schedule-reject-{uuid4().hex}"
    )
    reject_headers, reject_thread, reject_initial, _, _ = await _chat(
        api_client,
        owner,
        action,
        reject_arguments,
        tmp_path / f"{action}-reject-checkpoint.db",
        monkeypatch,
    )
    reject_run_id = _run_id_from_frames(reject_initial)
    assert any(
        frame.get("_event_type") == "approval_required" for frame in reject_initial
    )
    assert await _business_snapshot(db_session) == after
    rejected = await api_client.post(
        "/api/v1/chat/resume",
        params=_resume_params(reject_thread, reject_run_id, "reject"),
        headers=reject_headers,
    )
    assert rejected.status_code == 200, rejected.text
    rejected_frames = _frames(rejected.text)
    assert any(frame.get("_event_type") == "run_failed" for frame in rejected_frames)
    assert (await _read_run(api_client, reject_run_id, reject_headers))[
        "status"
    ] == "failed"
    assert await _business_snapshot(db_session) == after
    assert service_calls == [action]
    assert len(external_http.requests) == (
        1 if action == "sync_bangumi_schedule" else 0
    )


@pytest.mark.api
@pytest.mark.integration
@pytest.mark.parametrize("action", ACTIONS)
@pytest.mark.parametrize("fault", ["raise", "timeout"])
async def test_schedule_write_post_service_fault_reserves_unknown_key(
    action: str,
    fault: str,
    api_client: Any,
    db_session: AsyncSession,
    external_http: Any,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Any,
) -> None:
    owner, foreign, owner_schedule, _ = await _seed(db_session)
    assert owner.id is not None and foreign.id is not None
    assert owner_schedule.id is not None
    arguments = _arguments(action, owner_schedule.id)
    if action == "sync_bangumi_schedule":
        _install_calendar_http(external_http)
    service_calls, fault_state = _install_after_service_fault(
        action, fault, monkeypatch
    )
    before = await _business_snapshot(db_session)
    checkpoint = tmp_path / f"{action}-{fault}-checkpoint.db"
    headers, thread_id, initial_frames, _, _ = await _chat(
        api_client, owner, action, arguments, checkpoint, monkeypatch
    )
    run_id = _run_id_from_frames(initial_frames)
    assert any(
        frame.get("_event_type") == "approval_required" for frame in initial_frames
    )
    assert await _business_snapshot(db_session) == before
    assert service_calls == []
    approved = await api_client.post(
        "/api/v1/chat/resume",
        params=_resume_params(thread_id, run_id, "approve"),
        headers=headers,
    )
    assert approved.status_code == 200, approved.text
    first_frames = _frames(approved.text)
    first_ends = [
        frame for frame in first_frames if frame.get("_event_type") == "tool_call_end"
    ]
    assert len(first_ends) == 1
    assert first_ends[0]["status"] == ("timeout" if fault == "timeout" else "failed")
    assert SENTINEL_ERROR not in json.dumps(first_ends)
    assert fault_state == {
        "entered": True,
        "real_service_returned": True,
        "finalized": True,
    }
    assert service_calls == [action]
    first_run = await _read_run(api_client, run_id, headers)
    assert first_run["status"] == "failed"
    after_fault = await _business_snapshot(db_session)
    _assert_business_write(action, arguments, owner.id, foreign.id, before, after_fault)

    if action == "sync_bangumi_schedule":
        assert [
            (request.method, str(request.url)) for request in external_http.requests
        ] == [("GET", "https://api.bgm.tv/calendar")]
    else:
        assert external_http.requests == []

    retry_headers, retry_thread, retry_initial, _, _ = await _chat(
        api_client, owner, action, arguments, checkpoint, monkeypatch
    )
    retry_run_id = _run_id_from_frames(retry_initial)
    assert any(
        frame.get("_event_type") == "approval_required" for frame in retry_initial
    )
    retry = await api_client.post(
        "/api/v1/chat/resume",
        params=_resume_params(retry_thread, retry_run_id, "approve"),
        headers=retry_headers,
    )
    assert retry.status_code == 200, retry.text
    retry_frames = _frames(retry.text)
    retry_ends = [
        frame for frame in retry_frames if frame.get("_event_type") == "tool_call_end"
    ]
    assert len(retry_ends) == 1
    assert retry_ends[0]["status"] == "failed"
    assert retry_ends[0]["output"]["error_type"] == "attention_required"
    assert SENTINEL_ERROR not in json.dumps(retry_ends)
    assert service_calls == [action]
    assert await _business_snapshot(db_session) == after_fault
    assert len(external_http.requests) == (
        1 if action == "sync_bangumi_schedule" else 0
    )


def _rest_arguments(
    action: str,
    owner_schedule_id: int,
    *,
    key: str | None = None,
) -> dict[str, Any]:
    values = _arguments(action, owner_schedule_id, key=key)
    if action == "create_schedule":
        values.pop("idempotency_key")
        return values
    values.pop("idempotency_key")
    return values


async def _rest_call(
    api_client: Any,
    owner: User,
    foreign: User,
    action: str,
    arguments: dict[str, Any],
    key: str,
    *,
    authenticated: bool = True,
) -> Any:
    assert owner.id is not None and foreign.id is not None
    headers = {
        "X-Api-Key": "synthetic-test-key",
        "Idempotency-Key": key,
    }
    if authenticated:
        headers["Authorization"] = (
            f"Bearer {create_access_token({'sub': str(owner.id)})}"
        )
    values = dict(arguments)
    if action == "create_schedule":
        method, path = "POST", "/api/v1/schedules/"
        body = {"user_id": foreign.id, **values}
    elif action == "update_schedule":
        schedule_id = values.pop("schedule_id")
        method, path = "PUT", f"/api/v1/schedules/{schedule_id}"
        body = values
    elif action == "delete_schedule":
        schedule_id = values["schedule_id"]
        method, path, body = "DELETE", f"/api/v1/schedules/{schedule_id}", None
    elif action == "upsert_schedule":
        method, path = "POST", "/api/v1/schedules/upsert"
        body = {"user_id": foreign.id, **values}
    elif action == "bulk_upsert_schedules":
        method, path = "POST", "/api/v1/schedules/bulk-upsert"
        body = {
            "items": [{"user_id": foreign.id, **item} for item in values.pop("items")]
        }
    elif action == "sync_bangumi_schedule":
        method, path, body = "POST", "/api/v1/schedules/sync-bangumi", None
    else:
        raise AssertionError(f"Unknown action {action}")
    return await api_client.request(method, path, headers=headers, json=body)


def _rest_scope(action: str, owner_id: int, arguments: dict[str, Any]) -> str:
    if action == "create_schedule":
        return f"{owner_id}:schedule:schedule:collection"
    if action in {"update_schedule", "delete_schedule"}:
        return f"{owner_id}:schedule:schedule:{arguments['schedule_id']}"
    if action == "upsert_schedule":
        return f"{owner_id}:schedule:upsert:{arguments.get('id') or 'collection'}"
    if action == "bulk_upsert_schedules":
        return f"{owner_id}:schedule:bulk_upsert:collection"
    if action == "sync_bangumi_schedule":
        return f"{owner_id}:schedule:sync_bangumi:calendar"
    raise AssertionError(f"Unknown action {action}")


def _idempotency_run_id(scope: str, key: str) -> str:
    canonical = json.dumps(
        {"scope": scope, "key": key},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return f"idem-{hashlib.sha256(canonical).hexdigest()}"


async def _assert_rest_idempotency_scope(
    db: AsyncSession,
    action: str,
    owner_id: int,
    arguments: dict[str, Any],
    key: str,
) -> None:
    scope = _rest_scope(action, owner_id, arguments)
    run = await db.get(AgentRun, _idempotency_run_id(scope, key))
    assert run is not None
    assert run.thread_id == scope
    assert run.status == "succeeded"


def _rest_conflict_arguments(
    action: str, arguments: dict[str, Any]
) -> tuple[str, dict[str, Any]] | None:
    conflict = dict(arguments)
    if action == "create_schedule":
        conflict["source_id"] = f"sc{uuid4().hex[:8]}"
    elif action == "update_schedule":
        conflict["day_of_week"] = 3
    elif action == "delete_schedule":
        return (
            "update_schedule",
            {
                "schedule_id": arguments["schedule_id"],
                "day_of_week": 3,
                "start_time": "23:15:00",
            },
        )
    elif action == "upsert_schedule":
        conflict["source_id"] = f"su{uuid4().hex[:8]}"
    elif action == "bulk_upsert_schedules":
        conflict["items"] = [dict(item) for item in arguments["items"]]
        conflict["items"][0]["source_id"] = f"sb{uuid4().hex[:8]}"
    elif action == "sync_bangumi_schedule":
        return None
    return action, conflict


def _assert_rest_success(action: str, response: Any, owner_id: int) -> None:
    if action == "create_schedule":
        assert response.status_code == 201, response.text
        assert response.json()["user_id"] == owner_id
        assert response.json()["source"] == SOURCE
    elif action in {"update_schedule", "upsert_schedule"}:
        assert response.status_code == 200, response.text
        assert response.json()["user_id"] == owner_id
        assert isinstance(response.json()["id"], int)
    elif action == "delete_schedule":
        assert response.status_code == 200, response.text
        assert response.json() == {
            "status": "success",
            "message": "排班记录删除成功",
        }
    elif action == "bulk_upsert_schedules":
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["total"] == len(body["items"]) == 3
        assert all(item["user_id"] == owner_id for item in body["items"])
    elif action == "sync_bangumi_schedule":
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["total"] == len(body["items"]) == 1
        assert body["items"][0]["collection"] is None
        assert body["items"][0]["subject"]["id"] == 0
        assert body["items"][0]["subject"]["source_id"] == str(SYNC_SUBJECT_ID)
    else:
        raise AssertionError(f"Unknown action {action}")


@pytest.mark.api
@pytest.mark.integration
@pytest.mark.parametrize("action", ACTIONS)
async def test_schedule_rest_routes_preserve_scope_dto_replay_and_conflict(
    action: str,
    api_client: Any,
    db_session: AsyncSession,
    external_http: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    owner, foreign, owner_schedule, _ = await _seed(db_session)
    assert owner.id is not None and foreign.id is not None
    assert owner_schedule.id is not None
    calls = _track_service(action, monkeypatch)
    arguments = _rest_arguments(action, owner_schedule.id)
    key = f"rest-schedule-{uuid4().hex}"
    if action == "sync_bangumi_schedule":
        _install_calendar_http(external_http)

    first = await _rest_call(api_client, owner, foreign, action, arguments, key)
    _assert_rest_success(action, first, owner.id)
    assert calls == [action]
    await _assert_rest_idempotency_scope(db_session, action, owner.id, arguments, key)
    first_snapshot = await _business_snapshot(db_session)

    replay = await _rest_call(api_client, owner, foreign, action, arguments, key)
    _assert_rest_success(action, replay, owner.id)
    assert replay.json() == first.json()
    assert calls == [action]
    assert await _business_snapshot(db_session) == first_snapshot

    conflict_request = _rest_conflict_arguments(action, arguments)
    if conflict_request is not None:
        conflict_action, conflict_arguments = conflict_request
        conflict = await _rest_call(
            api_client, owner, foreign, conflict_action, conflict_arguments, key
        )
        assert conflict.status_code == 409, conflict.text
        assert calls == [action]
        assert await _business_snapshot(db_session) == first_snapshot

    if action == "sync_bangumi_schedule":
        assert [
            (request.method, str(request.url)) for request in external_http.requests
        ] == [("GET", "https://api.bgm.tv/calendar")]
    else:
        assert external_http.requests == []


@pytest.mark.api
@pytest.mark.integration
@pytest.mark.parametrize("action", ACTIONS)
async def test_schedule_rest_writes_require_auth_and_enforce_owner(
    action: str,
    api_client: Any,
    db_session: AsyncSession,
    external_http: Any,
) -> None:
    owner, foreign, owner_schedule, foreign_schedule = await _seed(db_session)
    assert owner.id is not None and foreign.id is not None
    assert owner_schedule.id is not None and foreign_schedule.id is not None
    arguments = _rest_arguments(action, owner_schedule.id)
    before = await _business_snapshot(db_session)
    unauthenticated = await _rest_call(
        api_client,
        owner,
        foreign,
        action,
        arguments,
        f"unauthenticated-{uuid4().hex}",
        authenticated=False,
    )
    assert unauthenticated.status_code == 401
    assert await _business_snapshot(db_session) == before
    assert external_http.requests == []

    if action in {"update_schedule", "delete_schedule"}:
        foreign_arguments = _rest_arguments(action, foreign_schedule.id)
        response = await _rest_call(
            api_client,
            owner,
            foreign,
            action,
            foreign_arguments,
            f"foreign-owner-{uuid4().hex}",
        )
        assert response.status_code == 404, response.text
        assert await _business_snapshot(db_session) == before


@pytest.mark.api
@pytest.mark.integration
@pytest.mark.parametrize("action", ACTIONS)
async def test_schedule_rest_post_commit_failure_keeps_old_key_unknown(
    action: str,
    api_client: Any,
    db_session: AsyncSession,
    external_http: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    owner, foreign, owner_schedule, _ = await _seed(db_session)
    assert owner.id is not None and foreign.id is not None
    assert owner_schedule.id is not None
    arguments = _rest_arguments(action, owner_schedule.id)
    key = f"rest-schedule-unknown-{uuid4().hex}"
    if action == "sync_bangumi_schedule":
        _install_calendar_http(external_http)
    calls, state = _install_after_service_fault(action, "raise", monkeypatch)
    before = await _business_snapshot(db_session)

    first = await _rest_call(api_client, owner, foreign, action, arguments, key)
    assert first.status_code >= 400, first.text
    assert SENTINEL_ERROR not in first.text
    assert state == {
        "entered": True,
        "real_service_returned": True,
        "finalized": True,
    }
    assert calls == [action]
    after = await _business_snapshot(db_session)
    _assert_business_write(action, arguments, owner.id, foreign.id, before, after)

    replay = await _rest_call(api_client, owner, foreign, action, arguments, key)
    assert replay.status_code >= 400, replay.text
    assert SENTINEL_ERROR not in replay.text
    assert calls == [action]
    assert await _business_snapshot(db_session) == after
    if action == "sync_bangumi_schedule":
        assert [
            (request.method, str(request.url)) for request in external_http.requests
        ] == [("GET", "https://api.bgm.tv/calendar")]
    else:
        assert external_http.requests == []

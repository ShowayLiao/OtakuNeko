"""HTTP/JWT -> Runtime/Dispatcher -> owned schedule reads over real SQL."""

from __future__ import annotations

import asyncio
from dataclasses import replace
from datetime import time
import json
import re
from typing import Any
from uuid import uuid4

import pytest
from sqlmodel import col, select

from app.core.security import create_access_token
from app.harness.model_types import ModelCallResult
from app.models import Collection, Schedule, Subject, User
from app.models.agent_run import AgentInvocation, AgentRunEvent
from app.models.enums import CollectionStatus, SubjectType, WatchType


ACTIONS = (
    "list_schedules",
    "list_schedules_by_day",
    "list_unified_schedules",
)
SOURCE = "bangumi"
SHARED_SOURCE_ID = "schedule-shared-501"
ORPHAN_SOURCE_ID = "schedule-orphan-502"
PRIVATE_COMMENTS = (
    "private-owner-a-schedule-comment",
    "private-owner-b-schedule-comment",
)
PRIVATE_TAGS = ("private-owner-a-tag", "private-owner-b-tag")
SENTINEL_ERROR = "synthetic schedule read fault detail"


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


def _gateway(action: str, arguments: dict[str, Any], decision_ids: list[str]):
    class Gateway:
        def __init__(self, **kwargs):
            self.model = kwargs["model"]
            self.calls = 0

        async def infer(self, **kwargs):
            self.calls += 1
            decision_id = uuid4().hex
            decision_ids.append(decision_id)
            decision: dict[str, Any] = {
                "schema_version": "v1",
                "decision_id": decision_id,
            }
            if self.calls == 1:
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

        async def close(self):
            pass

    return Gateway


async def _seed(db) -> list[User]:
    owners = [
        User(username="schedule-read-owner-a"),
        User(username="schedule-read-owner-b"),
    ]
    db.add_all(owners)
    await db.commit()

    subject = Subject(
        source=SOURCE,
        source_id=SHARED_SOURCE_ID,
        name="Shared schedule title",
        type=SubjectType.ANIME,
    )
    db.add(subject)

    for index, owner in enumerate(owners):
        db.add(
            Schedule(
                user_id=owner.id,
                source=SOURCE,
                source_id=SHARED_SOURCE_ID,
                day_of_week=2,
                start_time=time(19 + index, 30),
                watch_day=5 - index,
                watch_time=time(21 + index, 0),
                duration=7 + index,
                watch_type=WatchType.NEW,
            )
        )
        db.add(
            Collection(
                user_id=owner.id,
                source=SOURCE,
                source_id=SHARED_SOURCE_ID,
                type=CollectionStatus.DO,
                subject_type=int(SubjectType.ANIME),
                private=True,
                comment=PRIVATE_COMMENTS[index],
                rate=8 + index,
                tags=[PRIVATE_TAGS[index]],
            )
        )

    # Keep a valid schedule with no Subject or Collection to exercise the
    # existing left-join/null DTO behavior on the unified read.
    db.add(
        Schedule(
            user_id=owners[0].id,
            source=SOURCE,
            source_id=ORPHAN_SOURCE_ID,
            day_of_week=4,
            start_time=time(22, 15),
            watch_type=WatchType.LEISURE,
        )
    )
    await db.commit()
    return owners


def _arguments(action: str) -> dict[str, Any]:
    if action == "list_schedules_by_day":
        return {"day_of_week": 2}
    return {}


async def _business_snapshot(db) -> dict[str, list[dict[str, Any]]]:
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
    return {
        "schedules": [item.model_dump(mode="json") for item in schedules],
        "subjects": [item.model_dump(mode="json") for item in subjects],
        "collections": [item.model_dump(mode="json") for item in collections],
    }


async def _chat(
    api_client,
    owner: User,
    action: str,
    arguments: dict,
    monkeypatch,
    *,
    require_tool_end: bool = True,
):
    from app.api.v1 import agent as agent_api
    from app.core.config import settings

    decision_ids: list[str] = []
    monkeypatch.setattr(settings, "HARNESS_CHECKPOINT_ADAPTER", "disabled")
    monkeypatch.setattr(
        agent_api, "OpenAIModelGateway", _gateway(action, arguments, decision_ids)
    )
    headers = {
        "Authorization": f"Bearer {create_access_token({'sub': str(owner.id)})}",
        "X-Api-Key": "synthetic-test-key",
    }
    response = await api_client.post(
        "/api/v1/chat",
        headers=headers,
        json={
            "model": "synthetic-model",
            "messages": [{"role": "user", "content": "Read my schedule"}],
        },
    )
    assert response.status_code == 200, response.text
    frames = _frames(response.text)
    ends = [frame for frame in frames if frame.get("_event_type") == "tool_call_end"]
    assert len(ends) == (1 if require_tool_end else 0), json.dumps(frames, indent=2)
    assert len(decision_ids) == len(set(decision_ids))
    return headers, frames, ends[0] if ends else None


async def _assert_run_records(
    api_client,
    db,
    *,
    frames: list[dict[str, Any]],
    owner: User,
    other_owner: User,
    action: str,
    invocation_status: str,
    run_status: str,
    terminal_event: str,
):
    run_ids = {frame.get("run_id") for frame in frames if frame.get("run_id")}
    assert len(run_ids) == 1, json.dumps(frames, indent=2)
    run_id = run_ids.pop()
    owner_headers = {
        "Authorization": f"Bearer {create_access_token({'sub': str(owner.id)})}"
    }
    run_response = await api_client.get(f"/api/v1/runs/{run_id}", headers=owner_headers)
    assert run_response.status_code == 200
    assert run_response.json()["status"] == run_status

    invocation = (
        await db.execute(
            select(AgentInvocation).where(AgentInvocation.run_id == run_id)
        )
    ).scalar_one()
    assert invocation.status == invocation_status
    assert invocation.capability == action

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
    terminal = [
        event
        for event in events
        if event.event_type
        in {"run.succeeded", "run.failed", "run.cancelled", "run.abandoned"}
    ]
    assert len(terminal) == 1
    assert terminal[0].event_type == terminal_event

    trace = await api_client.get(f"/api/v1/trace/{run_id}", headers=owner_headers)
    assert trace.status_code == 200
    assert trace.json()["user_id"] == owner.id
    other_headers = {
        "Authorization": f"Bearer {create_access_token({'sub': str(other_owner.id)})}"
    }
    for path in (f"/api/v1/runs/{run_id}", f"/api/v1/trace/{run_id}"):
        assert (await api_client.get(path, headers=other_headers)).status_code == 404
    return run_id


def _assert_public_schedule(item: dict[str, Any]) -> None:
    assert isinstance(item["id"], int)
    assert item["source"] == SOURCE
    assert isinstance(item["source_id"], str)
    assert 0 <= item["day_of_week"] <= 6
    assert re.fullmatch(r"\d{2}:\d{2}:\d{2}", item["start_time"])
    assert item.get("watch_day") is None or 0 <= item["watch_day"] <= 6
    assert "user_id" not in item


@pytest.mark.api
@pytest.mark.integration
async def test_schedule_read_http_certification(api_client, db_session, monkeypatch):
    from app.capabilities.schedule import ScheduleCapability

    owners = await _seed(db_session)
    descriptors = {item.name: item for item in ScheduleCapability().actions()}
    for action in ACTIONS:
        descriptor = descriptors[action]
        assert descriptor.public_name == action
        assert descriptor.version == "v1"
        assert descriptor.requires_auth is True
        assert descriptor.is_side_effect is False
        assert descriptor.approval_required is False
        assert descriptor.idempotency_mode == "none"

    success_runs = []
    for action in ACTIONS:
        for index, owner in enumerate(owners):
            before = await _business_snapshot(db_session)
            headers, frames, tool_end = await _chat(
                api_client, owner, action, _arguments(action), monkeypatch
            )
            assert tool_end["status"] == "succeeded", tool_end
            output = tool_end["output"]
            assert output["success"] is True
            assert type(output["count"]) is int
            assert output["count"] == len(output["schedules"])
            serialized = json.dumps(output, allow_nan=False)
            assert '"user_id"' not in serialized
            assert PRIVATE_COMMENTS[1 - index] not in serialized
            assert PRIVATE_TAGS[1 - index] not in serialized

            schedules = output["schedules"]
            expected_count = (
                2
                if owner.id == owners[0].id and action != "list_schedules_by_day"
                else 1
            )
            assert output["count"] == expected_count
            if action == "list_unified_schedules":
                shared = [
                    item
                    for item in schedules
                    if item["schedule"]["source_id"] == SHARED_SOURCE_ID
                ]
                assert len(shared) == 1
                _assert_public_schedule(shared[0]["schedule"])
                assert shared[0]["subject"]["name"] == "Shared schedule title"
                assert shared[0]["collection"]["comment"] == PRIVATE_COMMENTS[index]
                assert shared[0]["collection"]["rate"] == 8 + index
                assert shared[0]["collection"]["private"] is True
                if index == 0:
                    orphan = next(
                        item
                        for item in schedules
                        if item["schedule"]["source_id"] == ORPHAN_SOURCE_ID
                    )
                    assert orphan["subject"] is None
                    assert orphan["collection"] is None
            else:
                for item in schedules:
                    _assert_public_schedule(item)
                source_ids = {item["source_id"] for item in schedules}
                if action == "list_schedules_by_day":
                    assert all(item["day_of_week"] == 2 for item in schedules)
                    assert source_ids == {SHARED_SOURCE_ID}
                else:
                    expected_sources = {SHARED_SOURCE_ID}
                    if index == 0:
                        expected_sources.add(ORPHAN_SOURCE_ID)
                    assert source_ids == expected_sources
                    assert all(item["day_of_week"] in {2, 4} for item in schedules)

            await _assert_run_records(
                api_client,
                db_session,
                frames=frames,
                owner=owner,
                other_owner=owners[1 - index],
                action=action,
                invocation_status="succeeded",
                run_status="succeeded",
                terminal_event="run.succeeded",
            )
            assert await _business_snapshot(db_session) == before
            success_runs.append({"action": action, "owner_id": owner.id})

    assert len(success_runs) == 6


@pytest.mark.api
@pytest.mark.integration
@pytest.mark.parametrize("action", ACTIONS)
async def test_schedule_read_identity_spoof_is_refused_without_sql_reads(
    api_client, db_session, monkeypatch, action: str
):
    owners = await _seed(db_session)
    method_names = {
        "list_schedules": "get_user_schedules",
        "list_schedules_by_day": "get_schedules_by_day",
        "list_unified_schedules": "get_unified_user_schedules",
    }
    method_name = method_names[action]
    from app.services.schedule_service import ScheduleService

    real_service = getattr(ScheduleService, method_name)
    calls = []

    async def record_service_call(*args, **kwargs):
        calls.append((args, kwargs))
        return await real_service(*args, **kwargs)

    monkeypatch.setattr(ScheduleService, method_name, record_service_call)
    arguments = {**_arguments(action), "user_id": owners[1].id}
    before = await _business_snapshot(db_session)
    _, frames, tool_end = await _chat(
        api_client,
        owners[0],
        action,
        arguments,
        monkeypatch,
        require_tool_end=False,
    )
    assert tool_end is None
    assert calls == []
    serialized_frames = json.dumps(frames)
    assert all(
        value not in serialized_frames for value in (*PRIVATE_COMMENTS, *PRIVATE_TAGS)
    )
    run_ids = {frame.get("run_id") for frame in frames if frame.get("run_id")}
    assert len(run_ids) == 1
    run_id = run_ids.pop()
    owner_headers = {
        "Authorization": f"Bearer {create_access_token({'sub': str(owners[0].id)})}"
    }
    run_response = await api_client.get(f"/api/v1/runs/{run_id}", headers=owner_headers)
    assert run_response.status_code == 200
    assert run_response.json()["status"] == "failed"
    assert (
        await db_session.execute(
            select(AgentInvocation).where(AgentInvocation.run_id == run_id)
        )
    ).scalars().all() == []
    events = (
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
    terminal = [
        event
        for event in events
        if event.event_type
        in {"run.succeeded", "run.failed", "run.cancelled", "run.abandoned"}
    ]
    assert len(terminal) == 1
    assert terminal[0].event_type == "run.failed"
    trace = await api_client.get(f"/api/v1/trace/{run_id}", headers=owner_headers)
    assert trace.status_code == 200
    assert trace.json()["user_id"] == owners[0].id
    foreign_headers = {
        "Authorization": f"Bearer {create_access_token({'sub': str(owners[1].id)})}"
    }
    for path in (f"/api/v1/runs/{run_id}", f"/api/v1/trace/{run_id}"):
        assert (await api_client.get(path, headers=foreign_headers)).status_code == 404
    assert await _business_snapshot(db_session) == before


@pytest.mark.api
@pytest.mark.integration
@pytest.mark.parametrize("action", ACTIONS)
@pytest.mark.parametrize("fault", ["raise", "timeout"])
async def test_schedule_read_http_faults_are_terminal_and_read_only(
    api_client, db_session, monkeypatch, action: str, fault: str
):
    from app.capabilities.schedule import ScheduleCapability
    from app.services.schedule_service import ScheduleService

    owners = await _seed(db_session)
    owner = owners[0]
    other_owner = owners[1]
    method_names = {
        "list_schedules": "get_user_schedules",
        "list_schedules_by_day": "get_schedules_by_day",
        "list_unified_schedules": "get_unified_user_schedules",
    }
    method_name = method_names[action]
    real_service = getattr(ScheduleService, method_name)
    service_entered = False
    real_read_returned = False
    wrapper_finalized = False

    async def fault_after_real_sql(*args, **kwargs):
        nonlocal service_entered, real_read_returned, wrapper_finalized
        service_entered = True
        try:
            result = await real_service(*args, **kwargs)
            real_read_returned = True
            if fault == "raise":
                raise RuntimeError(SENTINEL_ERROR)
            await asyncio.Event().wait()
            return result
        finally:
            wrapper_finalized = True

    monkeypatch.setattr(ScheduleService, method_name, fault_after_real_sql)
    if fault == "timeout":
        actions = ScheduleCapability.actions

        def short_timeout_actions(self):
            return [
                replace(item, timeout_seconds=0.1) if item.name == action else item
                for item in actions(self)
            ]

        monkeypatch.setattr(ScheduleCapability, "actions", short_timeout_actions)

    before = await _business_snapshot(db_session)
    _, frames, tool_end = await _chat(
        api_client, owner, action, _arguments(action), monkeypatch
    )
    expected_tool_status = "timeout" if fault == "timeout" else "failed"
    expected_invocation_status = "timed_out" if fault == "timeout" else "failed"
    assert service_entered is True
    assert real_read_returned is True, tool_end
    assert wrapper_finalized is True
    assert tool_end["status"] == expected_tool_status, tool_end
    assert tool_end["_event_type"] == "tool_call_end"
    await _assert_run_records(
        api_client,
        db_session,
        frames=frames,
        owner=owner,
        other_owner=other_owner,
        action=action,
        invocation_status=expected_invocation_status,
        run_status="failed",
        terminal_event="run.failed",
    )
    assert SENTINEL_ERROR not in json.dumps(tool_end["output"])
    assert await _business_snapshot(db_session) == before


@pytest.mark.api
@pytest.mark.integration
async def test_schedule_rest_gets_preserve_owner_dto_and_empty_results(
    api_client, db_session
):
    owners = await _seed(db_session)
    before = await _business_snapshot(db_session)
    for index, owner in enumerate(owners):
        response = await api_client.get(
            "/api/v1/schedules/",
            headers={
                "Authorization": f"Bearer {create_access_token({'sub': str(owner.id)})}"
            },
        )
        assert response.status_code == 200, response.text
        result = response.json()
        assert result["total"] == (2 if index == 0 else 1)
        shared = next(
            item
            for item in result["items"]
            if item["schedule"]["source_id"] == SHARED_SOURCE_ID
        )
        assert shared["schedule"]["user_id"] == owner.id
        assert shared["collection"]["user_id"] == owner.id
        assert shared["collection"]["comment"] == PRIVATE_COMMENTS[index]
        assert PRIVATE_COMMENTS[1 - index] not in response.text

        by_day = await api_client.get(
            "/api/v1/schedules/by-day/2",
            headers={
                "Authorization": f"Bearer {create_access_token({'sub': str(owner.id)})}"
            },
        )
        assert by_day.status_code == 200, by_day.text
        assert len(by_day.json()) == 1
        assert by_day.json()[0]["user_id"] == owner.id
        assert by_day.json()[0]["source_id"] == SHARED_SOURCE_ID

    empty_owner = User(username="schedule-read-empty")
    db_session.add(empty_owner)
    await db_session.commit()
    empty_headers = {
        "Authorization": f"Bearer {create_access_token({'sub': str(empty_owner.id)})}"
    }
    empty_list = await api_client.get("/api/v1/schedules/", headers=empty_headers)
    assert empty_list.status_code == 200
    assert empty_list.json() == {"items": [], "total": 0}
    empty_day = await api_client.get(
        "/api/v1/schedules/by-day/2", headers=empty_headers
    )
    assert empty_day.status_code == 200
    assert empty_day.json() == []
    assert await _business_snapshot(db_session) == before


@pytest.mark.api
@pytest.mark.integration
@pytest.mark.parametrize("day", [-1, 7])
async def test_schedule_rest_invalid_day_is_rejected_without_service_reads(
    api_client, db_session, monkeypatch, day: int
):
    from app.services.schedule_service import ScheduleService

    owners = await _seed(db_session)
    calls = []

    async def record_read(*args, **kwargs):
        calls.append((args, kwargs))
        raise AssertionError("invalid day must be rejected before SQL service")

    monkeypatch.setattr(ScheduleService, "get_schedules_by_day", record_read)
    before = await _business_snapshot(db_session)
    response = await api_client.get(
        f"/api/v1/schedules/by-day/{day}",
        headers={
            "Authorization": f"Bearer {create_access_token({'sub': str(owners[0].id)})}"
        },
    )
    assert response.status_code == 422
    assert calls == []
    assert await _business_snapshot(db_session) == before


@pytest.mark.api
@pytest.mark.integration
@pytest.mark.parametrize(
    ("path", "method_name", "safe_detail"),
    [
        ("/api/v1/schedules/", "get_unified_user_schedules", "获取排班记录失败"),
        (
            "/api/v1/schedules/by-day/2",
            "get_schedules_by_day",
            "获取指定星期的排班记录失败",
        ),
    ],
)
async def test_schedule_rest_get_errors_are_safe_after_real_sql_read(
    api_client, db_session, monkeypatch, path: str, method_name: str, safe_detail: str
):
    from app.services.schedule_service import ScheduleService

    owners = await _seed(db_session)
    real_service = getattr(ScheduleService, method_name)
    service_entered = False
    real_read_returned = False
    wrapper_finalized = False

    async def fail_after_real_sql(*args, **kwargs):
        nonlocal service_entered, real_read_returned, wrapper_finalized
        service_entered = True
        try:
            await real_service(*args, **kwargs)
            real_read_returned = True
            raise RuntimeError(SENTINEL_ERROR)
        finally:
            wrapper_finalized = True

    monkeypatch.setattr(ScheduleService, method_name, fail_after_real_sql)
    before = await _business_snapshot(db_session)
    response = await api_client.get(
        path,
        headers={
            "Authorization": f"Bearer {create_access_token({'sub': str(owners[0].id)})}"
        },
    )
    assert response.status_code == 500
    assert response.json() == {"detail": safe_detail}
    assert SENTINEL_ERROR not in response.text
    assert service_entered is True
    assert real_read_returned is True
    assert wrapper_finalized is True
    assert await _business_snapshot(db_session) == before

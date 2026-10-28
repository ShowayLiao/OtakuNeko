"""HTTP/JWT -> Runtime/Dispatcher -> approved collection writes over real SQL."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.security import create_access_token
from app.harness.model_types import ModelCallResult
from app.models import Collection, Subject, User
from app.models.agent_run import AgentInvocation, AgentRunEvent
from app.models.enums import SubjectType


ACTIONS = (
    "create_collection",
    "update_collection",
    "delete_collection",
    "upsert_collection",
    "batch_upsert_collections",
    "import_json_collections",
    "sync_bangumi_collections",
    "sync_douban_collections",
)
SOURCE = "bangumi"
SHARED_ID = "90001"
OWNER_A_ID = "90002"
OWNER_B_ID = "90003"
PRESEEDED_TARGETS = ("90004", "90005", "90006", "90040", "90041", "90042")

_EVIDENCE: list[dict[str, Any]] = []


def _frames(text: str) -> list[dict[str, Any]]:
    event_type = "message"
    frames: list[dict[str, Any]] = []
    for line in text.splitlines():
        if line.startswith("event:"):
            event_type = line[6:].strip()
        elif line.startswith("data:"):
            frame = json.loads(line[5:].strip())
            frame["_event_type"] = event_type
            frames.append(frame)
    return frames


def _gateway(
    action: str,
    arguments: dict[str, Any],
    decision_ids: list[str],
    gateway_calls: list[int],
):
    inference_count = 0

    class Gateway:
        def __init__(self, **kwargs: Any) -> None:
            self.model = kwargs["model"]

        async def infer(self, **kwargs: Any) -> ModelCallResult:
            nonlocal inference_count
            inference_count += 1
            gateway_calls.append(inference_count)
            decision_id = uuid4().hex
            decision_ids.append(decision_id)
            decision: dict[str, Any] = {
                "schema_version": "v1",
                "decision_id": decision_id,
            }
            if inference_count == 1:
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


async def _seed(db: AsyncSession) -> list[User]:
    owners = [
        User(username="collections-write-a", bangumi_name="synthetic-bangumi-a"),
        User(username="collections-write-b", bangumi_name="synthetic-bangumi-b"),
    ]
    db.add_all(owners)
    await db.commit()
    for owner in owners:
        await db.refresh(owner)

    subjects = [
        Subject(
            source=SOURCE,
            source_id=SHARED_ID,
            name="Synthetic Shared Title",
            name_cn="Synthetic Shared Title",
            type=SubjectType.ANIME,
        ),
        Subject(
            source=SOURCE,
            source_id=OWNER_A_ID,
            name="Synthetic Owner A Title",
            name_cn="Synthetic Owner A Title",
            type=SubjectType.ANIME,
        ),
        Subject(
            source=SOURCE,
            source_id=OWNER_B_ID,
            name="Synthetic Owner B Title",
            name_cn="Synthetic Owner B Title",
            type=SubjectType.ANIME,
        ),
        *[
            Subject(
                source=SOURCE,
                source_id=source_id,
                name=f"Synthetic Seed Target {source_id}",
                name_cn=f"Synthetic Seed Target {source_id}",
                type=SubjectType.ANIME,
            )
            for source_id in PRESEEDED_TARGETS
        ],
    ]
    db.add_all(subjects)
    db.add_all(
        [
            Collection(
                user_id=owners[0].id,
                source=SOURCE,
                source_id=SHARED_ID,
                type=3,
                subject_type=int(SubjectType.ANIME),
                private=True,
                comment="synthetic-private-owner-a-shared",
                rate=8,
            ),
            Collection(
                user_id=owners[1].id,
                source=SOURCE,
                source_id=SHARED_ID,
                type=3,
                subject_type=int(SubjectType.ANIME),
                private=True,
                comment="synthetic-private-owner-b-shared",
                rate=9,
            ),
            Collection(
                user_id=owners[0].id,
                source=SOURCE,
                source_id=OWNER_A_ID,
                type=3,
                subject_type=int(SubjectType.ANIME),
                private=True,
                comment="synthetic-private-owner-a-only",
                rate=6,
            ),
            Collection(
                user_id=owners[1].id,
                source=SOURCE,
                source_id=OWNER_B_ID,
                type=3,
                subject_type=int(SubjectType.ANIME),
                private=True,
                comment="synthetic-private-owner-b-only",
                rate=7,
            ),
        ]
    )
    await db.commit()
    return owners


def _bangumi_item(source_id: str, title: str, comment: str) -> dict[str, Any]:
    numeric_id = int(source_id)
    return {
        "subject_id": numeric_id,
        "subject": {
            "id": numeric_id,
            "type": int(SubjectType.ANIME),
            "name": title,
            "name_cn": title,
            "date": "2026-10-01",
            "platform": "TV",
            "images": {},
            "rating": {"score": 8.0, "count": 100},
            "collection": {"wish": 0, "doing": 1, "done": 2},
            "tags": [{"name": "synthetic", "count": 1, "total_cont": 1}],
            "eps": 12,
        },
        "type": 3,
        "rate": 8,
        "comment": comment,
        "private": True,
        "tags": ["synthetic"],
        "subject_type": int(SubjectType.ANIME),
        "updated_at": "2026-10-20T12:00:00+00:00",
    }


def _arguments(action: str, variant: str) -> dict[str, Any]:
    arguments: dict[str, Any] = {
        "idempotency_key": f"synthetic-{variant}-{action}",
    }
    if action == "create_collection":
        source_id = "90004" if variant == "approved" else "90040"
        arguments.update(
            source=SOURCE,
            source_id=source_id,
            type=3,
            rate=7,
            comment=f"synthetic-{variant}-create",
            private=True,
            tags=["synthetic-create"],
            subject_type=int(SubjectType.ANIME),
        )
    elif action == "update_collection":
        arguments.update(
            source=SOURCE,
            source_id=OWNER_A_ID,
            type=4,
            rate=9,
            comment=f"synthetic-{variant}-update",
            private=True,
            subject_type=int(SubjectType.ANIME),
        )
    elif action == "delete_collection":
        arguments.update(source=SOURCE, source_id=OWNER_A_ID)
    elif action == "upsert_collection":
        source_id = "90005" if variant == "approved" else "90041"
        arguments.update(
            source=SOURCE,
            source_id=source_id,
            type=2,
            rate=10,
            comment=f"synthetic-{variant}-upsert",
            private=True,
            subject_type=int(SubjectType.ANIME),
        )
    elif action == "batch_upsert_collections":
        new_source_id = "90006" if variant == "approved" else "90042"
        arguments["items"] = [
            {
                "source": SOURCE,
                "source_id": OWNER_A_ID,
                "type": 4,
                "rate": 6,
                "comment": f"synthetic-{variant}-batch-update",
                "private": True,
                "subject_type": int(SubjectType.ANIME),
            },
            {
                "source": SOURCE,
                "source_id": new_source_id,
                "type": 2,
                "rate": 8,
                "comment": f"synthetic-{variant}-batch-create",
                "private": True,
                "subject_type": int(SubjectType.ANIME),
            },
        ]
    elif action == "import_json_collections":
        source_id = "90107" if variant == "approved" else "90143"
        arguments["data"] = {
            "total": 1,
            "data": [
                _bangumi_item(
                    source_id,
                    f"Synthetic Imported Title {variant}",
                    f"synthetic-{variant}-import",
                )
            ],
        }
    elif action == "sync_bangumi_collections":
        source_id = "90108" if variant == "approved" else "90144"
        arguments.update(subject_type=int(SubjectType.ANIME), limit=10, offset=0)
        arguments["_synthetic_bangumi_response"] = {
            "total": 1,
            "data": [
                _bangumi_item(
                    source_id,
                    f"Synthetic Bangumi Sync {variant}",
                    f"synthetic-{variant}-bangumi-sync",
                )
            ],
        }
    elif action == "sync_douban_collections":
        source_id = "90109" if variant == "approved" else "90145"
        arguments["data"] = [
            {
                "interest": {
                    "status": "done",
                    "subject": {
                        "id": source_id,
                        "type": "book",
                        "title": f"Synthetic Douban Title {variant}",
                        "pubdate": ["2026-01-01"],
                        "intro": "Synthetic import fixture",
                        "pic": {},
                        "genres": ["synthetic"],
                    },
                    "rating": {"value": 4},
                    "comment": f"synthetic-{variant}-douban-sync",
                    "is_private": True,
                    "create_time": "2026-10-20T12:00:00+00:00",
                    "tags": ["synthetic"],
                }
            }
        ]
    else:
        raise AssertionError(f"Unknown action {action}")
    return arguments


async def _business_snapshot(db: AsyncSession) -> dict[str, list[dict[str, Any]]]:
    subject_rows = (
        await db.execute(
            select(Subject)
            .order_by(Subject.source, Subject.source_id)
            .execution_options(populate_existing=True)
        )
    ).scalars()
    collection_rows = (
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
        "subjects": [row.model_dump(mode="json") for row in subject_rows],
        "collections": [row.model_dump(mode="json") for row in collection_rows],
    }


def _subject_map(
    snapshot: dict[str, list[dict[str, Any]]],
) -> dict[tuple[str, str], dict[str, Any]]:
    return {(row["source"], row["source_id"]): row for row in snapshot["subjects"]}


def _collection_map(
    snapshot: dict[str, list[dict[str, Any]]], user_id: int
) -> dict[tuple[str, str], dict[str, Any]]:
    return {
        (row["source"], row["source_id"]): row
        for row in snapshot["collections"]
        if row["user_id"] == user_id
    }


def _arguments_target(action: str, variant: str) -> tuple[str, str] | None:
    if action == "create_collection":
        return SOURCE, "90004" if variant == "approved" else "90040"
    if action == "update_collection" or action == "delete_collection":
        return SOURCE, OWNER_A_ID
    if action == "upsert_collection":
        return SOURCE, "90005" if variant == "approved" else "90041"
    if action == "batch_upsert_collections":
        return SOURCE, "90006" if variant == "approved" else "90042"
    if action == "import_json_collections":
        return SOURCE, "90107" if variant == "approved" else "90143"
    if action == "sync_bangumi_collections":
        return SOURCE, "90108" if variant == "approved" else "90144"
    if action == "sync_douban_collections":
        return "douban", "90109" if variant == "approved" else "90145"
    return None


def _assert_write_output(action: str, output: dict[str, Any]) -> None:
    if action in {"create_collection", "update_collection", "upsert_collection"}:
        assert "collection" in output
    elif action == "delete_collection":
        assert output.get("deleted") is True
    elif action == "batch_upsert_collections":
        assert output.get("processed_count") == 2
        assert output.get("requested_count") == 2
    elif action in {
        "import_json_collections",
        "sync_bangumi_collections",
        "sync_douban_collections",
    }:
        assert output.get("processed_count") == 2
    else:
        raise AssertionError(f"Unknown action {action}")


def _assert_business_write(
    action: str,
    variant: str,
    owner_id: int,
    foreign_id: int,
    before: dict[str, list[dict[str, Any]]],
    after: dict[str, list[dict[str, Any]]],
) -> None:
    before_owner = _collection_map(before, owner_id)
    after_owner = _collection_map(after, owner_id)
    assert _collection_map(before, foreign_id) == _collection_map(after, foreign_id)

    before_subjects = _subject_map(before)
    after_subjects = _subject_map(after)
    if action in {
        "import_json_collections",
        "sync_bangumi_collections",
        "sync_douban_collections",
    }:
        new_subject_key = _arguments_target(action, variant)
        assert new_subject_key is not None
        assert set(after_subjects) == set(before_subjects) | {new_subject_key}
        assert after_subjects[new_subject_key]["name"].endswith(variant)
    else:
        assert after_subjects == before_subjects

    target = _arguments_target(action, variant)
    assert target is not None
    if action == "delete_collection":
        assert set(after_owner) == set(before_owner) - {target}
        return
    if action == "update_collection":
        assert set(after_owner) == set(before_owner)
        changed = after_owner[target]
        assert changed["comment"] == f"synthetic-{variant}-update"
        assert changed["rate"] == 9
        assert changed["type"] == 4
        assert changed["private"] is True
        return

    assert set(after_owner) == set(before_owner) | {target}
    created = after_owner[target]
    assert created["user_id"] == owner_id
    assert created["private"] is True
    if action == "create_collection":
        assert created["comment"] == f"synthetic-{variant}-create"
        assert created["rate"] == 7 and created["type"] == 3
    elif action == "upsert_collection":
        assert created["comment"] == f"synthetic-{variant}-upsert"
        assert created["rate"] == 10 and created["type"] == 2
    elif action == "batch_upsert_collections":
        updated = after_owner[(SOURCE, OWNER_A_ID)]
        assert updated["comment"] == f"synthetic-{variant}-batch-update"
        assert updated["rate"] == 6 and updated["type"] == 4
        assert created["comment"] == f"synthetic-{variant}-batch-create"
        assert created["rate"] == 8 and created["type"] == 2
    elif action in {"import_json_collections", "sync_bangumi_collections"}:
        expected = (
            f"synthetic-{variant}-import"
            if action == "import_json_collections"
            else f"synthetic-{variant}-bangumi-sync"
        )
        assert created["comment"] == expected
        assert created["rate"] == 8 and created["type"] == 3
    elif action == "sync_douban_collections":
        assert created["comment"] == f"synthetic-{variant}-douban-sync"
        assert created["rate"] == 8 and created["type"] == 2
    else:
        raise AssertionError(f"Unknown action {action}")


async def _chat(
    api_client: Any,
    owner: User,
    action: str,
    arguments: dict[str, Any],
    checkpoint_path: Path,
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
    thread_id = f"collections-write-{action}-{uuid4().hex[:10]}"
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
            "messages": [
                {"role": "user", "content": "Update my synthetic collections"}
            ],
        },
    )
    assert response.status_code == 200
    frames = _frames(response.text)
    assert len(decision_ids) == len(set(decision_ids))
    return headers, thread_id, frames, decision_ids, gateway_calls


def _install_service_counters(
    action: str, monkeypatch: pytest.MonkeyPatch
) -> tuple[list[str], list[dict[str, Any]], dict[str, dict[str, Any]]]:
    from app.capabilities import collections as collections_capability
    from app.services import bangumi_service

    service_symbols = {
        "create_collection": "create_collection",
        "update_collection": "update_collection",
        "delete_collection": "delete_collection",
        "upsert_collection": "upsert_collection",
        "batch_upsert_collections": "batch_upsert_collections",
        "import_json_collections": "import_json_collections",
        "sync_bangumi_collections": "sync_user_collections",
        "sync_douban_collections": "sync_user_collections_douban",
    }
    service_calls: list[str] = []
    original = getattr(collections_capability, service_symbols[action])

    async def tracked_service(*args: Any, **kwargs: Any) -> Any:
        service_calls.append(action)
        return await original(*args, **kwargs)

    monkeypatch.setattr(
        collections_capability, service_symbols[action], tracked_service
    )
    bangumi_fetch_calls: list[dict[str, Any]] = []
    active_response: dict[str, dict[str, Any]] = {"value": {"total": 0, "data": []}}

    async def synthetic_bangumi_fetch(
        username: str,
        subject_type: int | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> dict[str, Any]:
        bangumi_fetch_calls.append(
            {
                "username": username,
                "subject_type": subject_type,
                "limit": limit,
                "offset": offset,
            }
        )
        return active_response["value"]

    monkeypatch.setattr(
        bangumi_service, "fetch_user_collections", synthetic_bangumi_fetch
    )
    return service_calls, bangumi_fetch_calls, active_response


async def _read_run(
    api_client: Any, run_id: str, headers: dict[str, str]
) -> dict[str, Any]:
    response = await api_client.get(f"/api/v1/runs/{run_id}", headers=headers)
    assert response.status_code == 200
    return response.json()


def _resume_params(thread_id: str, run_id: str, decision: str) -> dict[str, str]:
    return {"thread_id": thread_id, "run_id": run_id, "decision": decision}


def _write_artifact() -> None:
    artifact_path = (
        Path(__file__).resolve().parents[2]
        / ".runtime/capability-contracts/collections-write-http.json"
    )
    artifact_path.parent.mkdir(parents=True, exist_ok=True)
    certified = sorted({str(item["action"]) for item in _EVIDENCE})
    artifact_path.write_text(
        json.dumps(
            {
                "source": "Synthetic HTTP/JWT + Runtime/Dispatcher + real SQL/domain + fake model and Bangumi fetch boundary",
                "expected_actions": list(ACTIONS),
                "certified_actions": certified,
                "complete": set(certified) == set(ACTIONS),
                "runs": _EVIDENCE,
            },
            indent=2,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )


@pytest.mark.api
@pytest.mark.integration
@pytest.mark.parametrize("action", ACTIONS)
async def test_collections_write_http_approval_certification(
    api_client: Any,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    action: str,
) -> None:
    from app.capabilities.factory import build_capability_registry

    registry = build_capability_registry()
    descriptor_owner = registry.find_action(action)
    assert descriptor_owner is not None
    capability, descriptor = descriptor_owner
    assert capability.name == "collections"
    assert descriptor.public_name == action
    assert descriptor.version == "v1"
    assert descriptor.requires_auth is True
    assert descriptor.is_side_effect is True
    assert descriptor.approval_required is True
    assert descriptor.idempotency_mode == "required"

    owners = await _seed(db_session)
    owner, foreign = owners
    assert owner.id is not None and foreign.id is not None
    service_calls, bangumi_fetch_calls, active_bangumi_response = (
        _install_service_counters(action, monkeypatch)
    )
    checkpoint_path = tmp_path / "collections-write-checkpoint.db"
    arguments = _arguments(action, "approved")
    if action == "sync_bangumi_collections":
        active_bangumi_response["value"] = arguments.pop("_synthetic_bangumi_response")

    before = await _business_snapshot(db_session)
    headers, thread_id, initial_frames, decision_ids, gateway_calls = await _chat(
        api_client,
        owner,
        action,
        arguments,
        checkpoint_path,
        monkeypatch,
    )
    paused_frames = [
        frame
        for frame in initial_frames
        if frame.get("_event_type") == "approval_required"
    ]
    assert len(paused_frames) == 1, json.dumps(initial_frames, indent=2)
    approval_frame = paused_frames[0]
    assert approval_frame["capability"] == action
    run_ids = {frame["run_id"] for frame in initial_frames if frame.get("run_id")}
    assert len(run_ids) == 1
    run_id = run_ids.pop()
    assert approval_frame["run_id"] == run_id
    assert await _business_snapshot(db_session) == before
    assert service_calls == []
    assert len(bangumi_fetch_calls) == 0
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
    assert approved.status_code == 200
    approved_frames = _frames(approved.text)
    successful_ends = [
        frame
        for frame in approved_frames
        if frame.get("_event_type") == "tool_call_end"
        and frame.get("status") == "succeeded"
    ]
    assert len(successful_ends) == 1, json.dumps(approved_frames, indent=2)
    assert successful_ends[0]["capability"] == action
    _assert_write_output(action, successful_ends[0]["output"])
    serialized_output = json.dumps(successful_ends[0]["output"], allow_nan=False)
    assert '"user_id"' not in serialized_output
    assert "synthetic-private-owner-b" not in serialized_output
    assert "Synthetic Owner B Title" not in serialized_output
    assert service_calls == [action]
    if action == "sync_bangumi_collections":
        assert bangumi_fetch_calls == [
            {
                "username": owner.bangumi_name,
                "subject_type": int(SubjectType.ANIME),
                "limit": 10,
                "offset": 0,
            }
        ]
    else:
        assert bangumi_fetch_calls == []

    after = await _business_snapshot(db_session)
    _assert_business_write(
        action,
        "approved",
        owner.id,
        foreign.id,
        before,
        after,
    )
    completed_run = await _read_run(api_client, run_id, headers)
    assert completed_run["status"] == "succeeded"
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
    invocation = invocations[0]
    assert invocation.invocation_id == approval_frame["invocation_id"]
    assert invocation.capability == action
    assert invocation.status == "succeeded"
    assert invocation.finished_at is not None

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
    assert len({event.sequence for event in events}) == len(events)
    terminal_events = [
        event
        for event in events
        if event.event_type in {"run.succeeded", "run.failed", "run.cancelled"}
    ]
    assert len(terminal_events) == 1
    assert terminal_events[0].event_type == "run.succeeded"
    end_events = [
        event
        for event in events
        if event.event_type == "tool_call_end"
        and event.invocation_id == invocation.invocation_id
        and event.payload.get("status") == "succeeded"
    ]
    assert len(end_events) == 1

    trace = await api_client.get(f"/api/v1/trace/{run_id}", headers=headers)
    assert trace.status_code == 200
    assert trace.json()["user_id"] == owner.id
    foreign_trace = await api_client.get(
        f"/api/v1/trace/{run_id}", headers=foreign_headers
    )
    assert foreign_trace.status_code == 404
    foreign_run = await api_client.get(
        f"/api/v1/runs/{run_id}", headers=foreign_headers
    )
    assert foreign_run.status_code == 404

    calls_after_approval = len(service_calls)
    repeat = await api_client.post(
        "/api/v1/chat/resume",
        params=_resume_params(thread_id, run_id, "approve"),
        headers=headers,
    )
    assert repeat.status_code == 409
    assert await _read_run(api_client, run_id, headers) == completed_run
    assert await _business_snapshot(db_session) == after
    assert service_calls == [action]
    assert len(bangumi_fetch_calls) == (
        1 if action == "sync_bangumi_collections" else 0
    )

    rejected_arguments = _arguments(action, "rejected")
    if action == "sync_bangumi_collections":
        active_bangumi_response["value"] = rejected_arguments.pop(
            "_synthetic_bangumi_response"
        )
    calls_before_rejection = len(service_calls)
    (
        reject_headers,
        reject_thread_id,
        reject_initial_frames,
        reject_ids,
        reject_gateway_calls,
    ) = await _chat(
        api_client,
        owner,
        action,
        rejected_arguments,
        checkpoint_path,
        monkeypatch,
    )
    reject_before = await _business_snapshot(db_session)
    assert reject_before == after
    reject_pauses = [
        frame
        for frame in reject_initial_frames
        if frame.get("_event_type") == "approval_required"
    ]
    assert len(reject_pauses) == 1
    reject_run_id = reject_pauses[0]["run_id"]
    assert await _business_snapshot(db_session) == reject_before
    rejected = await api_client.post(
        "/api/v1/chat/resume",
        params=_resume_params(reject_thread_id, reject_run_id, "reject"),
        headers=reject_headers,
    )
    assert rejected.status_code == 200
    rejected_frames = _frames(rejected.text)
    assert any(frame.get("_event_type") == "run_failed" for frame in rejected_frames)
    assert (await _read_run(api_client, reject_run_id, reject_headers))[
        "status"
    ] == "failed"
    assert await _business_snapshot(db_session) == reject_before
    assert service_calls == [action]
    assert len(service_calls) - calls_before_rejection == 0
    assert len(bangumi_fetch_calls) == (
        1 if action == "sync_bangumi_collections" else 0
    )

    _EVIDENCE.append(
        {
            "action": action,
            "approved_run_status": "succeeded",
            "rejected_run_status": "failed",
            "pause_business_snapshot_unchanged": True,
            "foreign_resume_status": 404,
            "continue_status": 409,
            "repeat_approval_status": 409,
            "approval_action_calls": len(service_calls),
            "repeat_approval_additional_service_calls": len(service_calls)
            - calls_after_approval,
            "rejected_run_service_calls": len(service_calls) - calls_before_rejection,
            "bangumi_fetch_calls": len(bangumi_fetch_calls),
            "owner_trace_verified": True,
            "foreign_run_and_trace_hidden": True,
            "foreign_private_collections_unchanged": True,
            "rejection_business_snapshot_unchanged": True,
            "unique_decisions": len(decision_ids) == len(set(decision_ids))
            and len(reject_ids) == len(set(reject_ids)),
            "gateway_calls": len(gateway_calls) + len(reject_gateway_calls),
        }
    )
    _write_artifact()

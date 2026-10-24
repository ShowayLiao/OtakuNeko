"""HTTP/JWT -> Runtime/Dispatcher -> owned collection reads over real SQL."""

from __future__ import annotations

import asyncio
from dataclasses import replace
import json
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest
from sqlmodel import col, select

from app.core.security import create_access_token
from app.harness.model_types import ModelCallResult
from app.models import Collection, Subject, User
from app.models.agent_run import AgentInvocation, AgentRunEvent
from app.models.enums import SubjectType


ACTIONS = ("list_collections", "get_collection", "search_collections")
SUBJECT_NAME = "Shared Collection Read"
SOURCE = "bangumi"
SOURCE_ID = "501"


def _frames(text: str) -> list[dict]:
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


def _gateway(action: str, arguments: dict, decision_ids: list[str]):
    class Gateway:
        def __init__(self, **kwargs):
            self.model = kwargs["model"]
            self.count = 0

        async def infer(self, **kwargs):
            self.count += 1
            decision_id = uuid4().hex
            decision_ids.append(decision_id)
            decision: dict[str, Any] = {
                "schema_version": "v1",
                "decision_id": decision_id,
            }
            if self.count == 1:
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
    owners = [User(username="collections-read-a"), User(username="collections-read-b")]
    db.add_all(owners)
    await db.commit()

    subjects = [
        Subject(
            source=SOURCE,
            source_id=SOURCE_ID,
            name=SUBJECT_NAME,
            type=SubjectType.ANIME,
        ),
        Subject(
            source=SOURCE,
            source_id="601",
            name="owner-a-only-title",
            type=SubjectType.BOOK,
        ),
        Subject(
            source=SOURCE,
            source_id="602",
            name="owner-b-only-title",
            type=SubjectType.GAME,
        ),
    ]
    db.add_all(subjects)
    for index, owner in enumerate(owners):
        db.add(
            Collection(
                user_id=owner.id,
                source=SOURCE,
                source_id=SOURCE_ID,
                type=3,
                subject_type=int(SubjectType.ANIME),
                private=True,
                comment=f"private-owner-{index}-comment",
                rate=8 + index,
            )
        )
        own_type = SubjectType.BOOK if index == 0 else SubjectType.GAME
        db.add(
            Collection(
                user_id=owner.id,
                source=SOURCE,
                source_id=str(601 + index),
                type=3,
                subject_type=int(own_type),
                private=True,
                comment=f"owner-{index}-only-comment",
                rate=6 + index,
            )
        )
    await db.commit()
    return owners


def _arguments(action: str) -> dict:
    if action == "get_collection":
        return {"source": SOURCE, "source_id": SOURCE_ID}
    if action == "search_collections":
        return {
            "keyword": "Shared",
            "status": 3,
            "type": int(SubjectType.ANIME),
            "skip": 0,
            "limit": 10,
            "sort_by": "updated_at",
        }
    return {
        "type": int(SubjectType.ANIME),
        "status": 3,
        "skip": 0,
        "limit": 10,
        "sort_by": "updated_at",
    }


async def _business_snapshot(db) -> dict:
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


async def _chat(api_client, owner: User, action: str, arguments: dict, monkeypatch):
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
            "messages": [{"role": "user", "content": "Read my collections"}],
        },
    )
    assert response.status_code == 200
    frames = _frames(response.text)
    ends = [frame for frame in frames if frame.get("_event_type") == "tool_call_end"]
    assert len(ends) == 1, json.dumps(frames, indent=2)
    assert len(decision_ids) == len(set(decision_ids))
    return headers, frames, ends[0]


@pytest.mark.api
@pytest.mark.integration
async def test_collections_read_http_certification(api_client, db_session, monkeypatch):
    from app.capabilities.collections import CollectionCapability

    owners = await _seed(db_session)
    descriptors = {item.name: item for item in CollectionCapability().actions()}
    for action in ACTIONS:
        assert descriptors[action].public_name == action
        assert descriptors[action].version == "v1"
        assert descriptors[action].requires_auth is True
        assert descriptors[action].is_side_effect is False
        assert descriptors[action].approval_required is False
        assert descriptors[action].idempotency_mode == "none"

    evidence = []
    for action in ACTIONS:
        arguments = _arguments(action)
        for index, owner in enumerate(owners):
            before = await _business_snapshot(db_session)
            headers, frames, tool_end = await _chat(
                api_client, owner, action, arguments, monkeypatch
            )
            assert tool_end["status"] == "succeeded", tool_end
            output = tool_end["output"]
            serialized = json.dumps(output, allow_nan=False)
            assert '"user_id"' not in serialized
            assert f"private-owner-{1 - index}-comment" not in serialized
            assert f"owner-{1 - index}-only-comment" not in serialized
            assert f"owner-{1 - index}-only-title" not in serialized

            items = (
                [output["collection"]]
                if action == "get_collection"
                else output["collections"]
            )
            assert len(items) == 1
            item = items[0]
            assert item["subject"]["name"] == SUBJECT_NAME
            assert item["collection"]["comment"] == f"private-owner-{index}-comment"
            assert item["collection"]["rate"] == 8 + index

            run_ids = {frame.get("run_id") for frame in frames if frame.get("run_id")}
            assert len(run_ids) == 1
            run_id = run_ids.pop()
            canonical = await api_client.get(f"/api/v1/runs/{run_id}", headers=headers)
            assert canonical.status_code == 200
            assert canonical.json()["status"] == "succeeded"
            invocation = (
                await db_session.execute(
                    select(AgentInvocation).where(AgentInvocation.run_id == run_id)
                )
            ).scalar_one()
            assert invocation.status == "succeeded"
            assert invocation.capability == action
            trace = await api_client.get(f"/api/v1/trace/{run_id}", headers=headers)
            assert trace.status_code == 200
            assert trace.json()["user_id"] == owner.id
            foreign_headers = {
                "Authorization": (
                    f"Bearer {create_access_token({'sub': str(owners[1 - index].id)})}"
                )
            }
            for path in (f"/api/v1/runs/{run_id}", f"/api/v1/trace/{run_id}"):
                assert (
                    await api_client.get(path, headers=foreign_headers)
                ).status_code == 404
            after = await _business_snapshot(db_session)
            assert after == before
            evidence.append(
                {
                    "action": action,
                    "owner": f"owner-{index}",
                    "run_id": run_id,
                    "run_status": canonical.json()["status"],
                    "invocation_status": invocation.status,
                    "tool_output": output,
                    "trace_owner_matches": True,
                    "foreign_run_and_trace_reads": 404,
                    "business_snapshot_unchanged": True,
                }
            )

    assert len(evidence) == 6
    evidence_path = (
        Path(__file__).resolve().parents[2]
        / ".runtime/capability-contracts/collections-read-http.json"
    )
    evidence_path.parent.mkdir(parents=True, exist_ok=True)
    evidence_path.write_text(
        json.dumps(
            {
                "source": "HTTP/JWT + Runtime/Dispatcher + real SQL/domain + fake model gateway",
                "runs": evidence,
            },
            indent=2,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )


@pytest.mark.api
@pytest.mark.integration
async def test_collections_get_hides_another_owners_collection(
    api_client, db_session, monkeypatch
):
    owners = await _seed(db_session)
    before = await _business_snapshot(db_session)
    headers, frames, tool_end = await _chat(
        api_client,
        owners[0],
        "get_collection",
        {"source": SOURCE, "source_id": "602"},
        monkeypatch,
    )
    assert tool_end["status"] == "failed"
    assert tool_end["output"]["error_type"] == "not_found"
    assert "owner-1-only-comment" not in json.dumps(tool_end["output"])
    run_ids = {frame.get("run_id") for frame in frames if frame.get("run_id")}
    assert len(run_ids) == 1
    run_id = run_ids.pop()
    canonical = await api_client.get(f"/api/v1/runs/{run_id}", headers=headers)
    assert canonical.status_code == 200
    assert canonical.json()["status"] == "failed"
    invocation = (
        await db_session.execute(
            select(AgentInvocation).where(AgentInvocation.run_id == run_id)
        )
    ).scalar_one()
    assert invocation.status == "failed"
    trace = await api_client.get(f"/api/v1/trace/{run_id}", headers=headers)
    assert trace.status_code == 200
    assert trace.json()["user_id"] == owners[0].id
    foreign_trace = await api_client.get(
        f"/api/v1/trace/{run_id}",
        headers={
            "Authorization": f"Bearer {create_access_token({'sub': str(owners[1].id)})}"
        },
    )
    assert foreign_trace.status_code == 404
    assert await _business_snapshot(db_session) == before


@pytest.mark.api
@pytest.mark.integration
@pytest.mark.parametrize("action", ACTIONS)
@pytest.mark.parametrize("fault", ["raise", "timeout"])
async def test_collections_read_http_faults_are_terminal_and_read_only(
    api_client, db_session, monkeypatch, action: str, fault: str
):
    from app.capabilities import collections as collection_capability
    from app.capabilities.collections import CollectionCapability

    owners = await _seed(db_session)
    owner = owners[0]
    service_names = {
        "list_collections": "get_user_collections",
        "get_collection": "get_collection",
        "search_collections": "search_collections",
    }
    service_name = service_names[action]
    real_service = getattr(collection_capability, service_name)
    read_entered = False

    async def fault_after_read(*args, **kwargs):
        nonlocal read_entered
        result = await real_service(*args, **kwargs)
        read_entered = True
        if fault == "raise":
            raise RuntimeError("synthetic collection read failure")
        await asyncio.Event().wait()
        return result

    monkeypatch.setattr(collection_capability, service_name, fault_after_read)
    if fault == "timeout":
        actions = CollectionCapability.actions

        def short_timeout_actions(self):
            return [
                replace(item, timeout_seconds=0.1) if item.name == action else item
                for item in actions(self)
            ]

        monkeypatch.setattr(CollectionCapability, "actions", short_timeout_actions)

    before = await _business_snapshot(db_session)
    _, frames, tool_end = await _chat(
        api_client, owner, action, _arguments(action), monkeypatch
    )
    expected_tool_status = "timeout" if fault == "timeout" else "failed"
    expected_invocation_status = "timed_out" if fault == "timeout" else "failed"
    assert read_entered is True
    assert tool_end["status"] == expected_tool_status, tool_end
    assert tool_end["_event_type"] == "tool_call_end"
    run_ids = {frame.get("run_id") for frame in frames if frame.get("run_id")}
    assert len(run_ids) == 1
    run_id = run_ids.pop()
    headers = {"Authorization": f"Bearer {create_access_token({'sub': str(owner.id)})}"}
    canonical = await api_client.get(f"/api/v1/runs/{run_id}", headers=headers)
    assert canonical.status_code == 200
    assert canonical.json()["status"] == "failed"
    invocation = (
        await db_session.execute(
            select(AgentInvocation).where(AgentInvocation.run_id == run_id)
        )
    ).scalar_one()
    assert invocation.status == expected_invocation_status
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
        if event.event_type in {"run.succeeded", "run.failed", "run.cancelled"}
    ]
    assert len(terminal) == 1
    assert terminal[0].event_type == "run.failed"
    trace = await api_client.get(f"/api/v1/trace/{run_id}", headers=headers)
    assert trace.status_code == 200
    assert trace.json()["user_id"] == owner.id
    foreign = await api_client.get(
        f"/api/v1/trace/{run_id}",
        headers={
            "Authorization": f"Bearer {create_access_token({'sub': str(owners[1].id)})}"
        },
    )
    assert foreign.status_code == 404
    after = await _business_snapshot(db_session)
    assert after == before

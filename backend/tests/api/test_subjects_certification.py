"""HTTP/JWT -> Runtime -> Subjects -> real SQL/domain views, with fake network."""

from __future__ import annotations

from datetime import datetime
import json
from pathlib import Path
from uuid import uuid4

import pytest
from sqlmodel import select

from app.core.security import create_access_token
from app.harness.model_types import ModelCallResult
from app.models import Collection, Subject, User
from app.models.agent_run import AgentInvocation
from app.models.enums import SubjectType


ACTIONS = (
    "get_subject",
    "search_local_subjects",
    "search_remote_subjects",
    "search_mixed_subjects",
    "get_subject_air_time",
)


def _frames(text):
    return [
        json.loads(line[5:].strip())
        for line in text.splitlines()
        if line.startswith("data:")
    ]


def _gateway(action, arguments):
    class Gateway:
        def __init__(self, **kwargs):
            self.model = kwargs["model"]
            self.count = 0

        async def infer(self, **kwargs):
            self.count += 1
            decision = {
                "schema_version": "v1",
                "decision_id": f"subjects-{uuid4().hex}",
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


async def _seed(db):
    owners = [User(username="subjects-owner-a"), User(username="subjects-owner-b")]
    db.add_all(owners)
    await db.commit()
    subject = Subject(
        source="bangumi",
        source_id="501",
        name="Synthetic catalog",
        type=SubjectType.ANIME,
        air_time=datetime(2026, 10, 20, 12),
        air_weekday=2,
    )
    db.add(subject)
    for index, owner in enumerate(owners):
        db.add(
            Collection(
                user_id=owner.id,
                source="bangumi",
                source_id="501",
                type=3,
                private=True,
                comment=f"owner-only-{index}",
                rate=8 + index,
            )
        )
    await db.commit()
    return owners


@pytest.mark.api
@pytest.mark.integration
@pytest.mark.parametrize("action", ACTIONS)
async def test_subjects_http_real_services_isolate_owned_collections(
    action, api_client, db_session, monkeypatch
):
    from app.api.v1 import agent as agent_api
    from app.core.config import settings
    from app.services import subject_service

    owners = await _seed(db_session)
    arguments = (
        {"source": "bangumi", "source_id": "501"}
        if action.startswith("get_")
        else {"keyword": "Synthetic", "limit": 5}
    )
    monkeypatch.setattr(settings, "HARNESS_CHECKPOINT_ADAPTER", "disabled")
    monkeypatch.setattr(agent_api, "OpenAIModelGateway", _gateway(action, arguments))
    calls = []

    async def remote(keyword, subject_type, limit, offset):
        calls.append((keyword, limit, offset))
        return {
            "total": 2,
            "data": [
                {"id": 501, "type": 2, "name": "Synthetic remote duplicate"},
                {"id": 502, "type": 2, "name": "Synthetic remote unique"},
            ],
        }

    monkeypatch.setattr(subject_service, "search_bangumi_subjects", remote)
    evidence = []
    for index, owner in enumerate(owners):
        token = create_access_token({"sub": str(owner.id)})
        headers = {
            "Authorization": f"Bearer {token}",
            "X-Api-Key": "synthetic-test-key",
        }
        response = await api_client.post(
            "/api/v1/chat",
            headers=headers,
            json={
                "model": "synthetic-model",
                "messages": [{"role": "user", "content": "Read synthetic catalog"}],
            },
        )
        assert response.status_code == 200
        frames = _frames(response.text)
        results = [
            frame for frame in frames if "output" in frame and "invocation_id" in frame
        ]
        assert len(results) == 1, json.dumps(frames, indent=2)
        result = results[0]
        assert result["status"] == "succeeded", result
        output = result["output"]
        serialized = json.dumps(output, allow_nan=False)
        assert "user_id" not in serialized
        assert f"owner-only-{1 - index}" not in serialized
        if action == "get_subject":
            item = output["subject"]
            assert item["subject"]["name"] == "Synthetic catalog"
            assert item["collection"]["comment"] == f"owner-only-{index}"
        elif action == "get_subject_air_time":
            assert output["air_time"] == "2026-10-20T12:00:00"
            assert output["air_weekday"] == 2
        else:
            items = output["subjects"]
            assert len(items) == (1 if action == "search_local_subjects" else 2)
            assert len(
                {
                    (item["subject"]["source"], item["subject"]["source_id"])
                    for item in items
                }
            ) == len(items)
            if action == "search_remote_subjects":
                assert all(item["collection"] is None for item in items)
            else:
                assert items[0]["subject"]["name"] == "Synthetic catalog"
                assert items[0]["collection"]["comment"] == f"owner-only-{index}"
        run_id = result["run_id"]
        canonical = await api_client.get(f"/api/v1/runs/{run_id}", headers=headers)
        assert (
            canonical.status_code == 200 and canonical.json()["status"] == "succeeded"
        )
        invocation = (
            await db_session.execute(
                select(AgentInvocation).where(AgentInvocation.run_id == run_id)
            )
        ).scalar_one()
        assert invocation.status == "succeeded"
        trace = await api_client.get(f"/api/v1/trace/{run_id}", headers=headers)
        assert trace.status_code == 200 and trace.json()["user_id"] == owner.id
        other = create_access_token({"sub": str(owners[1 - index].id)})
        for path in (f"/api/v1/runs/{run_id}", f"/api/v1/trace/{run_id}"):
            denied = await api_client.get(
                path, headers={"Authorization": f"Bearer {other}"}
            )
            assert denied.status_code == 404
        evidence.append(
            {
                "action": action,
                "run_id": run_id,
                "run_status": canonical.json()["status"],
                "invocation_status": invocation.status,
                "trace_owner_matches": True,
                "foreign_reads": 404,
            }
        )
    assert len(calls) == (
        2 if action in {"search_remote_subjects", "search_mixed_subjects"} else 0
    )
    evidence_path = (
        Path(__file__).resolve().parents[2]
        / ".runtime/capability-contracts"
        / f"subjects-http-{action}.json"
    )
    evidence_path.parent.mkdir(parents=True, exist_ok=True)
    evidence_path.write_text(
        json.dumps(
            {"source": "HTTP/JWT + real SQL/domain + fake upstream", "runs": evidence},
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


@pytest.mark.postgres
@pytest.mark.integration
async def test_postgres_subjects_real_service_collection_isolation(
    postgres_session, monkeypatch
):
    from app.capabilities.subjects import SubjectCapability
    from app.services import subject_service

    owners = await _seed(postgres_session)

    async def remote(*args):
        return {"total": 0, "data": []}

    monkeypatch.setattr(subject_service, "search_bangumi_subjects", remote)
    for index, owner in enumerate(owners):
        for action in ACTIONS:
            arguments = (
                {"source": "bangumi", "source_id": "501"}
                if action.startswith("get_")
                else {"keyword": "Synthetic"}
            )
            result = await SubjectCapability().execute(
                action, db=postgres_session, user_id=owner.id, **arguments
            )
            assert result["success"] is True, result
            encoded = json.dumps(result, allow_nan=False)
            assert "user_id" not in encoded
            assert f"owner-only-{1 - index}" not in encoded
            if action in {
                "get_subject",
                "search_local_subjects",
                "search_mixed_subjects",
            }:
                assert f"owner-only-{index}" in encoded
            elif action == "search_remote_subjects":
                assert result["subjects"] == []
            else:
                assert result["air_time"] == "2026-10-20T12:00:00"


@pytest.mark.api
@pytest.mark.integration
async def test_subjects_not_found_and_null_air_time_are_distinct(
    api_client, db_session, monkeypatch
):
    from app.capabilities.subjects import SubjectCapability

    owners = await _seed(db_session)
    capability = SubjectCapability()
    trusted = {"db": db_session, "user_id": owners[0].id, "source": "bangumi"}
    absent = await capability.execute(
        "get_subject_air_time", **trusted, source_id="absent"
    )
    assert absent["success"] is False and absent["error_type"] == "not_found"
    subject = (
        await db_session.execute(select(Subject).where(Subject.source_id == "501"))
    ).scalar_one()
    subject.air_time = None
    subject.air_weekday = None
    db_session.add(subject)
    await db_session.commit()
    present = await capability.execute(
        "get_subject_air_time", **trusted, source_id="501"
    )
    assert present == {
        "success": True,
        "source": "bangumi",
        "source_id": "501",
        "air_time": None,
        "air_weekday": None,
    }

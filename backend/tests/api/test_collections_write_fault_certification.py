"""Canonical HTTP outcomes when real collection writes commit before a fault."""

from __future__ import annotations

import asyncio
from dataclasses import replace
import json
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.capabilities import collections as boundary
from app.capabilities.collections import CollectionCapability
from app.core.security import create_access_token
from app.models.agent_run import AgentInvocation, AgentRunEvent
from app.schemas.user import UserRead
from tests.api import test_collections_write_certification as support
from tests.capabilities.test_collections_write_semantics import _dispatch, _runtime

_EVIDENCE: list[dict[str, Any]] = []


@pytest.mark.api
@pytest.mark.integration
@pytest.mark.parametrize("action", support.ACTIONS)
@pytest.mark.parametrize("fault", ["raise", "timeout"])
async def test_real_write_fault_has_canonical_terminal_and_no_duplicate(
    action, fault, api_client, db_session, initialized_cache, monkeypatch, tmp_path
):
    owner, foreign = await support._seed(db_session)
    assert owner.id is not None and foreign.id is not None
    calls, _, response_slot = support._install_service_counters(action, monkeypatch)
    arguments = support._arguments(action, "approved")
    if action == "sync_bangumi_collections":
        response_slot["value"] = arguments.pop("_synthetic_bangumi_response")
    symbol = {
        "create_collection": "create_collection",
        "update_collection": "update_collection",
        "delete_collection": "delete_collection",
        "upsert_collection": "upsert_collection",
        "batch_upsert_collections": "batch_upsert_collections",
        "import_json_collections": "import_json_collections",
        "sync_bangumi_collections": "sync_user_collections",
        "sync_douban_collections": "sync_user_collections_douban",
    }[action]
    real_service = getattr(boundary, symbol)
    entered, cleaned = asyncio.Event(), asyncio.Event()

    async def fault_after_commit(*args, **kwargs):
        result = await real_service(*args, **kwargs)
        entered.set()
        try:
            if fault == "raise":
                raise RuntimeError("synthetic-private-post-commit-fault")
            await asyncio.Event().wait()
            return result
        finally:
            cleaned.set()

    monkeypatch.setattr(boundary, symbol, fault_after_commit)
    original_actions = CollectionCapability.actions
    monkeypatch.setattr(
        CollectionCapability,
        "actions",
        lambda self: [
            replace(item, timeout_seconds=1.0) if item.name == action else item
            for item in original_actions(self)
        ],
    )
    before = await support._business_snapshot(db_session)
    headers, thread, initial, _, _ = await support._chat(
        api_client,
        owner,
        action,
        arguments,
        tmp_path / "fault-checkpoint.db",
        monkeypatch,
    )
    run_ids = {frame["run_id"] for frame in initial if frame.get("run_id")}
    assert len(run_ids) == 1
    run_id = run_ids.pop()
    assert (await support._read_run(api_client, run_id, headers))["status"] == "paused"
    assert await support._business_snapshot(db_session) == before
    assert calls == []
    response = await api_client.post(
        "/api/v1/chat/resume",
        params=support._resume_params(thread, run_id, "approve"),
        headers=headers,
    )
    assert response.status_code == 200
    ends = [
        frame
        for frame in support._frames(response.text)
        if frame.get("_event_type") == "tool_call_end"
    ]
    assert len(ends) == 1
    assert entered.is_set() and cleaned.is_set() and calls == [action]
    assert ends[0]["status"] == ("timeout" if fault == "timeout" else "failed")
    assert ends[0]["output"]["error_type"] == (
        "timeout" if fault == "timeout" else "attention_required"
    )
    assert "synthetic-private-post-commit" not in json.dumps(ends)
    canonical = await support._read_run(api_client, run_id, headers)
    assert canonical["status"] == "failed"
    invocation = (
        await db_session.execute(
            select(AgentInvocation).where(AgentInvocation.run_id == run_id)
        )
    ).scalar_one()
    assert invocation.status == ("timed_out" if fault == "timeout" else "failed")
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
    assert len(terminal) == 1 and terminal[0].event_type == "run.failed"
    assert len({event.sequence for event in events}) == len(events)
    trace = await api_client.get(f"/api/v1/trace/{run_id}", headers=headers)
    assert trace.status_code == 200 and trace.json()["user_id"] == owner.id
    foreign_headers = {
        "Authorization": f"Bearer {create_access_token({'sub': str(foreign.id)})}"
    }
    for path in (f"/api/v1/trace/{run_id}", f"/api/v1/runs/{run_id}"):
        assert (await api_client.get(path, headers=foreign_headers)).status_code == 404
    user = UserRead.model_validate(owner, from_attributes=True)
    factory = async_sessionmaker(
        db_session.bind, class_=AsyncSession, expire_on_commit=False
    )
    async with factory() as fresh:
        after = await support._business_snapshot(fresh)
        support._assert_business_write(
            action, "approved", owner.id, foreign.id, before, after
        )
        key = arguments["idempotency_key"]
        replay_arguments = {
            name: value
            for name, value in arguments.items()
            if name != "idempotency_key"
        }
        replay = await _dispatch(
            _runtime(fresh, user, action), user, action, key, **replay_arguments
        )
        assert replay.error_code == "attention_required" and not replay.retryable
        assert calls == [action] and await support._business_snapshot(fresh) == after
    assert (await support._read_run(api_client, run_id, headers))["status"] == "failed"
    _EVIDENCE.append(
        {
            "action": action,
            "fault": fault,
            "run_id": run_id,
            "run_status": canonical["status"],
            "invocation_status": invocation.status,
            "terminal_events": len(terminal),
            "trace_owner_matches": True,
            "fresh_runtime_replay": "attention_required",
            "actual_service_calls": len(calls),
        }
    )
    artifact = (
        Path(__file__).resolve().parents[2]
        / ".runtime/capability-contracts/collections-write-http-faults.json"
    )
    artifact.parent.mkdir(parents=True, exist_ok=True)
    artifact.write_text(
        json.dumps(
            {"expected_cases": 16, "passed_cases": len(_EVIDENCE), "cases": _EVIDENCE},
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

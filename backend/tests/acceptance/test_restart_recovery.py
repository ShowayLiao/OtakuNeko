from __future__ import annotations

from datetime import datetime, timedelta, timezone

import httpx
import pytest
from fastapi import FastAPI

from app.api.deps import get_current_user, get_session
from app.api.v1 import agent as agent_api
from app.api.v1.agent import _recover_stale_run, router
from app.harness.checkpoint import SqliteCheckpointStore
from app.harness.persistence.run_store import RunStore
from app.harness.state import AgentState
from app.harness.task import AgentTask
from app.models.agent_run import AgentRun
from app.schemas.user import UserRead


def _user(user_id: int) -> UserRead:
    return UserRead(
        id=user_id,
        username=f"user-{user_id}",
        created_at=datetime.now(timezone.utc),
    )


@pytest.mark.asyncio
async def test_restart_reopens_checkpoint_and_marks_stale_run_abandoned(
    db_session, tmp_path, monkeypatch
) -> None:
    checkpoint_path = str(tmp_path / "restart" / "checkpoints.db")
    monkeypatch.setattr(agent_api.settings, "CHECKPOINT_DB_PATH", checkpoint_path)
    monkeypatch.setattr(agent_api.settings, "CHECKPOINT_LEASE_SECONDS", 1)
    checkpoint = SqliteCheckpointStore(checkpoint_path)
    await checkpoint.save(
        "run-stale",
        "thread-stale",
        AgentState(
            task=AgentTask(user_id=7, goal="restart"),
            status="running",
        ),
    )
    await checkpoint.close()

    reopened = SqliteCheckpointStore(checkpoint_path)
    assert (await reopened.load("run-stale", "thread-stale")).status == "running"

    run_store = RunStore(db_session)
    await run_store.create(
        run_id="run-stale",
        user_id=7,
        thread_id="user:7:thread:thread-stale",
        status="running",
        goal_hash="goal-hash",
        model="test-model",
    )
    stored = await db_session.get(AgentRun, "run-stale")
    stored.started_at = datetime.now(timezone.utc) - timedelta(hours=2)
    db_session.add(stored)
    await db_session.commit()
    stale = await run_store.get("run-stale", user_id=7)
    recovered = await _recover_stale_run(stale, db_session)
    abandoned = await reopened.load("run-stale", "thread-stale")
    await reopened.close()

    assert recovered.status == "abandoned"
    assert recovered.error_code == "checkpoint_lease_expired"
    assert abandoned.status == "abandoned"
    assert abandoned.context["abandon_reason"]


@pytest.mark.asyncio
async def test_resume_requires_owner_thread_and_run_scope(db_session, monkeypatch) -> None:
    monkeypatch.setenv("HARNESS_PRIMARY_DECISION_LOOP_ENABLED", "false")
    run_store = RunStore(db_session)
    await run_store.create(
        run_id="run-approval",
        user_id=7,
        thread_id="user:7:thread:thread-1",
        status="running",
        goal_hash="goal-hash",
        model="test-model",
    )

    class FakeWorkflow:
        instances = []

        def __init__(self, **kwargs):
            self.app = self
            self.kwargs = kwargs
            self.closed = False
            self.__class__.instances.append(self)

        async def _ensure_checkpointer(self):
            return None

        async def astream_events(self, *args, **kwargs):
            if False:
                yield args, kwargs

        async def close(self):
            self.closed = True

    monkeypatch.setattr(agent_api, "ChatWorkflow", FakeWorkflow)
    current_user = _user(7)

    app = FastAPI()
    app.include_router(router, prefix="/v1")

    async def override_user() -> UserRead:
        return current_user

    async def override_session():
        yield db_session

    app.dependency_overrides[get_current_user] = override_user
    app.dependency_overrides[get_session] = override_session

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        accepted = await client.post(
            "/v1/chat/resume?thread_id=thread-1&run_id=run-approval&decision=approve"
        )
        assert accepted.status_code == 200
        assert FakeWorkflow.instances[-1].kwargs["run_id"] == "run-approval"
        assert FakeWorkflow.instances[-1].kwargs["thread_id"] == "user:7:thread:thread-1"

        current_user = _user(8)
        cross_user = await client.post(
            "/v1/chat/resume?thread_id=thread-1&run_id=run-approval&decision=approve"
        )
        assert cross_user.status_code == 404

        current_user = _user(7)
        wrong_thread = await client.post(
            "/v1/chat/resume?thread_id=other-thread&run_id=run-approval&decision=approve"
        )
        assert wrong_thread.status_code == 404

"""PostgreSQL lifecycle coverage for scheduled task UTC timestamps."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.harness.scheduler.repository import SqlTaskRepository
from app.models.agent_task import AgentTaskDef, AgentTaskRun
from app.models.user import User


def _session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def _seed_user(factory: async_sessionmaker[AsyncSession], user_id: int) -> None:
    async with factory() as session:
        session.add(User(id=user_id, username=f"postgres-task-time-{user_id}"))
        await session.commit()


def _utc_naive(value: datetime) -> datetime:
    if value.utcoffset() is None:
        return value.replace(tzinfo=None)
    return value.astimezone(timezone.utc).replace(tzinfo=None)


def _assert_naive_utc(actual: datetime | None, expected: datetime) -> None:
    assert actual is not None
    assert actual.tzinfo is None
    assert actual == _utc_naive(expected)


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.db
@pytest.mark.postgres
async def test_postgres_task_definition_lifecycle_binds_utc_and_scopes_owner(
    postgres_engine: AsyncEngine,
) -> None:
    factory = _session_factory(postgres_engine)
    owner_id, other_user_id = 811, 812
    await _seed_user(factory, owner_id)
    await _seed_user(factory, other_user_id)
    repository = SqlTaskRepository(factory)
    due_offset = datetime(2035, 1, 2, 11, 4, tzinfo=timezone(timedelta(hours=8)))
    payload = {"nested": {"titles": ["夜更かし", "番組"]}, "enabled": False}
    policy = {"allowed_capabilities": ["catalog.search"], "max_retries": 2}
    task = AgentTaskDef(
        user_id=owner_id,
        task_type="memory_summary",
        payload=json.dumps(payload, ensure_ascii=False),
        schedule_expr="* * * * *",
        timezone="UTC",
        next_run=due_offset,
        catch_up="all",
        policy=json.dumps(policy, ensure_ascii=False),
    )

    added = await repository.add(task)
    assert added.id is not None
    async with factory() as session:
        row = (
            (
                await session.execute(
                    text(
                        "SELECT next_run, created_at, updated_at, deleted_at "
                        "FROM agent_task_def WHERE id = :task_id"
                    ),
                    {"task_id": added.id},
                )
            )
            .mappings()
            .one()
        )
    _assert_naive_utc(row["next_run"], due_offset)
    _assert_naive_utc(row["created_at"], added.created_at)
    _assert_naive_utc(row["updated_at"], added.updated_at)
    assert row["deleted_at"] is None

    listed = await repository.list_for_user(owner_id)
    assert len(listed) == 1
    assert json.loads(listed[0].payload) == payload
    assert json.loads(listed[0].policy) == policy
    assert await repository.list_for_user(other_user_id) == []
    assert await repository.runs_for(added.id, other_user_id) is None
    assert await repository.set_enabled(added.id, other_user_id, False) is None
    assert (
        await repository.update(
            added.id, other_user_id, {"schedule_expr": "*/2 * * * *"}
        )
        is None
    )
    assert await repository.delete(added.id, other_user_id) is False

    old_update = datetime(2001, 2, 3, 4, 5, 6)
    async with factory() as session:
        await session.execute(
            text("UPDATE agent_task_def SET updated_at = :stamp WHERE id = :task_id"),
            {"stamp": old_update, "task_id": added.id},
        )
        await session.commit()

    paused = await repository.set_enabled(added.id, owner_id, False)
    assert paused is not None and paused.enabled is False
    async with factory() as session:
        after_pause = (
            (
                await session.execute(
                    text(
                        "SELECT created_at, updated_at FROM agent_task_def "
                        "WHERE id = :task_id"
                    ),
                    {"task_id": added.id},
                )
            )
            .mappings()
            .one()
        )
    _assert_naive_utc(after_pause["created_at"], added.created_at)
    assert after_pause["updated_at"].tzinfo is None
    assert after_pause["updated_at"] > old_update

    updated = await repository.update(
        added.id,
        owner_id,
        {"schedule_expr": "*/2 * * * *", "timezone": "Asia/Shanghai"},
    )
    assert updated is not None
    assert updated.schedule_expr == "*/2 * * * *"
    assert updated.timezone == "Asia/Shanghai"
    async with factory() as session:
        after_schedule = (
            (
                await session.execute(
                    text(
                        "SELECT next_run, updated_at FROM agent_task_def WHERE id = :id"
                    ),
                    {"id": added.id},
                )
            )
            .mappings()
            .one()
        )
    assert after_schedule["next_run"].tzinfo is None
    assert after_schedule["updated_at"].tzinfo is None

    assert await repository.delete(added.id, owner_id) is True
    async with factory() as session:
        deleted = (
            (
                await session.execute(
                    text(
                        "SELECT enabled, deleted_at, created_at, updated_at "
                        "FROM agent_task_def WHERE id = :id"
                    ),
                    {"id": added.id},
                )
            )
            .mappings()
            .one()
        )
    assert deleted["enabled"] is False
    assert deleted["deleted_at"].tzinfo is None
    _assert_naive_utc(deleted["created_at"], added.created_at)
    assert deleted["updated_at"].tzinfo is None


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.db
@pytest.mark.postgres
async def test_postgres_task_lease_reclaim_rejects_stale_finish_and_persists_result(
    postgres_engine: AsyncEngine,
) -> None:
    factory = _session_factory(postgres_engine)
    user_id = 813
    await _seed_user(factory, user_id)
    repository = SqlTaskRepository(factory)
    slot = datetime(2035, 4, 5, 6, 7, tzinfo=timezone.utc)
    task = AgentTaskDef(
        user_id=user_id,
        task_type="memory_summary",
        schedule_expr="* * * * *",
        timezone="UTC",
        next_run=slot,
        catch_up="all",
        payload=json.dumps({"scope": ["anime", "watchlist"]}),
        policy=json.dumps({"max_retries": 1}),
    )
    added = await repository.add(task)
    assert added.id is not None

    first_now = slot + timedelta(seconds=5)
    first_claims = await repository.claim_due(first_now, lease_seconds=30, limit=1)
    assert len(first_claims) == 1
    first = first_claims[0]
    assert first.run.attempt == 1
    first_lease_id = first.run.lease_id
    first_lease_expiry = first.run.lease_expires_at
    assert first_lease_id and first_lease_expiry is not None
    assert await repository.claim_due(first_now + timedelta(seconds=10), 30, 1) == []

    reclaimed = await repository.claim_due(first_now + timedelta(seconds=30), 30, 1)
    assert len(reclaimed) == 1
    current = reclaimed[0]
    assert current.run.id == first.run.id
    assert current.run.attempt == 2
    assert current.run.lease_id != first_lease_id
    current_lease_id = current.run.lease_id
    assert current_lease_id
    assert (
        await repository.finish(first.run, success=True, lease_id=first_lease_id)
        is False
    )
    assert (
        await repository.finish(current.run, success=True, lease_id=current_lease_id)
        is True
    )

    runs = await repository.runs_for(added.id, user_id)
    assert runs is not None and len(runs) == 1
    run = runs[0]
    assert run.status == "success"
    assert run.attempt == 2
    assert run.lease_id is None
    assert run.lease_expires_at is None
    assert run.finished_at is not None
    async with factory() as session:
        persisted = (
            (
                await session.execute(
                    text(
                        "SELECT scheduled_slot, lease_expires_at, finished_at, created_at "
                        "FROM agent_task_run WHERE id = :run_id"
                    ),
                    {"run_id": run.id},
                )
            )
            .mappings()
            .one()
        )
        definition = (
            (
                await session.execute(
                    text("SELECT next_run FROM agent_task_def WHERE id = :task_id"),
                    {"task_id": added.id},
                )
            )
            .mappings()
            .one()
        )
    _assert_naive_utc(persisted["scheduled_slot"], slot)
    assert persisted["lease_expires_at"] is None
    _assert_naive_utc(persisted["finished_at"], run.finished_at)
    _assert_naive_utc(persisted["created_at"], run.created_at)
    _assert_naive_utc(definition["next_run"], slot + timedelta(minutes=1))


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.db
@pytest.mark.postgres
async def test_postgres_task_run_accepts_aware_and_naive_optional_timestamps(
    postgres_engine: AsyncEngine,
) -> None:
    factory = _session_factory(postgres_engine)
    user_id = 814
    await _seed_user(factory, user_id)
    task = await SqlTaskRepository(factory).add(
        AgentTaskDef(
            user_id=user_id,
            task_type="memory_summary",
            schedule_expr="* * * * *",
            timezone="UTC",
            next_run=None,
        )
    )
    assert task.id is not None
    scheduled_slot = datetime(2036, 1, 2, 3, 4, tzinfo=timezone.utc)
    started_at = scheduled_slot + timedelta(seconds=2)
    lease_expires_at = scheduled_slot + timedelta(minutes=1)
    created_at = scheduled_slot - timedelta(minutes=1)
    aware_run = AgentTaskRun(
        task_def_id=task.id,
        user_id=user_id,
        scheduled_slot=scheduled_slot,
        lease_expires_at=lease_expires_at,
        started_at=started_at,
        finished_at=None,
        created_at=created_at,
        status="running",
        lease_id="aware-lease",
    )
    naive_slot = datetime(2036, 1, 2, 4, 4)
    naive_run = AgentTaskRun(
        task_def_id=task.id,
        user_id=user_id,
        scheduled_slot=naive_slot,
        lease_expires_at=None,
        started_at=None,
        finished_at=None,
        created_at=datetime(2036, 1, 2, 3, 4),
        status="pending",
    )
    async with factory() as session:
        session.add_all([aware_run, naive_run])
        await session.commit()
        await session.refresh(aware_run)
        await session.refresh(naive_run)

    async with factory() as session:
        rows = (
            (
                await session.execute(
                    text(
                        "SELECT scheduled_slot, lease_expires_at, started_at, finished_at, "
                        "created_at, lease_id FROM agent_task_run "
                        "WHERE task_def_id = :task_id ORDER BY scheduled_slot"
                    ),
                    {"task_id": task.id},
                )
            )
            .mappings()
            .all()
        )
    assert len(rows) == 2
    _assert_naive_utc(rows[0]["scheduled_slot"], scheduled_slot)
    _assert_naive_utc(rows[0]["lease_expires_at"], lease_expires_at)
    _assert_naive_utc(rows[0]["started_at"], started_at)
    assert rows[0]["finished_at"] is None
    _assert_naive_utc(rows[0]["created_at"], created_at)
    assert rows[0]["lease_id"] == "aware-lease"
    assert rows[1]["scheduled_slot"] == naive_slot
    assert rows[1]["scheduled_slot"].tzinfo is None
    assert rows[1]["lease_expires_at"] is None
    assert rows[1]["started_at"] is None
    assert rows[1]["finished_at"] is None
    assert rows[1]["created_at"] == datetime(2036, 1, 2, 3, 4)

    loaded = await SqlTaskRepository(factory).runs_for(task.id, user_id)
    assert loaded is not None and len(loaded) == 2
    loaded.sort(key=lambda run: run.scheduled_slot)
    assert loaded[0].scheduled_slot.tzinfo is None
    assert loaded[0].lease_expires_at is not None
    assert loaded[0].lease_expires_at.tzinfo is None


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.db
@pytest.mark.postgres
@pytest.mark.api
async def test_postgres_proactive_http_creates_updates_and_deletes_task(
    postgres_engine: AsyncEngine,
) -> None:
    from fastapi import FastAPI
    from httpx import ASGITransport, AsyncClient

    from app.api.deps import get_current_user
    from app.api.v1.proactive import router
    from app.schemas.user import UserRead

    factory = _session_factory(postgres_engine)
    await _seed_user(factory, 815)
    await _seed_user(factory, 816)
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")
    repository = SqlTaskRepository(factory)
    app.state.proactive_repository = repository
    principal = UserRead(
        id=815, username="postgres-http-owner", created_at=datetime.now(timezone.utc)
    )

    async def current_user() -> UserRead:
        return principal

    app.dependency_overrides[get_current_user] = current_user
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        created = await client.post(
            "/api/v1/proactive",
            json={
                "task_type": "memory_summary",
                "schedule_expr": "* * * * *",
                "timezone": "Asia/Shanghai",
            },
        )
        assert created.status_code == 201
        task_id = created.json()["id"]
        assert created.json()["next_run"] is not None
        principal = UserRead(
            id=816,
            username="postgres-http-other",
            created_at=datetime.now(timezone.utc),
        )
        denied = await client.patch(
            f"/api/v1/proactive/{task_id}", json={"schedule_expr": "*/2 * * * *"}
        )
        assert denied.status_code == 404
        principal = UserRead(
            id=815,
            username="postgres-http-owner",
            created_at=datetime.now(timezone.utc),
        )
        updated = await client.patch(
            f"/api/v1/proactive/{task_id}", json={"schedule_expr": "*/2 * * * *"}
        )
        assert updated.status_code == 200
        assert updated.json()["schedule_expr"] == "*/2 * * * *"
        assert updated.json()["next_run"] is not None
        deleted = await client.delete(f"/api/v1/proactive/{task_id}")
        assert deleted.status_code == 204
    assert await repository.list_for_user(815) == []

from __future__ import annotations

import os

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlmodel import SQLModel, select

from app.harness.persistence.run_store import (
    InvalidRunTransition,
    RunConflict,
    RunStore,
)
from app.models.agent_run import AgentRun


@pytest.mark.asyncio
async def test_run_store_create_get_and_transition(db_session) -> None:
    store = RunStore(db_session)
    created = await store.create(
        run_id="run-1",
        user_id=7,
        thread_id="thread-1",
        status="queued",
        goal_hash="goal-hash",
        model="test-model",
    )

    assert created.run_id == "run-1"
    assert created.status == "queued"
    assert (await store.get("run-1", user_id=7)).model == "test-model"
    assert await store.get("run-1", user_id=8) is None

    running = await store.transition("run-1", "running")
    succeeded = await store.transition("run-1", "succeeded")
    assert running.status == "running"
    assert succeeded.status == "succeeded"
    assert succeeded.finished_at is not None

    with pytest.raises(InvalidRunTransition):
        await store.transition("run-1", "failed")


@pytest.mark.asyncio
async def test_run_store_create_is_idempotent_for_same_run_id(db_session) -> None:
    store = RunStore(db_session)
    first = await store.create(
        run_id="run-idempotent",
        user_id=None,
        thread_id=None,
        status="queued",
        goal_hash="hash-a",
        model="model-a",
    )
    second = await store.create(
        run_id="run-idempotent",
        user_id=None,
        thread_id=None,
        status="queued",
        goal_hash="hash-a",
        model="model-a",
    )

    assert first.run_id == second.run_id
    rows = (await db_session.exec(select(AgentRun))).all()
    assert len(rows) == 1


@pytest.mark.asyncio
async def test_run_store_invocation_idempotency_is_deterministic(db_session) -> None:
    store = RunStore(db_session)
    await store.create(
        run_id="run-invocation",
        user_id=None,
        thread_id=None,
        status="queued",
        goal_hash="hash",
        model="model",
    )
    first = await store.create_invocation(
        run_id="run-invocation",
        invocation_id="invocation-1",
        sequence=1,
        capability="anime.search",
        input_payload={"query": "frieren"},
        idempotency_key="same-request",
    )
    duplicate = await store.create_invocation(
        run_id="run-invocation",
        invocation_id="invocation-2",
        sequence=2,
        capability="anime.search",
        input_payload={"query": "frieren"},
        idempotency_key="same-request",
    )

    assert duplicate.invocation_id == first.invocation_id
    with pytest.raises(RunConflict):
        await store.create_invocation(
            run_id="run-invocation",
            invocation_id="invocation-3",
            sequence=3,
            capability="anime.search",
            input_payload={"query": "another"},
            idempotency_key="same-request",
        )


@pytest.mark.asyncio
async def test_run_store_round_trip_survives_sqlite_restart(tmp_path) -> None:
    database_url = f"sqlite+aiosqlite:///{(tmp_path / 'runs.db').as_posix()}"
    first_engine = create_async_engine(database_url)
    async with first_engine.begin() as connection:
        await connection.run_sync(SQLModel.metadata.create_all)
    first_factory = async_sessionmaker(first_engine, expire_on_commit=False)
    async with first_factory() as session:
        await RunStore(session).create(
            run_id="run-restart",
            user_id=1,
            thread_id="thread",
            status="queued",
            goal_hash="hash",
            model="model",
        )
    await first_engine.dispose()

    second_engine = create_async_engine(database_url)
    second_factory = async_sessionmaker(second_engine, expire_on_commit=False)
    async with second_factory() as session:
        restored = await RunStore(session).get("run-restart", user_id=1)
    await second_engine.dispose()

    assert restored is not None
    assert restored.status == "queued"


@pytest.mark.asyncio
async def test_postgres_store_is_optional_when_test_url_is_not_configured() -> None:
    url = os.getenv("POSTGRES_TEST_URL")
    if not url:
        pytest.skip("POSTGRES_TEST_URL is not configured")
    pytest.importorskip("asyncpg")
    engine = create_async_engine(url)
    async with engine.begin() as connection:
        await connection.run_sync(SQLModel.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        stored = await RunStore(session).create(
            run_id="run-postgres",
            user_id=None,
            thread_id=None,
            status="queued",
            goal_hash="hash",
            model="model",
        )
        assert stored.run_id == "run-postgres"
    await engine.dispose()

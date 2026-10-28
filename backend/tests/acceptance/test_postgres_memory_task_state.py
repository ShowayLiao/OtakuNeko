"""PostgreSQL acceptance checks for memory transactions and task claiming."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from datetime import datetime, timezone
import json

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.harness.scheduler.repository import Claim, SqlTaskRepository
from app.memory.sql_repository import SqlMemoryRepository
from app.models.agent_task import AgentTaskDef
from app.models.user import User


def _session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def _seed_users(
    factory: async_sessionmaker[AsyncSession], *user_ids: int
) -> None:
    async with factory() as session:
        session.add_all(
            [
                User(id=user_id, username=f"postgres-a-l1-05-user-{user_id}")
                for user_id in user_ids
            ]
        )
        await session.commit()


@pytest.mark.asyncio
@pytest.mark.db
@pytest.mark.postgres
async def test_postgres_memory_commit_rollback_and_owner_scoped_json_roundtrip(
    postgres_engine: AsyncEngine,
    record_property: Callable[[str, object], None],
) -> None:
    factory = _session_factory(postgres_engine)
    await _seed_users(factory, 501, 502)
    metadata = {
        "nested": {
            "title": "追番记录",
            "values": [None, True, False, 1.25],
        },
        "enabled": False,
    }

    async with factory() as writer_session:
        writer = SqlMemoryRepository(writer_session)
        await writer.put_fact(
            thread_id="transaction-check",
            fact_id="rolled-back-fact",
            content="temporary fact",
            importance=0.5,
            source="acceptance-test",
            user_id=501,
            metadata=metadata,
        )
        async with factory() as independent_reader_session:
            independent_reader = SqlMemoryRepository(independent_reader_session)
            assert (
                await independent_reader.get_facts("transaction-check", user_id=501)
                == []
            )
        await writer.rollback()

    async with factory() as session:
        repository = SqlMemoryRepository(session)
        assert await repository.count_facts("transaction-check", user_id=501) == 0
        await repository.put_fact(
            thread_id="transaction-check",
            fact_id="committed-fact",
            content="persisted fact",
            importance=0.75,
            source="acceptance-test",
            user_id=501,
            metadata=metadata,
        )
        await repository.commit()

    async with factory() as session:
        repository = SqlMemoryRepository(session)
        facts = await repository.get_facts("transaction-check", user_id=501)
        assert len(facts) == 1
        assert facts[0]["id"] == "committed-fact"
        assert facts[0]["metadata"] == metadata
        assert facts[0]["content"] == "persisted fact"
        assert await repository.get_facts("transaction-check", user_id=502) == []

    async with factory() as session:
        other_owner_repository = SqlMemoryRepository(session)
        await other_owner_repository.put_fact(
            thread_id="transaction-check",
            fact_id="other-owner-fact",
            content="other owner fact",
            importance=0.25,
            source="acceptance-test",
            user_id=502,
        )
        await other_owner_repository.commit()

    async with factory() as session:
        owner_repository = SqlMemoryRepository(session)
        owner_facts = await owner_repository.get_facts("transaction-check", user_id=501)
        other_owner_facts = await owner_repository.get_facts(
            "transaction-check", user_id=502
        )
        assert [fact["id"] for fact in owner_facts] == ["committed-fact"]
        assert [fact["id"] for fact in other_owner_facts] == ["other-owner-fact"]

    record_property("memory_uncommitted_write_hidden_from_reader", "true")
    record_property("memory_rollback_rows_remaining", "0")
    record_property("memory_json_roundtrip", "unicode_nested_null_boolean_finite")
    record_property("memory_owner_scope", "verified")


@pytest.mark.asyncio
@pytest.mark.db
@pytest.mark.postgres
async def test_postgres_memory_concurrent_lock_owner_writers_commit_all_facts(
    postgres_engine: AsyncEngine,
    record_property: Callable[[str, object], None],
) -> None:
    factory = _session_factory(postgres_engine)
    await _seed_users(factory, 501)
    writer_count = 4
    ready: asyncio.Queue[int] = asyncio.Queue()
    start_writes = asyncio.Event()

    async def write_fact(index: int) -> None:
        async with factory() as session:
            backend_pid = await session.scalar(text("SELECT pg_backend_pid()"))
            assert isinstance(backend_pid, int)
            ready.put_nowait(backend_pid)
            await start_writes.wait()

            repository = SqlMemoryRepository(session)
            await repository.lock_owner(501)
            await repository.put_fact(
                thread_id="parallel-writers",
                fact_id=f"parallel-fact-{index}",
                content=f"parallel content {index}",
                importance=0.5,
                source="acceptance-test",
                user_id=501,
            )
            await repository.commit()

    tasks = [asyncio.create_task(write_fact(index)) for index in range(writer_count)]
    try:
        backend_pids = {
            await asyncio.wait_for(ready.get(), timeout=10) for _ in range(writer_count)
        }
        assert len(backend_pids) == writer_count
        start_writes.set()
        await asyncio.wait_for(asyncio.gather(*tasks), timeout=20)
    except BaseException:
        start_writes.set()
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        raise

    async with factory() as session:
        repository = SqlMemoryRepository(session)
        facts = await repository.get_facts("parallel-writers", user_id=501)
        assert {fact["id"] for fact in facts} == {
            f"parallel-fact-{index}" for index in range(writer_count)
        }
        assert (
            await repository.count_facts("parallel-writers", user_id=501)
            == writer_count
        )

    record_property("memory_concurrent_writer_count", str(writer_count))
    record_property("memory_distinct_backend_count", str(len(backend_pids)))
    record_property("memory_concurrent_committed_rows", str(writer_count))


@pytest.mark.asyncio
@pytest.mark.db
@pytest.mark.postgres
async def test_postgres_memory_unique_conflict_rolls_back_and_session_recovers(
    postgres_engine: AsyncEngine,
    record_property: Callable[[str, object], None],
) -> None:
    factory = _session_factory(postgres_engine)
    await _seed_users(factory, 501)

    async with factory() as session:
        repository = SqlMemoryRepository(session)
        await repository.put_fact(
            thread_id="unique-conflict",
            fact_id="same-fact",
            content="original value",
            importance=0.5,
            source="acceptance-test",
            user_id=501,
        )
        await repository.commit()

        with pytest.raises(IntegrityError):
            await repository.put_fact(
                thread_id="unique-conflict",
                fact_id="same-fact",
                content="conflicting value",
                importance=0.5,
                source="acceptance-test",
                user_id=501,
            )

        await repository.rollback()
        after_rollback = await repository.get_facts("unique-conflict", user_id=501)
        assert len(after_rollback) == 1
        assert after_rollback[0]["content"] == "original value"

        await repository.put_fact(
            thread_id="unique-conflict",
            fact_id="after-rollback",
            content="recovered value",
            importance=0.5,
            source="acceptance-test",
            user_id=501,
        )
        await repository.commit()

    async with factory() as session:
        facts = await SqlMemoryRepository(session).get_facts(
            "unique-conflict", user_id=501
        )
        assert {fact["id"] for fact in facts} == {"same-fact", "after-rollback"}
        assert {fact["content"] for fact in facts} == {
            "original value",
            "recovered value",
        }

    record_property("memory_conflict_category", "unique_constraint")
    record_property("memory_conflict_rollback_count", "1")
    record_property("memory_session_recovery_after_rollback", "verified")


@pytest.mark.asyncio
@pytest.mark.db
@pytest.mark.postgres
async def test_postgres_memory_rejects_non_json_metadata_without_poisoning_session(
    postgres_engine: AsyncEngine,
    record_property: Callable[[str, object], None],
) -> None:
    factory = _session_factory(postgres_engine)
    await _seed_users(factory, 501)

    async with factory() as session:
        repository = SqlMemoryRepository(session)
        with pytest.raises(ValueError):
            await repository.put_fact(
                thread_id="metadata-validation",
                fact_id="invalid-metadata",
                content="invalid metadata must not be stored",
                importance=0.5,
                source="acceptance-test",
                user_id=501,
                metadata={"nested": {"not_finite": float("nan")}},
            )

        await repository.put_fact(
            thread_id="metadata-validation",
            fact_id="valid-metadata",
            content="valid write after rejection",
            importance=0.5,
            source="acceptance-test",
            user_id=501,
            metadata={"valid": True},
        )
        await repository.commit()

    async with factory() as session:
        facts = await SqlMemoryRepository(session).get_facts(
            "metadata-validation", user_id=501
        )
        assert [fact["id"] for fact in facts] == ["valid-metadata"]

    record_property("memory_non_finite_metadata_rejected", "true")
    record_property("memory_valid_write_after_metadata_rejection", "true")


@pytest.mark.asyncio
@pytest.mark.db
@pytest.mark.postgres
async def test_postgres_task_state_roundtrip_and_concurrent_due_claim_has_one_owner(
    postgres_engine: AsyncEngine,
    record_property: Callable[[str, object], None],
) -> None:
    factory = _session_factory(postgres_engine)
    await _seed_users(factory, 501)
    task_repository = SqlTaskRepository(factory)
    due_slot = datetime(2030, 1, 1, 0, 0, tzinfo=timezone.utc)
    payload = {"anime": {"ids": [12, 34], "include_completed": False}}
    policy = {
        "allowed_capabilities": ["catalog.search"],
        "max_retries": 2,
        "timeout_seconds": 30,
        "max_model_calls": 4,
    }
    task = AgentTaskDef(
        user_id=501,
        task_type="memory_summary",
        payload=json.dumps(payload, ensure_ascii=False),
        schedule_expr="* * * * *",
        timezone="UTC",
        next_run=due_slot,
        policy=json.dumps(policy, ensure_ascii=False),
    )
    record_property("task_persistence_stage", "definition_insert")
    record_property("task_concurrency_reached", "false")
    added = await task_repository.add(task)
    assert added.id is not None

    tasks = await task_repository.list_for_user(501)
    assert len(tasks) == 1
    loaded = tasks[0]
    assert loaded.id == added.id
    assert json.loads(loaded.payload) == payload
    assert json.loads(loaded.policy) == policy
    assert loaded.next_run is not None
    stored_next_run = loaded.next_run
    if stored_next_run.tzinfo is None:
        stored_next_run = stored_next_run.replace(tzinfo=timezone.utc)
    assert stored_next_run == due_slot

    record_property("task_persistence_stage", "concurrent_claim")
    record_property("task_concurrency_reached", "true")

    claims: tuple[list[Claim], list[Claim]] = await asyncio.wait_for(
        asyncio.gather(
            task_repository.claim_due(due_slot, lease_seconds=60, limit=1),
            task_repository.claim_due(due_slot, lease_seconds=60, limit=1),
        ),
        timeout=20,
    )
    assert sum(len(owner_claims) for owner_claims in claims) == 1
    assert claims[0] + claims[1]

    persisted_runs = await task_repository.runs_for(added.id, 501)
    assert persisted_runs is not None
    assert len(persisted_runs) == 1
    assert persisted_runs[0].status == "running"
    assert persisted_runs[0].attempt == 1
    stored_slot = persisted_runs[0].scheduled_slot
    if stored_slot.tzinfo is None:
        stored_slot = stored_slot.replace(tzinfo=timezone.utc)
    assert stored_slot == due_slot

    record_property("task_payload_policy_roundtrip", "verified")
    record_property("task_concurrent_claim_count", "1")
    record_property("task_persisted_run_count", str(len(persisted_runs)))
    record_property("task_persisted_attempt_count", str(persisted_runs[0].attempt))

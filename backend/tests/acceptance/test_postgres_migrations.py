from __future__ import annotations

import json
import os
from contextlib import asynccontextmanager
from datetime import datetime, time, timezone
from pathlib import Path
from typing import AsyncIterator, Literal
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import UniqueConstraint, inspect, text
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool
from sqlmodel import SQLModel, col, select

import app.models  # noqa: F401
from app.models import (
    Collection,
    CollectionStatus,
    Schedule,
    Subject,
    SubjectType,
    User,
)
from app.models.agent_trace import AgentTraceModel, TraceEventModel
from app.models.enums import WatchType
from app.trace import TRACE_LEGACY_SCHEMA_VERSION
from app.trace.sql_store import SqlTraceStore
from tests.isolation_support import validate_postgres_url


pytestmark = [pytest.mark.postgres, pytest.mark.integration, pytest.mark.db]

BACKEND_ROOT = Path(__file__).resolve().parents[2]
HEAD_REVISION = "c7d1e4f8a2b6"
TRACE_REVISION = "5ae716ad749d"
BOOTSTRAP_REVISION = "a10300000001"
BUSINESS_TABLES = {
    "users",
    "subject",
    "collection",
    "schedules",
    "anime_broadcast_metadata",
}
TRACE_ID = "postgres-migration-legacy-trace"
TRACE_USER_ID = 804
TRACE_STARTED_AT = datetime(2026, 10, 14, 1, 2, 3, tzinfo=timezone.utc)


@asynccontextmanager
async def _isolated_postgres_schema() -> AsyncIterator[AsyncEngine]:
    """Yield a migration-only engine scoped to a disposable UUID schema."""
    url = validate_postgres_url(os.environ.get("TEST_POSTGRES_URL", ""))
    schema = f"test_{uuid4().hex}"
    admin_engine = create_async_engine(url, poolclass=NullPool)
    engine: AsyncEngine | None = None
    created = False
    try:
        async with admin_engine.begin() as connection:
            await connection.execute(text(f'CREATE SCHEMA "{schema}"'))
        created = True
        engine = create_async_engine(
            url,
            poolclass=NullPool,
            connect_args={"server_settings": {"search_path": schema}},
        )
        yield engine
    finally:
        try:
            if engine is not None:
                await engine.dispose()
        finally:
            try:
                if created:
                    async with admin_engine.begin() as connection:
                        await connection.execute(
                            text(f'DROP SCHEMA "{schema}" CASCADE')
                        )
                    async with admin_engine.connect() as connection:
                        exists = await connection.scalar(
                            text(
                                "SELECT EXISTS (SELECT 1 FROM pg_namespace "
                                "WHERE nspname = :schema)"
                            ),
                            {"schema": schema},
                        )
                    assert exists is False, "temporary PostgreSQL schema remains"
            finally:
                await admin_engine.dispose()


def _run_alembic(
    connection: Connection,
    operation: Literal["upgrade", "downgrade"],
    revision: str,
) -> None:
    config = Config(str(BACKEND_ROOT / "alembic.ini"))
    config.attributes["configure_logger"] = False
    config.attributes["connection"] = connection
    getattr(command, operation)(config, revision)


async def _alembic(
    engine: AsyncEngine,
    operation: Literal["upgrade", "downgrade"],
    revision: str,
) -> None:
    async with engine.begin() as connection:
        await connection.run_sync(
            lambda sync_connection: _run_alembic(sync_connection, operation, revision)
        )


async def _revision(engine: AsyncEngine) -> str:
    async with engine.connect() as connection:
        result = await connection.execute(
            text("SELECT version_num FROM alembic_version")
        )
        return str(result.scalar_one())


async def _table_names(engine: AsyncEngine) -> set[str]:
    async with engine.connect() as connection:
        return await connection.run_sync(
            lambda sync_connection: set(inspect(sync_connection).get_table_names())
        )


def _assert_business_metadata(connection: Connection) -> None:
    inspector = inspect(connection)
    assert BUSINESS_TABLES <= set(inspector.get_table_names())

    for name in sorted(BUSINESS_TABLES):
        expected = SQLModel.metadata.tables[name]
        live_columns = {
            column["name"]: column for column in inspector.get_columns(name)
        }
        assert set(live_columns) == set(expected.columns.keys())
        for column in expected.columns:
            actual = live_columns[column.name]
            assert actual["nullable"] == column.nullable
            assert (
                actual["type"].compile(dialect=connection.dialect).upper()
                == column.type.compile(dialect=connection.dialect).upper()
            )

        live_primary_key = tuple(
            inspector.get_pk_constraint(name).get("constrained_columns") or ()
        )
        expected_primary_key = tuple(
            column.name for column in expected.primary_key.columns
        )
        assert live_primary_key == expected_primary_key

        live_indexes = {
            (
                index["name"],
                tuple(index["column_names"]),
                bool(index["unique"]),
            )
            for index in inspector.get_indexes(name)
            if not index.get("duplicates_constraint")
        }
        expected_indexes = {
            (
                index.name,
                tuple(column.name for column in index.columns),
                bool(index.unique),
            )
            for index in expected.indexes
        }
        assert live_indexes == expected_indexes

        live_unique = {
            (
                constraint["name"],
                tuple(constraint["column_names"]),
            )
            for constraint in inspector.get_unique_constraints(name)
        }
        expected_unique = {
            (
                constraint.name,
                tuple(column.name for column in constraint.columns),
            )
            for constraint in expected.constraints
            if isinstance(constraint, UniqueConstraint)
        }
        assert live_unique == expected_unique

        live_foreign_keys = {
            (
                tuple(key["constrained_columns"]),
                key["referred_table"],
                tuple(key["referred_columns"]),
                (key.get("options") or {}).get("ondelete"),
            )
            for key in inspector.get_foreign_keys(name)
        }
        expected_foreign_keys = {
            (
                tuple(element.parent.name for element in constraint.elements),
                constraint.elements[0].column.table.name,
                tuple(element.column.name for element in constraint.elements),
                constraint.ondelete,
            )
            for constraint in expected.foreign_key_constraints
        }
        assert live_foreign_keys == expected_foreign_keys


async def _insert_business_rows(
    engine: AsyncEngine, *, username: str, source_id: str
) -> dict[str, tuple[object, ...]]:
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        user = User(username=username, bangumi_id=4200, sign="pg-migration-test")
        session.add(user)
        await session.flush()

        subject = Subject(
            source="bangumi",
            source_id=source_id,
            type=SubjectType.ANIME,
            name="PostgreSQL Migration Fixture",
            name_cn="PostgreSQL 迁移样本",
            summary="business row preservation check",
        )
        collection = Collection(
            user_id=user.id,
            source="bangumi",
            source_id=source_id,
            type=CollectionStatus.WISH,
            rate=8,
            comment="preserve this row",
        )
        schedule = Schedule(
            source="bangumi",
            source_id=source_id,
            day_of_week=2,
            start_time=time(20, 30),
            user_id=user.id,
            watch_type=WatchType.NEW,
        )
        session.add_all([subject, collection, schedule])
        await session.commit()

    return await _business_snapshot(engine, username=username, source_id=source_id)


async def _business_snapshot(
    engine: AsyncEngine, *, username: str, source_id: str
) -> dict[str, tuple[object, ...]]:
    factory = async_sessionmaker(engine, class_=AsyncSession)
    async with factory() as session:
        user = (
            (await session.execute(select(User).where(col(User.username) == username)))
            .scalars()
            .one()
        )
        subject = (
            (
                await session.execute(
                    select(Subject).where(col(Subject.source_id) == source_id)
                )
            )
            .scalars()
            .one()
        )
        collection = (
            (
                await session.execute(
                    select(Collection).where(
                        col(Collection.user_id) == user.id,
                        col(Collection.source_id) == source_id,
                    )
                )
            )
            .scalars()
            .one()
        )
        schedule = (
            (
                await session.execute(
                    select(Schedule).where(
                        col(Schedule.user_id) == user.id,
                        col(Schedule.source_id) == source_id,
                    )
                )
            )
            .scalars()
            .one()
        )

        assert user.bangumi_id == 4200
        assert user.sign == "pg-migration-test"
        assert subject.name == "PostgreSQL Migration Fixture"
        assert subject.name_cn == "PostgreSQL 迁移样本"
        assert collection.type == CollectionStatus.WISH
        assert collection.comment == "preserve this row"
        assert schedule.start_time == time(20, 30)
        assert schedule.watch_type == WatchType.NEW
        return {
            "user": (user.id, user.username, user.bangumi_id, user.sign),
            "subject": (
                subject.id,
                subject.source,
                subject.source_id,
                subject.type,
                subject.name,
                subject.name_cn,
                subject.summary,
            ),
            "collection": (
                collection.id,
                collection.user_id,
                collection.source,
                collection.source_id,
                collection.type,
                collection.rate,
                collection.comment,
            ),
            "schedule": (
                schedule.id,
                schedule.user_id,
                schedule.source,
                schedule.source_id,
                schedule.day_of_week,
                schedule.start_time,
                schedule.watch_type,
            ),
        }


async def _seed_legacy_trace(engine: AsyncEngine) -> None:
    headers = {
        "trace_id": TRACE_ID,
        "user_id": TRACE_USER_ID,
        "task_id": 27,
        "agent_name": "legacy-agent",
        "goal": "historical trace",
        "started_at": TRACE_STARTED_AT.isoformat(),
        "status": "completed",
    }
    step = {
        "step_index": 0,
        "step_label": "legacy-step",
        "agent_name": "legacy-agent",
        "started_at": TRACE_STARTED_AT.isoformat(),
        "completed_at": TRACE_STARTED_AT.isoformat(),
        "status": "completed",
        "events": [
            {
                "event_id": "legacy-event-1",
                "event_type": "node_end",
                "timestamp": TRACE_STARTED_AT.isoformat(),
                "status": "completed",
                "data": {"phase": "done"},
            }
        ],
    }
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        session.add(
            AgentTraceModel(
                trace_id=TRACE_ID,
                user_id=TRACE_USER_ID,
                task_id=27,
                agent_name="legacy-agent",
                goal="historical trace",
                status="completed",
                headers_json=json.dumps(headers),
                started_at=TRACE_STARTED_AT,
                created_at=TRACE_STARTED_AT,
            )
        )
        session.add(
            TraceEventModel(
                trace_id=TRACE_ID,
                step_index=0,
                step_label="legacy-step",
                agent_name="legacy-agent",
                status="completed",
                step_json=json.dumps(step),
                created_at=TRACE_STARTED_AT,
            )
        )
        await session.commit()


async def _query_legacy_trace(engine: AsyncEngine, *, user_id: int | None):
    factory = async_sessionmaker(engine, class_=AsyncSession)
    async with factory() as session:
        return await SqlTraceStore(session).query(TRACE_ID, user_id=user_id)


async def _assert_legacy_trace_readable(engine: AsyncEngine) -> None:
    trace = await _query_legacy_trace(engine, user_id=TRACE_USER_ID)
    assert trace is not None
    assert trace.schema_version == TRACE_LEGACY_SCHEMA_VERSION == 1
    assert trace.user_id == TRACE_USER_ID
    assert len(trace.steps) == 1
    assert len(trace.steps[0].events) == 1
    assert trace.steps[0].events[0].schema_version == 1
    assert await _query_legacy_trace(engine, user_id=TRACE_USER_ID + 1) is None
    assert await _query_legacy_trace(engine, user_id=None) is None


@pytest.mark.asyncio
async def test_fresh_postgres_migration_matches_business_metadata_and_preserves_rows(
    record_property,
) -> None:
    async with _isolated_postgres_schema() as engine:
        await _alembic(engine, "upgrade", "head")
        assert await _revision(engine) == HEAD_REVISION
        async with engine.connect() as connection:
            await connection.run_sync(_assert_business_metadata)

        snapshot = await _insert_business_rows(
            engine,
            username="pg-fresh-user",
            source_id="pg-fresh-subject",
        )
        await _alembic(engine, "downgrade", BOOTSTRAP_REVISION)
        assert await _revision(engine) == BOOTSTRAP_REVISION
        async with engine.connect() as connection:
            await connection.run_sync(_assert_business_metadata)
        assert (
            await _business_snapshot(
                engine,
                username="pg-fresh-user",
                source_id="pg-fresh-subject",
            )
            == snapshot
        )

        await _alembic(engine, "upgrade", "head")
        assert await _revision(engine) == HEAD_REVISION
        async with engine.connect() as connection:
            await connection.run_sync(_assert_business_metadata)
        assert (
            await _business_snapshot(
                engine,
                username="pg-fresh-user",
                source_id="pg-fresh-subject",
            )
            == snapshot
        )
        record_property("fresh_schema_revision", HEAD_REVISION)
        record_property("business_metadata_match", "true")
        record_property("business_rows_survived_downgrade_reupgrade", "true")


@pytest.mark.asyncio
async def test_unversioned_current_postgres_schema_is_adopted_idempotently(
    record_property,
) -> None:
    async with _isolated_postgres_schema() as engine:
        async with engine.begin() as connection:
            await connection.run_sync(SQLModel.metadata.create_all)

        business = await _insert_business_rows(
            engine,
            username="pg-adopted-user",
            source_id="pg-adopted-subject",
        )
        await _seed_legacy_trace(engine)

        await _alembic(engine, "upgrade", "head")
        assert await _revision(engine) == HEAD_REVISION
        assert (
            await _business_snapshot(
                engine,
                username="pg-adopted-user",
                source_id="pg-adopted-subject",
            )
            == business
        )
        await _assert_legacy_trace_readable(engine)

        await _alembic(engine, "upgrade", "head")
        assert await _revision(engine) == HEAD_REVISION
        assert (
            await _business_snapshot(
                engine,
                username="pg-adopted-user",
                source_id="pg-adopted-subject",
            )
            == business
        )
        await _assert_legacy_trace_readable(engine)
        record_property("adopted_unversioned_current_schema", "true")
        record_property("repeat_head_upgrade_idempotent", "true")
        record_property("legacy_trace_scope_isolation", "verified")


@pytest.mark.asyncio
async def test_migration_created_legacy_trace_survives_postgres_upgrade_downgrade(
    record_property,
) -> None:
    async with _isolated_postgres_schema() as engine:
        await _alembic(engine, "upgrade", TRACE_REVISION)
        assert await _revision(engine) == TRACE_REVISION
        await _seed_legacy_trace(engine)
        await _assert_legacy_trace_readable(engine)

        await _alembic(engine, "upgrade", "head")
        assert await _revision(engine) == HEAD_REVISION
        await _assert_legacy_trace_readable(engine)

        await _alembic(engine, "downgrade", TRACE_REVISION)
        assert await _revision(engine) == TRACE_REVISION
        await _assert_legacy_trace_readable(engine)

        await _alembic(engine, "upgrade", "head")
        assert await _revision(engine) == HEAD_REVISION
        await _assert_legacy_trace_readable(engine)
        record_property("trace_revision", TRACE_REVISION)
        record_property("head_revision", HEAD_REVISION)
        record_property("legacy_trace_scope_isolation", "verified")
        record_property("legacy_trace_survived_downgrade", "true")


@pytest.mark.asyncio
async def test_postgres_failed_upgrade_rolls_back_and_clean_schema_succeeds(
    record_property,
) -> None:
    async with _isolated_postgres_schema() as failed_engine:
        await _alembic(failed_engine, "upgrade", TRACE_REVISION)
        assert await _revision(failed_engine) == TRACE_REVISION
        async with failed_engine.begin() as connection:
            await connection.execute(
                text(
                    "CREATE TABLE migration_conflict_marker "
                    "(conflict_marker TEXT NOT NULL)"
                )
            )
            await connection.execute(
                text(
                    "INSERT INTO migration_conflict_marker (conflict_marker) "
                    "VALUES ('expected-conflict-marker')"
                )
            )
            await connection.execute(
                text(
                    "CREATE INDEX ix_agent_invocation_status "
                    "ON migration_conflict_marker (conflict_marker)"
                )
            )

        failure: Exception | None = None
        try:
            await _alembic(failed_engine, "upgrade", "head")
        except Exception as exc:
            failure = exc

        assert failure is not None, "conflicting index did not fail the upgrade"
        diagnostic = str(getattr(failure, "orig", failure)).lower()
        assert "ix_agent_invocation_status" in diagnostic
        assert "already exists" in diagnostic
        assert await _revision(failed_engine) == TRACE_REVISION
        failed_tables = await _table_names(failed_engine)
        assert "migration_conflict_marker" in failed_tables
        assert not {"agent_run", "agent_invocation", "agent_run_event"}.intersection(
            failed_tables
        )
        async with failed_engine.connect() as connection:
            marker = await connection.scalar(
                text("SELECT conflict_marker FROM migration_conflict_marker")
            )
            index_names = await connection.run_sync(
                lambda sync_connection: {
                    index["name"]
                    for index in inspect(sync_connection).get_indexes(
                        "migration_conflict_marker"
                    )
                }
            )
        assert marker == "expected-conflict-marker"
        assert "ix_agent_invocation_status" in index_names
        record_property("migration_failure_category", "index_conflict")
        record_property("migration_failure_exception_type", type(failure).__name__)
        record_property("migration_failure_transaction_rolled_back", "true")
        record_property("migration_failure_revision", TRACE_REVISION)

        async with _isolated_postgres_schema() as clean_engine:
            await _alembic(clean_engine, "upgrade", "head")
            assert await _revision(clean_engine) == HEAD_REVISION
            clean_tables = await _table_names(clean_engine)
            assert clean_tables == set(SQLModel.metadata.tables) | {"alembic_version"}
            assert "migration_conflict_marker" not in clean_tables
            async with clean_engine.connect() as connection:
                clean_indexes = await connection.run_sync(
                    lambda sync_connection: {
                        table_name: {
                            (
                                index["name"],
                                tuple(index["column_names"]),
                            )
                            for index in inspect(sync_connection).get_indexes(
                                table_name
                            )
                        }
                        for table_name in clean_tables
                    }
                )
            assert (
                "ix_agent_invocation_status",
                ("status",),
            ) in clean_indexes["agent_invocation"]
            record_property("clean_schema_upgrade_revision", HEAD_REVISION)
            record_property("failed_schema_has_no_target_tables", "true")

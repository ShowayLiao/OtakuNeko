"""Verify PostgreSQL reflection of current business schema before adoption."""

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Collection, CollectionStatus, Subject, SubjectType, User

from app.db.migration_compatibility import validate_table
from app.db.migration_snapshot import BUSINESS_TABLES


@pytest.mark.postgres
@pytest.mark.integration
@pytest.mark.db
async def test_postgres_current_business_schema_passes_adoption_checks(postgres_engine):
    def validate(connection):
        for name in BUSINESS_TABLES:
            validate_table(connection, name)

    async with postgres_engine.connect() as connection:
        await connection.run_sync(validate)


@pytest.mark.postgres
@pytest.mark.integration
@pytest.mark.db
async def test_postgres_missing_unique_constraint_is_rejected(postgres_engine):
    async with postgres_engine.begin() as connection:
        await connection.execute(
            text("ALTER TABLE subject DROP CONSTRAINT uq_source_source_id")
        )
        with pytest.raises(RuntimeError, match="unsupported_business_schema"):
            await connection.run_sync(lambda conn: validate_table(conn, "subject"))


@pytest.mark.postgres
@pytest.mark.integration
@pytest.mark.db
async def test_postgres_changed_enum_labels_are_rejected(postgres_engine):
    async with postgres_engine.begin() as connection:
        await connection.execute(
            text("ALTER TYPE subjecttype RENAME VALUE 'ANIME' TO 'INCOMPATIBLE_ANIME'")
        )
        with pytest.raises(RuntimeError, match="unsupported_business_schema"):
            await connection.run_sync(lambda conn: validate_table(conn, "subject"))


@pytest.mark.postgres
@pytest.mark.integration
@pytest.mark.db
async def test_postgres_foreign_schema_ownership_reference_is_rejected(postgres_engine):
    other_schema = "test_" + uuid4().hex
    try:
        async with postgres_engine.begin() as connection:
            await connection.execute(text(f'CREATE SCHEMA "{other_schema}"'))
            await connection.execute(
                text(f'CREATE TABLE "{other_schema}".users (id INTEGER PRIMARY KEY)')
            )
            await connection.execute(
                text("ALTER TABLE collection DROP CONSTRAINT collection_user_id_fkey")
            )
            await connection.execute(
                text(
                    f'ALTER TABLE collection ADD CONSTRAINT collection_user_id_fkey FOREIGN KEY (user_id) REFERENCES "{other_schema}".users(id)'
                )
            )
            with pytest.raises(RuntimeError, match="unsupported_business_schema"):
                await connection.run_sync(
                    lambda conn: validate_table(conn, "collection")
                )
    finally:
        async with postgres_engine.begin() as connection:
            await connection.execute(
                text(f'DROP SCHEMA IF EXISTS "{other_schema}" CASCADE')
            )


@pytest.mark.postgres
@pytest.mark.integration
@pytest.mark.db
async def test_postgres_existing_naive_timestamp_columns_bind_aware_values_in_utc(
    postgres_engine,
):
    value = datetime(2026, 10, 15, 9, 30, tzinfo=timezone(timedelta(hours=9)))
    subject = Subject(
        id=101,
        source_id="pg-offset-time",
        type=SubjectType.ANIME,
        name="offset fixture",
        last_sync=value,
    )
    collection = Collection(
        id=102,
        user_id=17,
        source_id="pg-offset-time",
        type=CollectionStatus.DO,
        updated_at=value,
    )
    async with AsyncSession(postgres_engine) as session:
        session.add(User(id=17, username="pg-offset-fixture"))
        await session.flush()
        session.add_all([subject, collection])
        await session.flush()
        assert subject.last_sync == value
        assert collection.updated_at == value
        await session.commit()
    expected = datetime(2026, 10, 15, 0, 30)
    async with AsyncSession(postgres_engine) as session:
        restored_subject = await session.get(Subject, 101)
        restored_collection = await session.get(Collection, 102)
        assert restored_subject is not None and restored_collection is not None
        assert restored_subject.last_sync == expected
        assert restored_subject.last_sync.tzinfo is None
        assert restored_collection.updated_at == expected
        assert restored_collection.updated_at.tzinfo is None


@pytest.mark.postgres
@pytest.mark.integration
@pytest.mark.db
async def test_postgres_changed_check_expression_is_rejected(postgres_engine):
    async with postgres_engine.begin() as connection:
        await connection.execute(
            text("ALTER TABLE agent_memory DROP CONSTRAINT ck_agent_memory_importance")
        )
        await connection.execute(
            text(
                "ALTER TABLE agent_memory ADD CONSTRAINT ck_agent_memory_importance CHECK (importance >= 0 AND importance <= 2)"
            )
        )
        with pytest.raises(RuntimeError, match="unsupported_business_schema"):
            await connection.run_sync(lambda conn: validate_table(conn, "agent_memory"))


@pytest.mark.postgres
@pytest.mark.integration
@pytest.mark.db
async def test_postgres_lower_precision_real_column_is_rejected(postgres_engine):
    async with postgres_engine.begin() as connection:
        await connection.execute(
            text("ALTER TABLE agent_memory ALTER COLUMN importance TYPE REAL")
        )
        with pytest.raises(RuntimeError, match="unsupported_business_schema"):
            await connection.run_sync(lambda conn: validate_table(conn, "agent_memory"))

"""Reject semantically incompatible PostgreSQL adoption candidates."""

import pytest
from sqlalchemy import text

from app.db.migration_compatibility import validate_table

pytestmark = [pytest.mark.postgres, pytest.mark.integration, pytest.mark.db]


async def test_postgres_partial_unique_username_index_is_rejected(postgres_engine):
    async with postgres_engine.begin() as connection:
        await connection.execute(text("DROP INDEX ix_users_username"))
        await connection.execute(
            text(
                "CREATE UNIQUE INDEX ix_users_username ON users(username) WHERE username <> 'excluded-fixture'"
            )
        )
        with pytest.raises(RuntimeError, match="unsupported_business_schema"):
            await connection.run_sync(lambda conn: validate_table(conn, "users"))


@pytest.mark.parametrize("first_kind", ["EPISODIC", "epi sodic"])
async def test_postgres_changed_check_literal_is_rejected(postgres_engine, first_kind):
    async with postgres_engine.begin() as connection:
        await connection.execute(
            text("ALTER TABLE agent_memory DROP CONSTRAINT ck_agent_memory_kind")
        )
        # Parameter values are a fixed test-only allowlist above; no user input.
        await connection.execute(
            text(
                "ALTER TABLE agent_memory ADD CONSTRAINT ck_agent_memory_kind CHECK (kind IN ('"
                + first_kind
                + "', 'semantic', 'profile'))"
            )
        )
        with pytest.raises(RuntimeError, match="unsupported_business_schema"):
            await connection.run_sync(lambda conn: validate_table(conn, "agent_memory"))


async def test_postgres_integer_primary_key_without_generation_is_rejected(
    postgres_engine,
):
    async with postgres_engine.begin() as connection:
        await connection.execute(text("ALTER TABLE users ALTER COLUMN id DROP DEFAULT"))
        with pytest.raises(RuntimeError, match="unsupported_business_schema"):
            await connection.run_sync(lambda conn: validate_table(conn, "users"))


async def test_postgres_generated_username_is_rejected(postgres_engine):
    async with postgres_engine.begin() as connection:
        await connection.execute(text("DROP INDEX ix_users_username"))
        await connection.execute(text("ALTER TABLE users DROP COLUMN username"))
        await connection.execute(
            text(
                "ALTER TABLE users ADD COLUMN username VARCHAR "
                "GENERATED ALWAYS AS (upper(bangumi_name)) STORED NOT NULL"
            )
        )
        await connection.execute(
            text("CREATE UNIQUE INDEX ix_users_username ON users(username)")
        )
        with pytest.raises(RuntimeError, match="unsupported_business_schema"):
            await connection.run_sync(lambda conn: validate_table(conn, "users"))

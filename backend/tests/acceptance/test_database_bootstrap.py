from __future__ import annotations

import asyncio
import os
import sqlite3
import subprocess
import sys
from contextlib import closing
from datetime import datetime, time, timezone
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest
from sqlalchemy import UniqueConstraint, create_engine, inspect, select
from sqlalchemy.engine import URL
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlmodel import SQLModel, col

import app.models  # noqa: F401
from app.models import (
    Collection,
    CollectionStatus,
    Schedule,
    Subject,
    SubjectType,
    User,
)
from app.models.enums import WatchType


BACKEND_ROOT = Path(__file__).resolve().parents[2]
HEAD_REVISION = "c7d1e4f8a2b6"
BOOTSTRAP_REVISION = "a10300000001"
BUSINESS_TABLES = {
    "users",
    "subject",
    "collection",
    "schedules",
    "anime_broadcast_metadata",
}


def _run_alembic(
    database_path: Path, *arguments: str
) -> subprocess.CompletedProcess[str]:
    child_env = os.environ.copy()
    child_env.update(
        {
            "DEBUG": "false",
            "DEPLOY_MODE": "local",
            "SQLITE_FILE": str(database_path.resolve()),
        }
    )
    return subprocess.run(
        [sys.executable, "-m", "alembic", "-c", "alembic.ini", *arguments],
        cwd=BACKEND_ROOT,
        env=child_env,
        check=False,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        text=True,
        timeout=30,
    )


def _assert_alembic_succeeded(
    result: subprocess.CompletedProcess[str], command: str
) -> None:
    assert result.returncode == 0, (
        f"Alembic {command} returned {result.returncode}:\n"
        f"{result.stdout}\n{result.stderr}"
    )


def _current_revision(database_path: Path) -> str | None:
    with closing(sqlite3.connect(database_path)) as connection:
        exists = connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' "
            "AND name = 'alembic_version'"
        ).fetchone()
        if exists is None:
            return None
        row = connection.execute("SELECT version_num FROM alembic_version").fetchone()
    return None if row is None else str(row[0])


def _table_names(database_path: Path) -> set[str]:
    with closing(sqlite3.connect(database_path)) as connection:
        rows = connection.execute(
            "SELECT name FROM sqlite_master "
            "WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
        ).fetchall()
    return {str(row[0]) for row in rows}


def _assert_business_metadata(database_path: Path) -> None:
    engine = create_engine(URL.create("sqlite", database=str(database_path.resolve())))
    try:
        with engine.connect() as connection:
            inspector = inspect(connection)
            live_tables = set(inspector.get_table_names())
            assert BUSINESS_TABLES <= live_tables

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
                    (constraint.get("name"), tuple(constraint["column_names"]))
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
    finally:
        engine.dispose()


async def _insert_business_rows(
    database_path: Path, *, username: str, source_id: str
) -> None:
    engine = create_async_engine(
        URL.create("sqlite+aiosqlite", database=str(database_path.resolve()))
    )
    try:
        async with AsyncSession(engine, expire_on_commit=False) as session:
            user = User(username=username, bangumi_id=4200, sign="bootstrap-test")
            session.add(user)
            await session.flush()

            subject = Subject(
                source="bangumi",
                source_id=source_id,
                type=SubjectType.ANIME,
                name="Bootstrap Fixture",
                name_cn="启动迁移样本",
                summary="preserved across migration operations",
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
    finally:
        await engine.dispose()


async def _business_snapshot(
    database_path: Path, *, username: str, source_id: str
) -> dict[str, tuple[object, ...]]:
    engine = create_async_engine(
        URL.create("sqlite+aiosqlite", database=str(database_path.resolve()))
    )
    try:
        async with AsyncSession(engine) as session:
            user = (
                (
                    await session.execute(
                        select(User).where(col(User.username) == username)
                    )
                )
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
            assert user.sign == "bootstrap-test"
            assert subject.name == "Bootstrap Fixture"
            assert subject.name_cn == "启动迁移样本"
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
    finally:
        await engine.dispose()


def _create_current_unversioned_database(database_path: Path) -> None:
    engine = create_engine(URL.create("sqlite", database=str(database_path.resolve())))
    try:
        SQLModel.metadata.create_all(engine)
    finally:
        engine.dispose()


def _unsupported_database_snapshot(
    database_path: Path,
) -> tuple[
    tuple[tuple[str, str, str | None], ...],
    dict[str, tuple[tuple[object, ...], ...]],
]:
    with closing(sqlite3.connect(database_path)) as connection:
        schema_rows = connection.execute(
            "SELECT type, name, sql FROM sqlite_master "
            "WHERE type IN ('table', 'index') AND name NOT LIKE 'sqlite_%' "
            "AND name != 'alembic_version' AND tbl_name != 'alembic_version' "
            "ORDER BY type, name"
        ).fetchall()
        schema = tuple(
            (str(object_type), str(name), sql) for object_type, name, sql in schema_rows
        )
        table_names = [
            str(name)
            for object_type, name, _sql in schema_rows
            if object_type == "table"
        ]
        rows = {
            name: tuple(
                tuple(row)
                for row in connection.execute(f'SELECT * FROM "{name}" ORDER BY rowid')
            )
            for name in table_names
        }
    return schema, rows


def _create_unsupported_legacy_database(database_path: Path) -> None:
    with closing(sqlite3.connect(database_path)) as connection, connection:
        connection.execute(
            "CREATE TABLE subject ("
            "id INTEGER PRIMARY KEY, type INTEGER NOT NULL, name TEXT NOT NULL)"
        )
        connection.execute(
            "CREATE TABLE collection ("
            "user_id INTEGER NOT NULL, subject_id INTEGER NOT NULL, "
            "type INTEGER NOT NULL)"
        )
        connection.execute(
            "INSERT INTO subject (id, type, name) VALUES (?, ?, ?)",
            (91, 2, "unsupported legacy subject"),
        )
        connection.execute(
            "INSERT INTO collection (user_id, subject_id, type) VALUES (?, ?, ?)",
            (17, 91, 3),
        )


def _create_partial_agent_database(database_path: Path) -> None:
    engine = create_engine(URL.create("sqlite", database=str(database_path.resolve())))
    try:
        trace_table = SQLModel.metadata.tables["agent_trace"]
        trace_table.create(engine)
        timestamp = datetime(2026, 10, 15, 8, 30, tzinfo=timezone.utc)
        with engine.begin() as connection:
            connection.execute(
                trace_table.insert().values(
                    trace_id="partial-agent-group-trace",
                    user_id=None,
                    task_id=None,
                    agent_name="migration-test-agent",
                    goal="safe migration fixture",
                    status="completed",
                    headers_json=None,
                    started_at=timestamp,
                    created_at=timestamp,
                )
            )
    finally:
        engine.dispose()


@pytest.mark.db
def test_fresh_upgrade_creates_business_schema_and_downgrade_preserves_rows() -> None:
    with TemporaryDirectory(prefix="otakuneko-fresh-bootstrap-") as directory:
        database_path = Path(directory) / "fresh.sqlite3"

        upgrade = _run_alembic(database_path, "upgrade", "head")
        _assert_alembic_succeeded(upgrade, "fresh upgrade head")
        assert _current_revision(database_path) == HEAD_REVISION
        _assert_business_metadata(database_path)

        asyncio.run(
            _insert_business_rows(
                database_path,
                username="fresh-bootstrap-user",
                source_id="fresh-bootstrap-subject",
            )
        )
        original_rows = asyncio.run(
            _business_snapshot(
                database_path,
                username="fresh-bootstrap-user",
                source_id="fresh-bootstrap-subject",
            )
        )

        downgrade = _run_alembic(database_path, "downgrade", BOOTSTRAP_REVISION)
        _assert_alembic_succeeded(downgrade, f"downgrade {BOOTSTRAP_REVISION}")
        assert _current_revision(database_path) == BOOTSTRAP_REVISION
        _assert_business_metadata(database_path)
        assert (
            asyncio.run(
                _business_snapshot(
                    database_path,
                    username="fresh-bootstrap-user",
                    source_id="fresh-bootstrap-subject",
                )
            )
            == original_rows
        )

        reupgrade = _run_alembic(database_path, "upgrade", "head")
        _assert_alembic_succeeded(reupgrade, "re-upgrade head")
        assert _current_revision(database_path) == HEAD_REVISION
        _assert_business_metadata(database_path)
        assert (
            asyncio.run(
                _business_snapshot(
                    database_path,
                    username="fresh-bootstrap-user",
                    source_id="fresh-bootstrap-subject",
                )
            )
            == original_rows
        )


@pytest.mark.db
def test_unversioned_current_local_database_is_adopted_and_upgrade_is_idempotent() -> (
    None
):
    with TemporaryDirectory(prefix="otakuneko-local-adoption-") as directory:
        database_path = Path(directory) / "unversioned.sqlite3"
        _create_current_unversioned_database(database_path)
        assert _current_revision(database_path) is None

        asyncio.run(
            _insert_business_rows(
                database_path,
                username="adopted-local-user",
                source_id="adopted-local-subject",
            )
        )
        original_rows = asyncio.run(
            _business_snapshot(
                database_path,
                username="adopted-local-user",
                source_id="adopted-local-subject",
            )
        )

        upgrade = _run_alembic(database_path, "upgrade", "head")
        _assert_alembic_succeeded(upgrade, "adopt unversioned local schema")
        assert _current_revision(database_path) == HEAD_REVISION
        _assert_business_metadata(database_path)
        assert (
            asyncio.run(
                _business_snapshot(
                    database_path,
                    username="adopted-local-user",
                    source_id="adopted-local-subject",
                )
            )
            == original_rows
        )

        downgrade = _run_alembic(database_path, "downgrade", BOOTSTRAP_REVISION)
        _assert_alembic_succeeded(downgrade, f"downgrade {BOOTSTRAP_REVISION}")
        assert _current_revision(database_path) == BOOTSTRAP_REVISION
        _assert_business_metadata(database_path)
        assert (
            asyncio.run(
                _business_snapshot(
                    database_path,
                    username="adopted-local-user",
                    source_id="adopted-local-subject",
                )
            )
            == original_rows
        )
        agent_tables = {
            "agent_memory",
            "agent_task_def",
            "agent_task_run",
            "agent_trace",
            "trace_event",
            "agent_run",
            "agent_invocation",
            "agent_run_event",
        }
        assert not agent_tables.intersection(_table_names(database_path))

        reupgrade = _run_alembic(database_path, "upgrade", "head")
        _assert_alembic_succeeded(reupgrade, "re-upgrade adopted local schema")
        assert _current_revision(database_path) == HEAD_REVISION
        _assert_business_metadata(database_path)
        assert (
            asyncio.run(
                _business_snapshot(
                    database_path,
                    username="adopted-local-user",
                    source_id="adopted-local-subject",
                )
            )
            == original_rows
        )

        second_upgrade = _run_alembic(database_path, "upgrade", "head")
        _assert_alembic_succeeded(second_upgrade, "idempotent upgrade head")
        assert _current_revision(database_path) == HEAD_REVISION
        _assert_business_metadata(database_path)
        assert (
            asyncio.run(
                _business_snapshot(
                    database_path,
                    username="adopted-local-user",
                    source_id="adopted-local-subject",
                )
            )
            == original_rows
        )


@pytest.mark.db
def test_unsupported_legacy_business_schema_is_rejected_before_schema_changes() -> None:
    with TemporaryDirectory(prefix="otakuneko-unsupported-bootstrap-") as directory:
        database_path = Path(directory) / "unsupported.sqlite3"
        _create_unsupported_legacy_database(database_path)
        schema_before, rows_before = _unsupported_database_snapshot(database_path)

        result = _run_alembic(database_path, "upgrade", "head")
        diagnostic = (result.stdout + "\n" + result.stderr).lower()

        assert result.returncode != 0
        assert "unsupported_business_schema" in diagnostic
        schema_after, rows_after = _unsupported_database_snapshot(database_path)
        assert schema_after == schema_before
        assert rows_after == rows_before
        assert "alembic_version" in _table_names(database_path)
        assert _current_revision(database_path) is None


@pytest.mark.db
def test_partial_current_agent_group_is_rejected_before_business_ddl() -> None:
    with TemporaryDirectory(prefix="otakuneko-partial-agent-bootstrap-") as directory:
        database_path = Path(directory) / "partial-agent.sqlite3"
        _create_partial_agent_database(database_path)
        schema_before, rows_before = _unsupported_database_snapshot(database_path)

        result = _run_alembic(database_path, "upgrade", "head")
        diagnostic = (result.stdout + "\n" + result.stderr).lower()

        assert result.returncode != 0
        assert "unsupported_business_schema" in diagnostic
        schema_after, rows_after = _unsupported_database_snapshot(database_path)
        assert schema_after == schema_before
        assert rows_after == rows_before
        assert _table_names(database_path) == {"agent_trace", "alembic_version"}
        assert _current_revision(database_path) is None

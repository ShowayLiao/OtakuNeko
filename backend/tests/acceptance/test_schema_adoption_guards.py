"""SQLite CLI regressions for strict adoption of unversioned schemas."""

from __future__ import annotations

import os
import sqlite3
import subprocess
import sys
from contextlib import closing
from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest
from sqlalchemy import (
    CheckConstraint,
    Column,
    Computed,
    Index,
    MetaData,
    String,
    UniqueConstraint,
    create_engine,
    text,
)
from sqlalchemy.schema import CreateTable
from sqlmodel import Session, SQLModel

import app.models  # noqa: F401
from app.models import User


BACKEND_ROOT = Path(__file__).resolve().parents[2]
HEAD_REVISION = "c7d1e4f8a2b6"
FIXTURE_USER_ID = 41
FIXTURE_COLLECTION_ID = 7
FIXTURE_USERNAME = "adoption-guard-fixture"
_UNIQUE_CONFLICT_ACTIONS = {
    "unique_on_conflict_abort": "ABORT",
    "unique_on_conflict_replace": "REPLACE",
    "unique_on_conflict_ignore": "IGNORE",
    "unique_on_conflict_fail": "FAIL",
    "unique_on_conflict_rollback": "ROLLBACK",
    "unique_on_conflict_replace_comments": "REPLACE",
    "unique_on_conflict_abort_quoted": "ABORT",
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


def _clone_current_metadata() -> MetaData:
    metadata = MetaData()
    for table in SQLModel.metadata.tables.values():
        table.to_metadata(metadata)
    return metadata


def _mutate_metadata(metadata: MetaData, mutation: str) -> None:
    if mutation == "partial_username_index":
        users = metadata.tables["users"]
        current_index = next(
            index for index in users.indexes if index.name == "ix_users_username"
        )
        users.indexes.remove(current_index)
        Index(
            "ix_users_username",
            users.c.username,
            unique=True,
            sqlite_where=text("username != 'duplicate-fixture'"),
        )
        return

    if mutation in {
        "uppercase_check_literal",
        "whitespace_check_literal",
        "format_check",
    }:
        constraint = next(
            constraint
            for constraint in metadata.tables["agent_memory"].constraints
            if isinstance(constraint, CheckConstraint)
            and constraint.name == "ck_agent_memory_kind"
        )
        expressions = {
            "uppercase_check_literal": "kind IN ('EPISODIC', 'semantic', 'profile')",
            "whitespace_check_literal": "kind IN ('epi sodic', 'semantic', 'profile')",
            "format_check": "KIND   in ( 'episodic' , 'semantic' , 'profile' )",
        }
        constraint.sqltext = text(expressions[mutation])
        return

    if mutation == "users_without_rowid":
        metadata.tables["users"].dialect_options["sqlite"]["with_rowid"] = False
        return

    if mutation in _UNIQUE_CONFLICT_ACTIONS:
        collection = metadata.tables["collection"]
        for unique_constraint in list(collection.constraints):
            if isinstance(unique_constraint, UniqueConstraint):
                collection.constraints.discard(unique_constraint)
        collection.append_constraint(
            UniqueConstraint(
                "user_id",
                "source",
                "source_id",
                name=(
                    "UNIQUE ON CONFLICT REPLACE ) label"
                    if mutation == "unique_on_conflict_abort_quoted"
                    else "uq_user_collection"
                ),
                sqlite_on_conflict=_UNIQUE_CONFLICT_ACTIONS[mutation],
            )
        )
        return

    if mutation == "computed_username":
        metadata.tables["users"].append_column(
            Column(
                "username",
                String(),
                Computed("upper(bangumi_name)"),
                nullable=False,
            ),
            replace_existing=True,
        )
        return

    raise AssertionError(f"unknown test mutation: {mutation}")


def _create_unversioned_database(database_path: Path, mutation: str | None) -> None:
    metadata = _clone_current_metadata()
    if mutation is not None:
        _mutate_metadata(metadata, mutation)

    engine = create_engine(f"sqlite:///{database_path.resolve()}")
    try:
        if mutation in {
            "unique_on_conflict_replace_comments",
            "unique_on_conflict_abort_quoted",
        }:
            with engine.begin() as connection:
                for table in metadata.sorted_tables:
                    if table.name != "collection":
                        table.create(connection)
                        continue
                    ddl = str(CreateTable(table).compile(dialect=engine.dialect))
                    ddl = ddl.replace(
                        "ON CONFLICT ABORT", "ON /* strategy fixture */ CONFLICT ABORT"
                    )
                    ddl = ddl.replace(
                        "ON CONFLICT REPLACE\n",
                        "ON /* strategy fixture */ CONFLICT REPLACE\n",
                    )
                    connection.exec_driver_sql(ddl)
                    for index in table.indexes:
                        index.create(connection)
        else:
            metadata.create_all(engine)
        with engine.begin() as connection:
            user_values: dict[str, object] = {
                "id": FIXTURE_USER_ID,
                "created_at": datetime(2026, 10, 15),
            }
            if mutation == "computed_username":
                user_values["bangumi_name"] = FIXTURE_USERNAME
            else:
                user_values["username"] = FIXTURE_USERNAME
            connection.execute(metadata.tables["users"].insert().values(**user_values))
            connection.execute(
                metadata.tables["collection"]
                .insert()
                .values(
                    id=FIXTURE_COLLECTION_ID,
                    user_id=FIXTURE_USER_ID,
                    source="bangumi",
                    source_id=FIXTURE_USERNAME,
                    type="DO",
                    updated_at=datetime(2026, 10, 15),
                    private=False,
                    vol_status=0,
                    ep_status=0,
                    subject_type=2,
                )
            )
    finally:
        engine.dispose()


def _database_snapshot(
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
        rows: dict[str, tuple[tuple[object, ...], ...]] = {}
        for name in table_names:
            escaped_name = name.replace('"', '""')
            primary_key = [
                str(column_name)
                for _cid, column_name, _type, _notnull, _default, pk_order in sorted(
                    connection.execute(f'PRAGMA table_info("{escaped_name}")'),
                    key=lambda column: int(column[5]),
                )
                if pk_order
            ]
            order_by = ""
            if primary_key:
                order_by = " ORDER BY " + ", ".join(
                    f'"{column.replace(chr(34), chr(34) * 2)}"'
                    for column in primary_key
                )
            elif not any(
                str(row[1]) == "rowid"
                for row in connection.execute(f'PRAGMA table_info("{escaped_name}")')
            ):
                order_by = " ORDER BY rowid"
            rows[name] = tuple(
                tuple(row)
                for row in connection.execute(
                    f'SELECT * FROM "{escaped_name}"{order_by}'
                )
            )
    return schema, rows


@pytest.mark.db
@pytest.mark.parametrize(
    "mutation",
    [
        "partial_username_index",
        "uppercase_check_literal",
        "whitespace_check_literal",
        "users_without_rowid",
        "unique_on_conflict_replace",
        "unique_on_conflict_ignore",
        "unique_on_conflict_fail",
        "unique_on_conflict_rollback",
        "unique_on_conflict_replace_comments",
        "computed_username",
    ],
    ids=[
        "partial-unique-index",
        "uppercase-check-value",
        "check-inner-whitespace",
        "without-rowid",
        "unique-on-conflict-replace",
        "unique-on-conflict-ignore",
        "unique-on-conflict-fail",
        "unique-on-conflict-rollback",
        "unique-on-conflict-replace-comments",
        "computed-username",
    ],
)
def test_incompatible_unversioned_schema_is_rejected_before_business_ddl(
    mutation: str,
) -> None:
    with TemporaryDirectory(prefix="otakuneko-sqlite-adoption-guard-") as directory:
        database_path = Path(directory) / "unversioned.sqlite3"
        _create_unversioned_database(database_path, mutation)
        schema_before, rows_before = _database_snapshot(database_path)

        result = _run_alembic(database_path, "upgrade", "head")
        diagnostic = (result.stdout + "\n" + result.stderr).lower()

        assert result.returncode != 0
        assert "unsupported_business_schema" in diagnostic
        schema_after, rows_after = _database_snapshot(database_path)
        assert schema_after == schema_before
        assert rows_after == rows_before
        with closing(sqlite3.connect(database_path)) as connection:
            version_rows = connection.execute(
                "SELECT * FROM alembic_version"
            ).fetchall()
        assert version_rows == []
        assert _current_revision(database_path) is None


@pytest.mark.db
def test_check_formatting_outside_literals_is_accepted_and_orm_ids_are_generated() -> (
    None
):
    with TemporaryDirectory(prefix="otakuneko-sqlite-adoption-format-") as directory:
        database_path = Path(directory) / "unversioned.sqlite3"
        _create_unversioned_database(database_path, "format_check")

        result = _run_alembic(database_path, "upgrade", "head")
        assert result.returncode == 0, f"{result.stdout}\n{result.stderr}"
        assert _current_revision(database_path) == HEAD_REVISION

        engine = create_engine(f"sqlite:///{database_path.resolve()}")
        try:
            with Session(engine) as session:
                user = User(username="orm-generated-id-fixture")
                session.add(user)
                session.flush()
                assert user.id is not None
                assert user.id > 0
        finally:
            engine.dispose()


@pytest.mark.db
@pytest.mark.parametrize(
    "mutation", ["unique_on_conflict_abort", "unique_on_conflict_abort_quoted"]
)
def test_explicit_abort_conflict_clause_is_adopted_and_conflicting_write_keeps_row(
    mutation: str,
) -> None:
    with TemporaryDirectory(prefix="otakuneko-sqlite-adoption-conflict-") as directory:
        database_path = Path(directory) / "unversioned.sqlite3"
        _create_unversioned_database(database_path, mutation)

        result = _run_alembic(database_path, "upgrade", "head")
        assert result.returncode == 0, f"{result.stdout}\n{result.stderr}"
        assert _current_revision(database_path) == HEAD_REVISION

        with closing(sqlite3.connect(database_path)) as connection:
            original = connection.execute("SELECT * FROM collection").fetchone()
            assert original is not None
            # ABORT is SQLite's implicit default, so the conflict clause is
            # semantically identical to the snapshot. A duplicate write must
            # fail rather than silently replace the stored collection row.
            duplicate = (FIXTURE_COLLECTION_ID + 1,) + tuple(original[1:])
            placeholders = ", ".join(["?"] * len(duplicate))
            with pytest.raises(sqlite3.IntegrityError):
                connection.execute(
                    f"INSERT INTO collection VALUES ({placeholders})", duplicate
                )
            connection.rollback()
            surviving_rows = connection.execute("SELECT * FROM collection").fetchall()
        assert surviving_rows == [original]

from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import sys
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest
from sqlalchemy.engine import URL
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.core.config import settings
from app.harness.contracts import ErrorCode
from app.harness.decision_parser import DecisionParseError, DecisionParser
from app.harness.model_types import ModelCallResult
from app.trace import TRACE_LEGACY_SCHEMA_VERSION
from app.trace.sql_store import SqlTraceStore


BACKEND_ROOT = Path(__file__).resolve().parents[2]
BASELINE_REVISION = "bbd93366421b"
TRACE_REVISION = "5ae716ad749d"
HEAD_REVISION = "c7d1e4f8a2b6"
LEGACY_TRACE_ID = "migration-legacy-trace"
LEGACY_USER_ID = 314
LEGACY_STARTED_AT = datetime(2026, 10, 14, 1, 2, 3, tzinfo=timezone.utc)

_PARENT_ENV_KEYS = ("DEBUG", "DEPLOY_MODE", "SQLITE_FILE")


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


def _alembic_revision(database_path: Path) -> str:
    with closing(sqlite3.connect(database_path)) as connection:
        row = connection.execute("SELECT version_num FROM alembic_version").fetchone()
    assert row is not None
    return str(row[0])


def _table_names(database_path: Path) -> set[str]:
    with closing(sqlite3.connect(database_path)) as connection:
        rows = connection.execute(
            "SELECT name FROM sqlite_master "
            "WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
        ).fetchall()
    return {str(row[0]) for row in rows}


def _table_columns(database_path: Path, table_name: str) -> set[str]:
    with closing(sqlite3.connect(database_path)) as connection:
        rows = connection.execute(f'PRAGMA table_info("{table_name}")').fetchall()
    return {str(row[1]) for row in rows}


def _seed_legacy_trace(database_path: Path) -> None:
    started_at = LEGACY_STARTED_AT.isoformat(sep=" ")
    headers = {
        "trace_id": LEGACY_TRACE_ID,
        "user_id": LEGACY_USER_ID,
        "task_id": 27,
        "agent_name": "legacy-agent",
        "goal": "historical trace",
        "started_at": LEGACY_STARTED_AT.isoformat(),
        "status": "completed",
    }
    step = {
        "step_index": 0,
        "step_label": "legacy-step",
        "agent_name": "legacy-agent",
        "started_at": LEGACY_STARTED_AT.isoformat(),
        "completed_at": LEGACY_STARTED_AT.isoformat(),
        "status": "completed",
        "events": [
            {
                "event_id": "legacy-event-1",
                "event_type": "node_end",
                "timestamp": LEGACY_STARTED_AT.isoformat(),
                "status": "completed",
                "data": {"phase": "done"},
            }
        ],
    }
    with closing(sqlite3.connect(database_path)) as connection, connection:
        connection.execute(
            "INSERT INTO agent_trace "
            "(trace_id, user_id, task_id, agent_name, goal, status, "
            "headers_json, started_at, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                LEGACY_TRACE_ID,
                LEGACY_USER_ID,
                27,
                "legacy-agent",
                "historical trace",
                "completed",
                json.dumps(headers),
                started_at,
                started_at,
            ),
        )
        connection.execute(
            "INSERT INTO trace_event "
            "(trace_id, step_index, step_label, agent_name, status, "
            "step_json, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                LEGACY_TRACE_ID,
                0,
                "legacy-step",
                "legacy-agent",
                "completed",
                json.dumps(step),
                started_at,
            ),
        )


def _assert_legacy_trace_storage(database_path: Path) -> None:
    with closing(sqlite3.connect(database_path)) as connection:
        row = connection.execute(
            "SELECT headers_json FROM agent_trace WHERE trace_id = ?",
            (LEGACY_TRACE_ID,),
        ).fetchone()
        event_row = connection.execute(
            "SELECT step_json FROM trace_event WHERE trace_id = ?",
            (LEGACY_TRACE_ID,),
        ).fetchone()
    assert row is not None and event_row is not None
    assert "schema_version" not in json.loads(row[0])
    stored_events = json.loads(event_row[0])["events"]
    assert all("schema_version" not in event for event in stored_events)


async def _query_trace(database_path: Path, *, user_id: int | None):
    engine = create_async_engine(
        URL.create("sqlite+aiosqlite", database=str(database_path.resolve()))
    )
    try:
        async with AsyncSession(engine) as session:
            return await SqlTraceStore(session).query(
                LEGACY_TRACE_ID,
                user_id=user_id,
            )
    finally:
        await engine.dispose()


async def _assert_legacy_trace_is_readable(database_path: Path) -> None:
    trace = await _query_trace(database_path, user_id=LEGACY_USER_ID)
    assert trace is not None
    assert trace.schema_version == TRACE_LEGACY_SCHEMA_VERSION == 1
    assert trace.user_id == LEGACY_USER_ID
    assert len(trace.steps) == 1
    assert len(trace.steps[0].events) == 1
    assert trace.steps[0].events[0].schema_version == 1
    assert await _query_trace(database_path, user_id=LEGACY_USER_ID + 1) is None
    assert await _query_trace(database_path, user_id=None) is None


def _parent_configuration_snapshot() -> tuple[object, ...]:
    return (
        tuple((key, os.environ.get(key)) for key in _PARENT_ENV_KEYS),
        settings.DEBUG,
        settings.DEPLOY_MODE,
        settings.SQLITE_FILE,
        settings.DATABASE_URL,
    )


@pytest.mark.db
@pytest.mark.asyncio
async def test_legacy_trace_survives_incremental_upgrade_downgrade_and_reupgrade(
    record_property,
) -> None:
    parent_configuration = _parent_configuration_snapshot()
    try:
        with TemporaryDirectory(prefix="otakuneko-trace-migration-") as directory:
            database_path = Path(directory) / "trace.sqlite3"

            _assert_alembic_succeeded(
                _run_alembic(database_path, "stamp", BASELINE_REVISION),
                f"stamp {BASELINE_REVISION}",
            )
            assert _alembic_revision(database_path) == BASELINE_REVISION

            _assert_alembic_succeeded(
                _run_alembic(database_path, "upgrade", TRACE_REVISION),
                f"upgrade {TRACE_REVISION}",
            )
            assert _alembic_revision(database_path) == TRACE_REVISION
            _seed_legacy_trace(database_path)
            _assert_legacy_trace_storage(database_path)

            _assert_alembic_succeeded(
                _run_alembic(database_path, "upgrade", "head"), "upgrade head"
            )
            assert _alembic_revision(database_path) == HEAD_REVISION
            await _assert_legacy_trace_is_readable(database_path)

            _assert_alembic_succeeded(
                _run_alembic(database_path, "downgrade", TRACE_REVISION),
                f"downgrade {TRACE_REVISION}",
            )
            assert _alembic_revision(database_path) == TRACE_REVISION
            _assert_legacy_trace_storage(database_path)
            await _assert_legacy_trace_is_readable(database_path)

            _assert_alembic_succeeded(
                _run_alembic(database_path, "upgrade", "head"), "re-upgrade head"
            )
            assert _alembic_revision(database_path) == HEAD_REVISION
            _assert_legacy_trace_storage(database_path)
            await _assert_legacy_trace_is_readable(database_path)

            record_property("migration_start_revision", BASELINE_REVISION)
            record_property("migration_trace_revision", TRACE_REVISION)
            record_property("migration_head_revision", HEAD_REVISION)
            record_property("legacy_trace_schema_version", "1")
            record_property("legacy_trace_scope_isolation", "verified")
            record_property("legacy_trace_survived_downgrade", "true")
    finally:
        assert _parent_configuration_snapshot() == parent_configuration


def _create_invocation_conflict(database_path: Path) -> None:
    # A standalone conflicting index allows the real migration to start creating
    # its tables, then fail midway without bypassing table-adoption validation.
    with closing(sqlite3.connect(database_path)) as connection, connection:
        connection.execute(
            "CREATE TABLE migration_conflict_marker (conflict_marker TEXT NOT NULL)"
        )
        connection.execute(
            "INSERT INTO migration_conflict_marker (conflict_marker) VALUES (?)",
            ("expected-conflict-marker",),
        )
        connection.execute(
            "CREATE INDEX ix_agent_invocation_status "
            "ON migration_conflict_marker (conflict_marker)"
        )


@pytest.mark.db
def test_failed_migration_is_isolated_from_clean_upgrade_and_temporary_files(
    record_property,
) -> None:
    parent_configuration = _parent_configuration_snapshot()
    failure_directory = TemporaryDirectory(prefix="otakuneko-failed-migration-")
    failure_directory_path = Path(failure_directory.name)
    failure_database = failure_directory_path / "failure.sqlite3"
    try:
        try:
            _assert_alembic_succeeded(
                _run_alembic(failure_database, "stamp", TRACE_REVISION),
                f"stamp {TRACE_REVISION}",
            )
            _create_invocation_conflict(failure_database)

            failed_upgrade = _run_alembic(failure_database, "upgrade", "head")
            failed_diagnostic = (
                failed_upgrade.stdout + "\n" + failed_upgrade.stderr
            ).lower()
            failure_tables = _table_names(failure_database)
            record_property(
                "migration_failure_returncode", str(failed_upgrade.returncode)
            )
            record_property("migration_failure_category", "index_conflict")
            record_property(
                "migration_failure_diagnostic_matched",
                str(
                    "ix_agent_invocation_status" in failed_diagnostic
                    and "already exists" in failed_diagnostic
                ).lower(),
            )
            record_property(
                "migration_failure_revision", _alembic_revision(failure_database)
            )
            record_property(
                "migration_failure_partial_schema", ",".join(sorted(failure_tables))
            )

            assert failed_upgrade.returncode == 1
            assert "ix_agent_invocation_status" in failed_diagnostic
            assert "already exists" in failed_diagnostic
            assert _alembic_revision(failure_database) == TRACE_REVISION
            assert failure_tables == {
                "agent_invocation",
                "agent_run",
                "alembic_version",
                "migration_conflict_marker",
            }
            assert "invocation_id" in _table_columns(
                failure_database, "agent_invocation"
            )
            assert "conflict_marker" not in _table_columns(
                failure_database, "agent_invocation"
            )
            with closing(sqlite3.connect(failure_database)) as connection:
                marker = connection.execute(
                    "SELECT conflict_marker FROM migration_conflict_marker"
                ).fetchone()
            assert marker == ("expected-conflict-marker",)

            with TemporaryDirectory(prefix="otakuneko-clean-migration-") as directory:
                clean_database = Path(directory) / "clean.sqlite3"
                assert clean_database.resolve() != failure_database.resolve()
                _assert_alembic_succeeded(
                    _run_alembic(clean_database, "stamp", TRACE_REVISION),
                    f"stamp {TRACE_REVISION}",
                )
                clean_upgrade = _run_alembic(clean_database, "upgrade", "head")
                record_property(
                    "migration_clean_upgrade_returncode",
                    str(clean_upgrade.returncode),
                )
                _assert_alembic_succeeded(clean_upgrade, "clean upgrade head")

                clean_tables = _table_names(clean_database)
                assert clean_tables == {
                    "alembic_version",
                    "agent_invocation",
                    "agent_run",
                    "agent_run_event",
                }
                assert _alembic_revision(clean_database) == HEAD_REVISION
                invocation_columns = _table_columns(clean_database, "agent_invocation")
                assert "conflict_marker" not in invocation_columns
                assert "expected-conflict-marker" not in clean_upgrade.stdout
                assert "expected-conflict-marker" not in clean_upgrade.stderr
                assert "migration_conflict_marker" not in clean_tables
                with closing(sqlite3.connect(clean_database)) as connection:
                    invocation_count = connection.execute(
                        "SELECT COUNT(*) FROM agent_invocation"
                    ).fetchone()
                assert invocation_count == (0,)
                record_property(
                    "migration_clean_schema_tables", ",".join(sorted(clean_tables))
                )
                record_property("migration_clean_revision", HEAD_REVISION)
                record_property("migration_clean_conflict_markers", "none")
        finally:
            failure_directory.cleanup()

        assert not failure_database.exists()
        assert not failure_directory_path.exists()
        record_property("migration_failure_database_cleanup", "verified")
    finally:
        assert _parent_configuration_snapshot() == parent_configuration


def _model_result(payload: dict[str, object]) -> ModelCallResult:
    return ModelCallResult(
        provider="test-provider",
        model="test-model",
        operation="infer",
        status="completed",
        decision=payload,
    )


def test_decision_parser_accepts_legacy_v1_and_recovers_after_future_version() -> None:
    parser = DecisionParser()
    expected_run_id = "compatibility-test-run"

    legacy = parser.parse(
        _model_result({"action": "finish", "content": "done"}),
        expected_run_id=expected_run_id,
    )
    assert legacy.schema_version == "v1"
    assert legacy.run_id == expected_run_id

    explicit_v1 = parser.parse(
        _model_result({"schema_version": "v1", "action": "finish", "content": "done"}),
        expected_run_id=expected_run_id,
    )
    assert explicit_v1.schema_version == "v1"

    with pytest.raises(DecisionParseError) as error:
        parser.parse(
            _model_result(
                {"schema_version": "v2", "action": "finish", "content": "done"}
            ),
            expected_run_id=expected_run_id,
        )
    assert error.value.error_code == ErrorCode.INVALID_REQUEST

    after_rejection = parser.parse(
        _model_result({"schema_version": "v1", "action": "finish", "content": "done"}),
        expected_run_id=expected_run_id,
    )
    assert after_rejection.schema_version == "v1"
    assert after_rejection.run_id == expected_run_id

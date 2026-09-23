"""Alembic upgrade/downgrade coverage for durable memory."""

from __future__ import annotations

import os
from pathlib import Path
import sqlite3
import subprocess
import sys


def _run_alembic(backend: Path, env: dict[str, str], *args: str) -> None:
    result = subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        cwd=backend,
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_agent_memory_migration_upgrades_and_downgrades(tmp_path):
    backend = Path(__file__).resolve().parents[2]
    database = tmp_path / "migration.db"
    env = {
        **os.environ,
        "DEBUG": "false",
        "DEPLOY_MODE": "local",
        "SQLITE_FILE": str(database),
    }

    _run_alembic(backend, env, "stamp", "bbd93366421b")
    _run_alembic(backend, env, "upgrade", "head")

    with sqlite3.connect(database) as connection:
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
        indexes = {
            row[1] for row in connection.execute("PRAGMA index_list('agent_memory')")
        }
    assert "agent_memory" in tables
    assert {
        "ix_agent_memory_user_id",
        "ix_agent_memory_thread_id",
        "ix_agent_memory_kind",
        "ix_agent_memory_created_at",
    }.issubset(indexes)

    _run_alembic(backend, env, "downgrade", "bbd93366421b")
    with sqlite3.connect(database) as connection:
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
    assert "agent_memory" not in tables

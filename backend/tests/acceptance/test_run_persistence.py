from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlmodel import SQLModel, select

from app.harness.contracts import RunResult
from app.harness.coordinator import RunCoordinator
from app.harness.persistence.event_store import EventStore
from app.harness.persistence.run_store import RunStore
from app.harness.task import AgentTask
from app.models.agent_run import AgentInvocation


class ReadOnlyAdapter:
    async def stream(self, state, **kwargs):
        yield {"type": "message_start"}
        yield {"type": "message_chunk", "content": "anime result"}
        yield {"type": "message_end"}


class GraphErrorAdapter:
    async def stream(self, state, **kwargs):
        yield {"type": "error", "error_code": "transient"}


class ToolAdapter:
    async def stream(self, state, **kwargs):
        yield {
            "type": "tool_call_start",
            "name": "anime.search",
            "inputs": {"query": "frieren"},
        }
        yield {
            "type": "tool_call_end",
            "name": "anime.search",
            "status": "success",
        }


class FailingEventStore:
    async def append(self, event):
        raise RuntimeError("database unavailable")


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


@pytest.mark.asyncio
async def test_coordinator_persists_read_only_run_and_graph_failure(tmp_path) -> None:
    database_url = f"sqlite+aiosqlite:///{(tmp_path / 'interactive.db').as_posix()}"
    engine = create_async_engine(database_url)
    async with engine.begin() as connection:
        await connection.run_sync(SQLModel.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async with factory() as session:
        run_store = RunStore(session)
        event_store = EventStore(session)
        coordinator = RunCoordinator(
            ReadOnlyAdapter(), run_store=run_store, event_store=event_store
        )
        items = [
            item
            async for item in coordinator.stream(
                AgentTask(task_id=None, user_id=7, goal="search anime"), {}
            )
        ]
        result = next(item for item in items if isinstance(item, RunResult))
        assert result.status == "completed"
        stored = await run_store.get(result.run_id, user_id=7)
        assert stored is not None
        assert stored.status == "succeeded"
        events = await event_store.list_after(result.run_id, after_sequence=0)
        assert events[-1].event_type == "run.succeeded"
        assert [event.sequence for event in events] == list(
            range(1, len(events) + 1)
        )

        tool_coordinator = RunCoordinator(
            ToolAdapter(), run_store=run_store, event_store=event_store
        )
        tool_items = [
            item
            async for item in tool_coordinator.stream(
                AgentTask(user_id=7, goal="search anime tool"), {}
            )
        ]
        tool_result = next(item for item in tool_items if isinstance(item, RunResult))
        invocations = (
            await session.execute(select(AgentInvocation))
        ).scalars().all()
        assert tool_result.status == "completed"
        assert len(invocations) == 1
        assert invocations[0].status == "succeeded"

        failed_persistence = RunCoordinator(
            ReadOnlyAdapter(), run_store=run_store, event_store=FailingEventStore()
        )
        persistence_items = [
            item
            async for item in failed_persistence.stream(
                AgentTask(user_id=7, goal="persistence failure"), {}
            )
        ]
        persistence_result = next(
            item for item in persistence_items if isinstance(item, RunResult)
        )
        persistence_stored = await run_store.get(
            persistence_result.run_id, user_id=7
        )
        assert persistence_result.status == "failed"
        assert persistence_stored is not None
        assert persistence_stored.status == "failed"

        failed_coordinator = RunCoordinator(
            GraphErrorAdapter(), run_store=run_store, event_store=event_store
        )
        failed_items = [
            item
            async for item in failed_coordinator.stream(
                AgentTask(user_id=7, goal="graph failure"), {}
            )
        ]
        failed = next(item for item in failed_items if isinstance(item, RunResult))
        failed_stored = await run_store.get(failed.run_id, user_id=7)
        assert failed.status == "failed"
        assert failed_stored is not None
        assert failed_stored.status == "failed"
    await engine.dispose()


def test_interactive_run_migration_creates_and_drops_only_new_tables(tmp_path) -> None:
    backend = Path(__file__).resolve().parents[2]
    database = tmp_path / "migration.db"
    env = {
        **os.environ,
        "DEBUG": "false",
        "DEPLOY_MODE": "local",
        "SQLITE_FILE": str(database),
    }

    _run_alembic(backend, env, "stamp", "5ae716ad749d")
    _run_alembic(backend, env, "upgrade", "head")

    import sqlite3

    with sqlite3.connect(database) as connection:
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
    assert {"agent_run", "agent_invocation", "agent_run_event"}.issubset(tables)

    _run_alembic(backend, env, "downgrade", "5ae716ad749d")
    with sqlite3.connect(database) as connection:
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
    assert not {"agent_run", "agent_invocation", "agent_run_event"}.intersection(tables)

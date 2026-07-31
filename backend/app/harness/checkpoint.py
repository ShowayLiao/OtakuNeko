"""Run-scoped checkpoint ports and small local-development adapters."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from pathlib import Path
from typing import Protocol

import aiosqlite

from app.harness.state import AgentState


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _scope(run_id: str, thread_id: str) -> tuple[str, str]:
    normalized_run_id = str(run_id).strip()
    normalized_thread_id = str(thread_id).strip()
    if not normalized_run_id or not normalized_thread_id:
        raise ValueError("run_id and thread_id are required")
    return normalized_run_id, normalized_thread_id


class CheckpointStore(Protocol):
    """Run-scoped state port independent of LangGraph checkpoint types."""

    async def save(self, run_id: str, thread_id: str, state: AgentState) -> None:
        ...

    async def load(self, run_id: str, thread_id: str) -> AgentState | None:
        ...

    async def mark_abandoned(self, run_id: str, reason: str) -> None:
        ...

    # Legacy Runtime compatibility. These methods remain available while the
    # runtime's older task-id checkpoint hook is migrated in a later batch.
    async def save_state(self, state: AgentState) -> None:
        ...

    async def load_state(self, task_id: int) -> AgentState | None:
        ...


class InMemoryCheckpointStore:
    """Scoped checkpoint store for tests and local non-persistent runs."""

    def __init__(self):
        self._states: dict[tuple[str, str], AgentState] = {}
        self._legacy_states: dict[int, AgentState] = {}
        self._abandoned: dict[str, str] = {}

    @staticmethod
    def _copy(state: AgentState) -> AgentState:
        return state.model_copy(deep=True)

    async def save(self, run_id: str, thread_id: str, state: AgentState) -> None:
        run_id, thread_id = _scope(run_id, thread_id)
        if run_id in self._abandoned:
            raise ValueError(f"checkpoint run {run_id} is abandoned")
        self._states[(run_id, thread_id)] = self._copy(state)

    async def load(self, run_id: str, thread_id: str) -> AgentState | None:
        run_id, thread_id = _scope(run_id, thread_id)
        state = self._states.get((run_id, thread_id))
        if state is None:
            return None
        return self._copy(state)

    async def mark_abandoned(self, run_id: str, reason: str) -> None:
        run_id = str(run_id).strip()
        if not run_id:
            raise ValueError("run_id is required")
        self._abandoned[run_id] = str(reason)
        for (stored_run_id, _), state in self._states.items():
            if stored_run_id == run_id:
                state.status = "abandoned"
                state.context = {
                    **state.context,
                    "abandon_reason": str(reason),
                }
        for state in self._legacy_states.values():
            if str(state.task.metadata.get("run_id", "")).strip() == run_id:
                state.status = "abandoned"
                state.context = {
                    **state.context,
                    "abandon_reason": str(reason),
                }

    async def save_state(self, state: AgentState) -> None:
        task_id = state.task.task_id
        metadata = state.task.metadata
        run_id = metadata.get("run_id")
        thread_id = metadata.get("thread_id")
        if run_id is not None and thread_id is not None:
            await self.save(str(run_id), str(thread_id), state)
        if task_id is not None:
            self._legacy_states[task_id] = self._copy(state)

    async def load_state(self, task_id: int) -> AgentState | None:
        state = self._legacy_states.get(task_id)
        if state is None:
            return None
        return self._copy(state)


class SqliteCheckpointStore:
    """Small file-backed checkpoint adapter for one-worker local persistence.

    It stores only the harness state contract. LangGraph's native checkpoint
    object remains behind ``ChatWorkflow`` and is never exposed through this
    port. A shared multi-worker deployment requires a separately verified
    adapter implementing this port.
    """

    def __init__(self, path: str):
        self.path = str(path)
        self._init_lock = asyncio.Lock()
        self._initialized = False

    async def _ensure_schema(self) -> None:
        if self._initialized:
            return
        async with self._init_lock:
            if self._initialized:
                return
            if self.path != ":memory:":
                Path(self.path).parent.mkdir(parents=True, exist_ok=True)
            async with aiosqlite.connect(self.path) as connection:
                await connection.execute(
                    """
                    CREATE TABLE IF NOT EXISTS harness_checkpoint_runs (
                        run_id TEXT PRIMARY KEY,
                        status TEXT NOT NULL,
                        abandon_reason TEXT,
                        updated_at TEXT NOT NULL
                    )
                    """
                )
                await connection.execute(
                    """
                    CREATE TABLE IF NOT EXISTS harness_checkpoints (
                        run_id TEXT NOT NULL,
                        thread_id TEXT NOT NULL,
                        state_json TEXT NOT NULL,
                        status TEXT NOT NULL,
                        abandon_reason TEXT,
                        updated_at TEXT NOT NULL,
                        PRIMARY KEY (run_id, thread_id)
                    )
                    """
                )
                await connection.commit()
            self._initialized = True

    @staticmethod
    def _legacy_scope(state: AgentState) -> tuple[str, str] | None:
        task_id = state.task.task_id
        metadata = state.task.metadata
        if metadata.get("run_id") is not None and metadata.get("thread_id") is not None:
            return str(metadata["run_id"]), str(metadata["thread_id"])
        if task_id is None:
            return None
        return (
            str(metadata.get("run_id") or f"task:{task_id}"),
            str(metadata.get("thread_id") or f"task:{task_id}"),
        )

    async def save(self, run_id: str, thread_id: str, state: AgentState) -> None:
        run_id, thread_id = _scope(run_id, thread_id)
        await self._ensure_schema()
        state_json = state.model_dump_json()
        async with aiosqlite.connect(self.path) as connection:
            cursor = await connection.execute(
                "SELECT status FROM harness_checkpoint_runs WHERE run_id = ?",
                (run_id,),
            )
            existing = await cursor.fetchone()
            if existing is not None and existing[0] == "abandoned":
                raise ValueError(f"checkpoint run {run_id} is abandoned")
            await connection.execute(
                """
                INSERT INTO harness_checkpoint_runs
                    (run_id, status, abandon_reason, updated_at)
                VALUES (?, ?, NULL, ?)
                ON CONFLICT(run_id) DO UPDATE SET
                    status = excluded.status,
                    abandon_reason = NULL,
                    updated_at = excluded.updated_at
                """,
                (run_id, state.status, _utc_now()),
            )
            await connection.execute(
                """
                INSERT INTO harness_checkpoints
                    (run_id, thread_id, state_json, status, abandon_reason, updated_at)
                VALUES (?, ?, ?, ?, NULL, ?)
                ON CONFLICT(run_id, thread_id) DO UPDATE SET
                    state_json = excluded.state_json,
                    status = excluded.status,
                    abandon_reason = NULL,
                    updated_at = excluded.updated_at
                """,
                (run_id, thread_id, state_json, state.status, _utc_now()),
            )
            await connection.commit()

    async def load(self, run_id: str, thread_id: str) -> AgentState | None:
        run_id, thread_id = _scope(run_id, thread_id)
        await self._ensure_schema()
        async with aiosqlite.connect(self.path) as connection:
            cursor = await connection.execute(
                """
                SELECT state_json, status, abandon_reason
                FROM harness_checkpoints
                WHERE run_id = ? AND thread_id = ?
                """,
                (run_id, thread_id),
            )
            row = await cursor.fetchone()
        if row is None:
            return None
        state = AgentState.model_validate_json(row[0])
        if row[1] == "abandoned":
            state.status = "abandoned"
            state.context = {
                **state.context,
                "abandon_reason": row[2] or "checkpoint abandoned",
            }
        return state

    async def mark_abandoned(self, run_id: str, reason: str) -> None:
        run_id = str(run_id).strip()
        if not run_id:
            raise ValueError("run_id is required")
        await self._ensure_schema()
        async with aiosqlite.connect(self.path) as connection:
            await connection.execute(
                """
                INSERT INTO harness_checkpoint_runs
                    (run_id, status, abandon_reason, updated_at)
                VALUES (?, 'abandoned', ?, ?)
                ON CONFLICT(run_id) DO UPDATE SET
                    status = 'abandoned',
                    abandon_reason = excluded.abandon_reason,
                    updated_at = excluded.updated_at
                """,
                (run_id, str(reason), _utc_now()),
            )
            await connection.execute(
                """
                UPDATE harness_checkpoints
                SET status = 'abandoned', abandon_reason = ?, updated_at = ?
                WHERE run_id = ?
                """,
                (str(reason), _utc_now(), run_id),
            )
            await connection.commit()

    async def save_state(self, state: AgentState) -> None:
        scope = self._legacy_scope(state)
        if scope is None:
            return
        await self.save(*scope, state)

    async def load_state(self, task_id: int) -> AgentState | None:
        return await self.load(f"task:{task_id}", f"task:{task_id}")

    async def close(self) -> None:
        """Compatibility lifecycle hook; operations use short-lived handles."""
        return None

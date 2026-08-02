"""Run-scoped checkpoint ports and small local-development adapters."""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable, Protocol

import aiosqlite

from app.harness.state import AgentState


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


class CheckpointLeaseLost(RuntimeError):
    """A checkpoint writer no longer owns the current fencing token."""


@dataclass(frozen=True)
class CheckpointLease:
    run_id: str
    thread_id: str
    worker_id: str
    fencing_token: int
    lease_expires_at: datetime


@dataclass(frozen=True)
class CancellationRequest:
    run_id: str
    requester: str
    reason: str
    requested_at: datetime


def _scope(run_id: str, thread_id: str) -> tuple[str, str]:
    normalized_run_id = str(run_id).strip()
    normalized_thread_id = str(thread_id).strip()
    if not normalized_run_id or not normalized_thread_id:
        raise ValueError("run_id and thread_id are required")
    return normalized_run_id, normalized_thread_id


def run_checkpoint_config(
    thread_id: str,
    run_id: str | None = None,
) -> dict[str, dict[str, str]]:
    """Build the single thread/run namespace mapping used by all adapters.

    An empty namespace is retained only as the explicit legacy-read scope for
    callers that have not been assigned a Run yet. Active Runs always receive
    their own namespace, preventing short-term context from crossing Runs on
    the same user-scoped conversation thread.
    """
    normalized_thread_id = str(thread_id).strip()
    if not normalized_thread_id:
        raise ValueError("thread_id is required")
    namespace = str(run_id).strip() if run_id is not None else ""
    return {
        "configurable": {
            "thread_id": normalized_thread_id,
            "checkpoint_ns": namespace,
        }
    }


def validate_checkpoint_configuration(
    *,
    deploy_mode: str,
    adapter: str,
    single_worker: bool,
    worker_count: int = 1,
) -> None:
    """Fail closed when a local SQLite adapter is configured for shared workers."""
    if worker_count < 1:
        raise ValueError("worker_count must be positive")
    if (
        str(deploy_mode).lower() != "local"
        and str(adapter).lower() in {"sqlite", "sqlite-single-worker"}
        and (not single_worker or worker_count > 1)
    ):
        raise RuntimeError(
            "SQLite checkpoints require explicit single-worker deployment; "
            "configure a verified shared checkpoint adapter for multiple workers"
        )


class CheckpointStore(Protocol):
    """Run-scoped state port independent of LangGraph checkpoint types."""

    async def save(
        self,
        run_id: str,
        thread_id: str,
        state: AgentState,
        *,
        worker_id: str | None = None,
        fencing_token: int | None = None,
    ) -> None:
        ...

    async def load(self, run_id: str, thread_id: str) -> AgentState | None:
        ...

    async def mark_abandoned(self, run_id: str, reason: str) -> None:
        ...

    async def claim_lease(
        self,
        run_id: str,
        thread_id: str,
        worker_id: str,
        lease_seconds: int,
    ) -> CheckpointLease | None:
        ...

    async def renew_lease(
        self,
        lease: CheckpointLease,
        lease_seconds: int,
    ) -> CheckpointLease | None:
        ...

    async def release_lease(self, lease: CheckpointLease) -> bool:
        ...

    async def request_cancellation(
        self,
        run_id: str,
        *,
        requester: str,
        reason: str,
    ) -> CancellationRequest:
        ...

    async def get_cancellation(self, run_id: str) -> CancellationRequest | None:
        ...

    async def is_cancellation_requested(self, run_id: str) -> bool:
        ...

    async def recover_expired(self, run_id: str, reason: str) -> bool:
        ...

    # Legacy Runtime compatibility. These methods remain available while the
    # runtime's older task-id checkpoint hook is migrated in a later batch.
    async def save_state(self, state: AgentState) -> None:
        ...

    async def load_state(self, task_id: int) -> AgentState | None:
        ...


class InMemoryCheckpointStore:
    """Scoped checkpoint store for tests and local non-persistent runs."""

    def __init__(self, *, clock: Callable[[], datetime] | None = None):
        self._states: dict[tuple[str, str], AgentState] = {}
        self._legacy_states: dict[int, AgentState] = {}
        self._abandoned: dict[str, str] = {}
        self._leases: dict[tuple[str, str], CheckpointLease] = {}
        self._checkpoint_versions: dict[tuple[str, str], int] = {}
        self._cancellations: dict[str, CancellationRequest] = {}
        self._clock = clock or (lambda: datetime.now(timezone.utc))

    @staticmethod
    def _copy(state: AgentState) -> AgentState:
        return state.model_copy(deep=True)

    async def save(
        self,
        run_id: str,
        thread_id: str,
        state: AgentState,
        *,
        worker_id: str | None = None,
        fencing_token: int | None = None,
    ) -> None:
        run_id, thread_id = _scope(run_id, thread_id)
        if run_id in self._abandoned:
            raise ValueError(f"checkpoint run {run_id} is abandoned")
        self._assert_lease(run_id, thread_id, worker_id, fencing_token)
        key = (run_id, thread_id)
        version = self._checkpoint_versions.get(key, 0) + 1
        stored = self._copy(state)
        stored.context = {**stored.context, "checkpoint_version": version}
        self._checkpoint_versions[key] = version
        self._states[key] = stored

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

    async def claim_lease(
        self,
        run_id: str,
        thread_id: str,
        worker_id: str,
        lease_seconds: int,
    ) -> CheckpointLease | None:
        run_id, thread_id = _scope(run_id, thread_id)
        worker_id = str(worker_id).strip()
        if not worker_id or lease_seconds <= 0:
            raise ValueError("worker_id and positive lease_seconds are required")
        if run_id in self._abandoned:
            raise ValueError(f"checkpoint run {run_id} is abandoned")
        key = (run_id, thread_id)
        current = self._leases.get(key)
        now = _aware(self._clock())
        if current is not None and current.lease_expires_at > now:
            return current if current.worker_id == worker_id else None
        token = current.fencing_token + 1 if current is not None else 1
        lease = CheckpointLease(
            run_id=run_id,
            thread_id=thread_id,
            worker_id=worker_id,
            fencing_token=token,
            lease_expires_at=now + timedelta(seconds=lease_seconds),
        )
        self._leases[key] = lease
        return lease

    async def renew_lease(
        self,
        lease: CheckpointLease,
        lease_seconds: int,
    ) -> CheckpointLease | None:
        current = self._leases.get((lease.run_id, lease.thread_id))
        now = _aware(self._clock())
        if (
            current is None
            or current.worker_id != lease.worker_id
            or current.fencing_token != lease.fencing_token
            or current.lease_expires_at <= now
            or lease_seconds <= 0
        ):
            return None
        renewed = CheckpointLease(
            **{
                **current.__dict__,
                "lease_expires_at": now + timedelta(seconds=lease_seconds),
            }
        )
        self._leases[(lease.run_id, lease.thread_id)] = renewed
        return renewed

    async def release_lease(self, lease: CheckpointLease) -> bool:
        current = self._leases.get((lease.run_id, lease.thread_id))
        if current is None or (
            current.worker_id != lease.worker_id
            or current.fencing_token != lease.fencing_token
        ):
            return False
        self._leases.pop((lease.run_id, lease.thread_id), None)
        return True

    async def request_cancellation(
        self,
        run_id: str,
        *,
        requester: str,
        reason: str,
    ) -> CancellationRequest:
        normalized = str(run_id).strip()
        if not normalized:
            raise ValueError("run_id is required")
        existing = self._cancellations.get(normalized)
        if existing is not None:
            return existing
        request = CancellationRequest(
            run_id=normalized,
            requester=str(requester)[:200],
            reason=str(reason)[:500],
            requested_at=_aware(self._clock()),
        )
        self._cancellations[normalized] = request
        return request

    async def get_cancellation(self, run_id: str) -> CancellationRequest | None:
        return self._cancellations.get(str(run_id).strip())

    async def is_cancellation_requested(self, run_id: str) -> bool:
        return await self.get_cancellation(run_id) is not None

    async def recover_expired(self, run_id: str, reason: str) -> bool:
        target = str(run_id).strip()
        expired = any(
            lease.run_id == target and lease.lease_expires_at <= _aware(self._clock())
            for lease in self._leases.values()
        )
        if not expired:
            return False
        await self.mark_abandoned(target, reason)
        return True

    def _assert_lease(
        self,
        run_id: str,
        thread_id: str,
        worker_id: str | None,
        fencing_token: int | None,
    ) -> None:
        current = self._leases.get((run_id, thread_id))
        if current is None and worker_id is None and fencing_token is None:
            return
        now = _aware(self._clock())
        if (
            current is None
            or current.lease_expires_at <= now
            or worker_id != current.worker_id
            or fencing_token != current.fencing_token
        ):
            raise CheckpointLeaseLost(
                f"checkpoint lease lost for {run_id}/{thread_id}"
            )

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

    def __init__(self, path: str, *, clock: Callable[[], datetime] | None = None):
        self.path = str(path)
        self._init_lock = asyncio.Lock()
        self._initialized = False
        self._clock = clock or (lambda: datetime.now(timezone.utc))

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
                await connection.execute(
                    """
                    CREATE TABLE IF NOT EXISTS harness_checkpoint_leases (
                        run_id TEXT NOT NULL,
                        thread_id TEXT NOT NULL,
                        worker_id TEXT NOT NULL,
                        fencing_token INTEGER NOT NULL,
                        lease_expires_at TEXT NOT NULL,
                        PRIMARY KEY (run_id, thread_id)
                    )
                    """
                )
                await connection.execute(
                    """
                    CREATE TABLE IF NOT EXISTS harness_cancellation_requests (
                        run_id TEXT PRIMARY KEY,
                        requester TEXT NOT NULL,
                        reason TEXT NOT NULL,
                        requested_at TEXT NOT NULL
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

    async def save(
        self,
        run_id: str,
        thread_id: str,
        state: AgentState,
        *,
        worker_id: str | None = None,
        fencing_token: int | None = None,
    ) -> None:
        run_id, thread_id = _scope(run_id, thread_id)
        await self._ensure_schema()
        stored = state.model_copy(deep=True)
        async with aiosqlite.connect(self.path) as connection:
            await self._assert_sqlite_lease(
                connection,
                run_id,
                thread_id,
                worker_id,
                fencing_token,
            )
            cursor = await connection.execute(
                "SELECT status FROM harness_checkpoint_runs WHERE run_id = ?",
                (run_id,),
            )
            existing = await cursor.fetchone()
            if existing is not None and existing[0] == "abandoned":
                raise ValueError(f"checkpoint run {run_id} is abandoned")
            version_cursor = await connection.execute(
                "SELECT state_json FROM harness_checkpoints WHERE run_id = ? AND thread_id = ?",
                (run_id, thread_id),
            )
            previous = await version_cursor.fetchone()
            previous_version = 0
            if previous is not None:
                try:
                    previous_version = int(
                        json.loads(previous[0]).get("context", {}).get(
                            "checkpoint_version", 0
                        )
                    )
                except (TypeError, ValueError, json.JSONDecodeError):
                    previous_version = 0
            stored.context = {
                **stored.context,
                "checkpoint_version": previous_version + 1,
            }
            state_json = stored.model_dump_json()
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

    async def claim_lease(
        self,
        run_id: str,
        thread_id: str,
        worker_id: str,
        lease_seconds: int,
    ) -> CheckpointLease | None:
        run_id, thread_id = _scope(run_id, thread_id)
        worker_id = str(worker_id).strip()
        if not worker_id or lease_seconds <= 0:
            raise ValueError("worker_id and positive lease_seconds are required")
        await self._ensure_schema()
        now = _aware(self._clock())
        async with aiosqlite.connect(self.path) as connection:
            await connection.execute("BEGIN IMMEDIATE")
            abandoned = await connection.execute(
                "SELECT status FROM harness_checkpoint_runs WHERE run_id = ?",
                (run_id,),
            )
            abandoned_row = await abandoned.fetchone()
            if abandoned_row is not None and abandoned_row[0] == "abandoned":
                await connection.rollback()
                raise ValueError(f"checkpoint run {run_id} is abandoned")
            cursor = await connection.execute(
                "SELECT worker_id, fencing_token, lease_expires_at "
                "FROM harness_checkpoint_leases WHERE run_id = ? AND thread_id = ?",
                (run_id, thread_id),
            )
            current = await cursor.fetchone()
            if current is not None:
                current_expiry = _aware(datetime.fromisoformat(current[2]))
                if current_expiry > now:
                    await connection.commit()
                    if current[0] != worker_id:
                        return None
                    return CheckpointLease(
                        run_id=run_id,
                        thread_id=thread_id,
                        worker_id=current[0],
                        fencing_token=int(current[1]),
                        lease_expires_at=current_expiry,
                    )
                token = int(current[1]) + 1
            else:
                token = 1
            expiry = now + timedelta(seconds=lease_seconds)
            await connection.execute(
                "INSERT INTO harness_checkpoint_leases "
                "(run_id, thread_id, worker_id, fencing_token, lease_expires_at) "
                "VALUES (?, ?, ?, ?, ?) "
                "ON CONFLICT(run_id, thread_id) DO UPDATE SET "
                "worker_id=excluded.worker_id, fencing_token=excluded.fencing_token, "
                "lease_expires_at=excluded.lease_expires_at",
                (run_id, thread_id, worker_id, token, expiry.isoformat()),
            )
            await connection.commit()
        return CheckpointLease(run_id, thread_id, worker_id, token, expiry)

    async def renew_lease(
        self,
        lease: CheckpointLease,
        lease_seconds: int,
    ) -> CheckpointLease | None:
        if lease_seconds <= 0:
            return None
        await self._ensure_schema()
        now = _aware(self._clock())
        expiry = now + timedelta(seconds=lease_seconds)
        async with aiosqlite.connect(self.path) as connection:
            cursor = await connection.execute(
                "UPDATE harness_checkpoint_leases SET lease_expires_at = ? "
                "WHERE run_id = ? AND thread_id = ? AND worker_id = ? "
                "AND fencing_token = ? AND lease_expires_at > ?",
                (
                    expiry.isoformat(),
                    lease.run_id,
                    lease.thread_id,
                    lease.worker_id,
                    lease.fencing_token,
                    now.isoformat(),
                ),
            )
            await connection.commit()
            if cursor.rowcount != 1:
                return None
        return CheckpointLease(
            lease.run_id,
            lease.thread_id,
            lease.worker_id,
            lease.fencing_token,
            expiry,
        )

    async def release_lease(self, lease: CheckpointLease) -> bool:
        await self._ensure_schema()
        async with aiosqlite.connect(self.path) as connection:
            cursor = await connection.execute(
                "DELETE FROM harness_checkpoint_leases WHERE run_id = ? AND thread_id = ? "
                "AND worker_id = ? AND fencing_token = ?",
                (lease.run_id, lease.thread_id, lease.worker_id, lease.fencing_token),
            )
            await connection.commit()
            return cursor.rowcount == 1

    async def request_cancellation(
        self,
        run_id: str,
        *,
        requester: str,
        reason: str,
    ) -> CancellationRequest:
        normalized = str(run_id).strip()
        if not normalized:
            raise ValueError("run_id is required")
        await self._ensure_schema()
        async with aiosqlite.connect(self.path) as connection:
            await connection.execute(
                "INSERT OR IGNORE INTO harness_cancellation_requests "
                "(run_id, requester, reason, requested_at) VALUES (?, ?, ?, ?)",
                (
                    normalized,
                    str(requester)[:200],
                    str(reason)[:500],
                    _aware(self._clock()).isoformat(),
                ),
            )
            await connection.commit()
        request = await self.get_cancellation(normalized)
        if request is None:
            raise RuntimeError("cancellation request was not persisted")
        return request

    async def get_cancellation(self, run_id: str) -> CancellationRequest | None:
        await self._ensure_schema()
        async with aiosqlite.connect(self.path) as connection:
            cursor = await connection.execute(
                "SELECT run_id, requester, reason, requested_at "
                "FROM harness_cancellation_requests WHERE run_id = ?",
                (str(run_id).strip(),),
            )
            row = await cursor.fetchone()
        if row is None:
            return None
        return CancellationRequest(
            row[0], row[1], row[2], _aware(datetime.fromisoformat(row[3]))
        )

    async def is_cancellation_requested(self, run_id: str) -> bool:
        return await self.get_cancellation(run_id) is not None

    async def recover_expired(self, run_id: str, reason: str) -> bool:
        await self._ensure_schema()
        now = _aware(self._clock())
        async with aiosqlite.connect(self.path) as connection:
            cursor = await connection.execute(
                "SELECT 1 FROM harness_checkpoint_leases WHERE run_id = ? "
                "AND lease_expires_at <= ?",
                (str(run_id).strip(), now.isoformat()),
            )
            expired = await cursor.fetchone()
        if expired is None:
            return False
        await self.mark_abandoned(str(run_id), reason)
        return True

    async def _assert_sqlite_lease(
        self,
        connection: aiosqlite.Connection,
        run_id: str,
        thread_id: str,
        worker_id: str | None,
        fencing_token: int | None,
    ) -> None:
        cursor = await connection.execute(
            "SELECT worker_id, fencing_token, lease_expires_at "
            "FROM harness_checkpoint_leases WHERE run_id = ? AND thread_id = ?",
            (run_id, thread_id),
        )
        current = await cursor.fetchone()
        if current is None and worker_id is None and fencing_token is None:
            return
        now = _aware(self._clock())
        if (
            current is None
            or _aware(datetime.fromisoformat(current[2])) <= now
            or worker_id != current[0]
            or fencing_token != int(current[1])
        ):
            raise CheckpointLeaseLost(
                f"checkpoint lease lost for {run_id}/{thread_id}"
            )

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

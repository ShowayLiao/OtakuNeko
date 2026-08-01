"""Durable idempotency execution records built on the BATCH-06 tables."""

from __future__ import annotations

import asyncio
import hashlib
import inspect
import json
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Literal

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.harness.contracts import RunEvent
from app.harness.persistence.event_store import EventStore
from app.harness.persistence.run_store import RunConflict, RunStore
from app.models.agent_run import AgentRun, AgentRunEvent


IdempotencyStatus = Literal["replayed", "conflict", "executed"]
Operation = Callable[[], Any | Awaitable[Any]]


@dataclass(frozen=True)
class IdempotencyExecution:
    status: IdempotencyStatus
    result: dict[str, Any]


def _canonical_hash(payload: Any) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _safe_failure() -> dict[str, Any]:
    return {
        "status": "attention_required",
        "error_code": "operation_state_unknown",
        "message": "The operation state is unknown; manual verification is required.",
        "retryable": False,
    }


class SqlIdempotencyStore:
    """Persist one safe operation result in the existing Run/Event contract."""

    _locks: dict[str, asyncio.Lock] = {}
    _locks_guard = asyncio.Lock()

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def execute_once(
        self,
        scope: str,
        key: str,
        payload_hash: str,
        operation: Operation,
    ) -> IdempotencyExecution:
        run_id = f"idem-{_canonical_hash({'scope': scope, 'key': key})}"
        lock = await self._lock_for(run_id)
        async with lock:
            existing = await self._session.get(AgentRun, run_id)
            if existing is not None:
                return await self._existing_result(existing, payload_hash)

            try:
                await RunStore(self._session).create(
                    run_id=run_id,
                    user_id=None,
                    thread_id=scope,
                    status="running",
                    goal_hash=payload_hash,
                    model="idempotency.v1",
                )
            except IntegrityError:
                await self._session.rollback()
                existing = await self._session.get(AgentRun, run_id)
                if existing is not None:
                    return await self._existing_result(existing, payload_hash)
                raise
            except RunConflict:
                existing = await self._session.get(AgentRun, run_id)
                if existing is not None:
                    return await self._existing_result(existing, payload_hash)
                raise

            invocation_id = f"idem-inv-{_canonical_hash({'run_id': run_id})}"
            await RunStore(self._session).create_invocation(
                run_id=run_id,
                invocation_id=invocation_id,
                sequence=1,
                capability="idempotency.operation",
                capability_version="v1",
                input_payload={"scope": scope, "payload_hash": payload_hash},
                idempotency_key=key,
            )
            result = await self._run_operation(operation)
            await EventStore(self._session).append(
                RunEvent(
                    run_id=run_id,
                    sequence=1,
                    event_type="idempotency.result",
                    invocation_id=invocation_id,
                    payload={"result": result},
                )
            )
            invocation_status = (
                "succeeded" if result.get("status") == "succeeded" else "failed"
            )
            await RunStore(self._session).finish_invocation(
                invocation_id,
                invocation_status,
                error_code=result.get("error_code"),
            )
            await RunStore(self._session).transition(
                run_id,
                "succeeded" if invocation_status == "succeeded" else "failed",
                error_code=result.get("error_code"),
            )
            return IdempotencyExecution(status="executed", result=result)

    async def _existing_result(
        self,
        run: AgentRun,
        payload_hash: str,
    ) -> IdempotencyExecution:
        if run.goal_hash != payload_hash:
            return IdempotencyExecution(
                status="conflict",
                result={
                    "status": "conflict",
                    "error_code": "idempotency_conflict",
                    "message": "The idempotency key was reused with different arguments.",
                    "retryable": False,
                },
            )
        event = (
            await self._session.execute(
                select(AgentRunEvent).where(
                    AgentRunEvent.run_id == run.run_id,
                    AgentRunEvent.event_type == "idempotency.result",
                )
            )
        ).scalars().first()
        if event is not None:
            return IdempotencyExecution(
                status="replayed",
                result=event.payload.get("result", _safe_failure()),
            )
        return IdempotencyExecution(status="replayed", result=_safe_failure())

    async def _run_operation(self, operation: Operation) -> dict[str, Any]:
        try:
            value = operation()
            if inspect.isawaitable(value):
                value = await value
            if value is None:
                return {"status": "succeeded", "message": "Operation completed."}
            if isinstance(value, dict):
                return value
        except Exception:
            return _safe_failure()
        return {"status": "succeeded", "message": "Operation completed."}

    @classmethod
    async def _lock_for(cls, run_id: str) -> asyncio.Lock:
        async with cls._locks_guard:
            return cls._locks.setdefault(run_id, asyncio.Lock())


class InMemoryIdempotencyStore:
    """Small test adapter with the same replay/conflict contract."""

    def __init__(self) -> None:
        self._records: dict[tuple[str, str], tuple[str, dict[str, Any]]] = {}
        self._locks: dict[tuple[str, str], asyncio.Lock] = {}

    async def execute_once(
        self,
        scope: str,
        key: str,
        payload_hash: str,
        operation: Operation,
    ) -> IdempotencyExecution:
        identity = (scope, key)
        lock = self._locks.setdefault(identity, asyncio.Lock())
        async with lock:
            existing = self._records.get(identity)
            if existing is not None:
                previous_hash, result = existing
                if previous_hash != payload_hash:
                    return IdempotencyExecution(
                        status="conflict",
                        result={
                            "status": "conflict",
                            "error_code": "idempotency_conflict",
                            "message": "The idempotency key was reused with different arguments.",
                            "retryable": False,
                        },
                    )
                return IdempotencyExecution(status="replayed", result=result)
            try:
                value = operation()
                if inspect.isawaitable(value):
                    value = await value
                result = value if isinstance(value, dict) else {
                    "status": "succeeded",
                    "message": "Operation completed.",
                }
            except Exception:
                result = _safe_failure()
            self._records[identity] = (payload_hash, result)
            return IdempotencyExecution(status="executed", result=result)


# Public port name used by capability/API adapters; production uses the SQL adapter.
IdempotencyStore = SqlIdempotencyStore

"""Transactional persistence for interactive Run lifecycle state."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.models.agent_run import AgentInvocation, AgentRun, RUN_STATUSES


class RunStoreError(RuntimeError):
    """Base error for Run persistence operations."""


class RunNotFound(RunStoreError):
    """The requested Run does not exist or is outside the requested scope."""


class RunConflict(RunStoreError):
    """A run id was reused with different immutable identity fields."""


class InvalidRunTransition(RunStoreError):
    """A requested status transition is not allowed by the Run state machine."""


_TRANSITIONS: dict[str, frozenset[str]] = {
    "queued": frozenset({"running", "cancelled", "abandoned", "failed"}),
    "running": frozenset(
        {"succeeded", "failed", "cancelled", "paused", "abandoned"}
    ),
    "paused": frozenset({"running", "cancelled", "abandoned"}),
    "succeeded": frozenset(),
    "failed": frozenset(),
    "cancelled": frozenset(),
    "abandoned": frozenset(),
}
_TERMINAL = frozenset({"succeeded", "failed", "cancelled", "abandoned"})


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class RunStore:
    """SQLModel-backed Run store with explicit transition validation."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        run: AgentRun | None = None,
        **fields: Any,
    ) -> AgentRun:
        if run is None:
            run = AgentRun(**fields)
        elif fields:
            raise TypeError("provide either an AgentRun or create fields, not both")
        if run.status == "running" and run.started_at is None:
            run.started_at = _utc_now()
        if run.status in _TERMINAL and run.finished_at is None:
            run.finished_at = _utc_now()

        existing = await self._session.get(AgentRun, run.run_id)
        if existing is not None:
            immutable = (
                existing.user_id,
                existing.thread_id,
                existing.goal_hash,
                existing.model,
            )
            requested = (
                run.user_id,
                run.thread_id,
                run.goal_hash,
                run.model,
            )
            if immutable != requested:
                raise RunConflict(f"run id already exists with different identity: {run.run_id}")
            return existing.model_copy(deep=True)

        try:
            self._session.add(run)
            await self._session.commit()
            await self._session.refresh(run)
            return run.model_copy(deep=True)
        except Exception:
            await self._session.rollback()
            raise

    async def get(self, run_id: str, *, user_id: int | None = None) -> AgentRun | None:
        run = await self._session.get(AgentRun, run_id)
        if run is None:
            return None
        if user_id is not None and run.user_id != user_id:
            return None
        return run.model_copy(deep=True)

    async def transition(
        self,
        run_id: str,
        status: str,
        *,
        error_code: str | None = None,
    ) -> AgentRun:
        if status not in RUN_STATUSES:
            raise InvalidRunTransition(f"unknown Run status: {status}")
        run = await self._session.get(AgentRun, run_id)
        if run is None:
            raise RunNotFound(run_id)
        if status not in _TRANSITIONS[run.status]:
            raise InvalidRunTransition(
                f"cannot transition Run {run_id} from {run.status} to {status}"
            )

        now = _utc_now()
        run.status = status
        if status == "running" and run.started_at is None:
            run.started_at = now
        if status in _TERMINAL:
            run.finished_at = now
        if error_code is not None:
            run.error_code = error_code
        self._session.add(run)
        try:
            await self._session.commit()
            await self._session.refresh(run)
            return run.model_copy(deep=True)
        except Exception:
            await self._session.rollback()
            raise

    async def create_invocation(
        self,
        *,
        run_id: str,
        invocation_id: str,
        sequence: int,
        capability: str,
        capability_version: str = "v1",
        input_payload: dict[str, Any] | None = None,
        idempotency_key: str | None = None,
    ) -> AgentInvocation:
        existing = await self._session.get(AgentInvocation, invocation_id)
        input_hash = hashlib.sha256(
            json.dumps(
                input_payload or {},
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()
        if existing is not None:
            self._ensure_invocation_same(
                existing,
                run_id=run_id,
                sequence=sequence,
                capability=capability,
                capability_version=capability_version,
                input_hash=input_hash,
                idempotency_key=idempotency_key,
            )
            return existing.model_copy(deep=True)
        if idempotency_key is not None:
            existing_key = (
                await self._session.execute(
                    select(AgentInvocation).where(
                        AgentInvocation.run_id == run_id,
                        AgentInvocation.idempotency_key == idempotency_key,
                    )
                )
            ).scalars().one_or_none()
            if existing_key is not None:
                self._ensure_invocation_same(
                    existing_key,
                    run_id=run_id,
                    sequence=existing_key.sequence,
                    capability=capability,
                    capability_version=capability_version,
                    input_hash=input_hash,
                    idempotency_key=idempotency_key,
                )
                return existing_key.model_copy(deep=True)
        existing_sequence = (
            await self._session.execute(
                select(AgentInvocation).where(
                    AgentInvocation.run_id == run_id,
                    AgentInvocation.sequence == sequence,
                )
            )
        ).scalars().one_or_none()
        if existing_sequence is not None:
            self._ensure_invocation_same(
                existing_sequence,
                run_id=run_id,
                sequence=sequence,
                capability=capability,
                capability_version=capability_version,
                input_hash=input_hash,
                idempotency_key=idempotency_key,
            )
            return existing_sequence.model_copy(deep=True)
        now = _utc_now()
        invocation = AgentInvocation(
            invocation_id=invocation_id,
            run_id=run_id,
            sequence=sequence,
            capability=capability,
            capability_version=capability_version,
            status="running",
            input_hash=input_hash,
            idempotency_key=idempotency_key,
            started_at=now,
        )
        self._session.add(invocation)
        try:
            await self._session.commit()
            await self._session.refresh(invocation)
            return invocation.model_copy(deep=True)
        except IntegrityError:
            await self._session.rollback()
            existing = await self._session.get(AgentInvocation, invocation_id)
            if existing is not None:
                self._ensure_invocation_same(
                    existing,
                    run_id=run_id,
                    sequence=sequence,
                    capability=capability,
                    capability_version=capability_version,
                    input_hash=input_hash,
                    idempotency_key=idempotency_key,
                )
                return existing.model_copy(deep=True)
            raise RunConflict(
                f"invocation uniqueness conflict for Run {run_id} sequence {sequence}"
            )
        except Exception:
            await self._session.rollback()
            raise

    @staticmethod
    def _ensure_invocation_same(
        existing: AgentInvocation,
        *,
        run_id: str,
        sequence: int,
        capability: str,
        capability_version: str,
        input_hash: str,
        idempotency_key: str | None,
    ) -> None:
        if (
            existing.run_id != run_id
            or existing.sequence != sequence
            or existing.capability != capability
            or existing.capability_version != capability_version
            or existing.input_hash != input_hash
            or existing.idempotency_key != idempotency_key
        ):
            raise RunConflict(
                "invocation identity or idempotency key conflicts with existing content"
            )

    async def finish_invocation(
        self,
        invocation_id: str,
        status: str,
        *,
        error_code: str | None = None,
    ) -> AgentInvocation:
        invocation = await self._session.get(AgentInvocation, invocation_id)
        if invocation is None:
            raise RunNotFound(invocation_id)
        if status not in {
            "succeeded",
            "failed",
            "denied",
            "cancelled",
            "timed_out",
        }:
            raise InvalidRunTransition(f"unknown invocation status: {status}")
        invocation.status = status
        invocation.finished_at = _utc_now()
        if error_code is not None:
            invocation.error_code = error_code
        self._session.add(invocation)
        try:
            await self._session.commit()
            await self._session.refresh(invocation)
            return invocation.model_copy(deep=True)
        except Exception:
            await self._session.rollback()
            raise

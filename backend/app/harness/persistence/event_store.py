"""Append-only, idempotent persistence for versioned Run events."""

from __future__ import annotations

import hashlib
import json
import math
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.harness.contracts import RunEvent
from app.models.agent_run import AgentRunEvent


_SENSITIVE_KEYS = {
    "api_key",
    "apikey",
    "authorization",
    "credential",
    "credentials",
    "password",
    "secret",
    "token",
}
_MAX_PAYLOAD_BYTES = 64 * 1024


class EventStoreError(RuntimeError):
    """Base error for append-only Event persistence."""


class EventConflict(EventStoreError):
    """An event id or run sequence was reused with different content."""


class EventPayloadError(EventStoreError, ValueError):
    """Payload is not safe JSON or exceeds the bounded event size."""


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _safe_value(value: Any, *, key: str = "", depth: int = 0) -> Any:
    if depth > 8:
        raise EventPayloadError("event payload nesting is too deep")
    if key.lower().replace("-", "_") in _SENSITIVE_KEYS:
        return "[REDACTED]"
    if value is None or isinstance(value, (str, int, bool)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise EventPayloadError("event payload contains a non-finite number")
        return value
    if isinstance(value, dict):
        return {
            str(child_key): _safe_value(
                child_value,
                key=str(child_key),
                depth=depth + 1,
            )
            for child_key, child_value in value.items()
        }
    if isinstance(value, list):
        return [
            _safe_value(child, depth=depth + 1)
            for child in value
        ]
    raise EventPayloadError(f"event payload contains unsupported value: {type(value).__name__}")


def _safe_payload_json(payload: dict[str, Any], max_bytes: int) -> str:
    if not isinstance(payload, dict):
        raise EventPayloadError("event payload must be a JSON object")
    safe = _safe_value(payload)
    encoded = json.dumps(
        safe,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
    if len(encoded.encode("utf-8")) > max_bytes:
        raise EventPayloadError("event payload exceeds the configured size limit")
    return encoded


def _event_id(
    run_id: str,
    sequence: int,
    event_type: str,
    invocation_id: str | None,
    payload_json: str,
) -> str:
    digest = hashlib.sha256(
        "|".join(
            [run_id, str(sequence), event_type, invocation_id or "", payload_json]
        ).encode("utf-8")
    ).hexdigest()[:32]
    return f"evt-{digest}"


class EventStore:
    """SQLModel-backed append-only Run event store."""

    def __init__(
        self,
        session: AsyncSession,
        *,
        max_payload_bytes: int = _MAX_PAYLOAD_BYTES,
    ) -> None:
        if max_payload_bytes < 1:
            raise ValueError("max_payload_bytes must be positive")
        self._session = session
        self._max_payload_bytes = max_payload_bytes

    async def append(
        self,
        event: RunEvent | AgentRunEvent,
        *,
        event_id: str | None = None,
    ) -> AgentRunEvent:
        if isinstance(event, RunEvent):
            run_id = event.run_id
            sequence = event.sequence
            event_type = event.event_type
            invocation_id = event.invocation_id
            payload = event.payload
            occurred_at = _utc_now()
            payload_json = _safe_payload_json(payload, self._max_payload_bytes)
            resolved_event_id = event_id or _event_id(
                run_id,
                sequence,
                event_type,
                invocation_id,
                payload_json,
            )
        elif isinstance(event, AgentRunEvent):
            run_id = event.run_id
            sequence = event.sequence
            event_type = event.event_type
            invocation_id = event.invocation_id
            try:
                payload = json.loads(event.payload_json or "{}")
            except json.JSONDecodeError as exc:
                raise EventPayloadError("event payload is not valid JSON") from exc
            payload_json = _safe_payload_json(payload, self._max_payload_bytes)
            resolved_event_id = event_id or event.event_id
            occurred_at = event.occurred_at
        else:
            raise TypeError("event must be RunEvent or AgentRunEvent")

        existing = await self._get_by_id(resolved_event_id)
        if existing is not None:
            self._ensure_same(existing, run_id, sequence, event_type, invocation_id, payload_json)
            return existing
        existing_sequence = await self._get_by_sequence(run_id, sequence)
        if existing_sequence is not None:
            self._ensure_same(
                existing_sequence,
                run_id,
                sequence,
                event_type,
                invocation_id,
                payload_json,
            )
            return existing_sequence

        stored = AgentRunEvent(
            event_id=resolved_event_id,
            run_id=run_id,
            sequence=sequence,
            event_type=event_type,
            invocation_id=invocation_id,
            payload_json=payload_json,
            occurred_at=occurred_at,
        )
        self._session.add(stored)
        try:
            await self._session.commit()
            await self._session.refresh(stored)
            return stored
        except IntegrityError:
            await self._session.rollback()
            existing = await self._get_by_id(resolved_event_id)
            if existing is None:
                existing = await self._get_by_sequence(run_id, sequence)
            if existing is None:
                raise
            self._ensure_same(
                existing,
                run_id,
                sequence,
                event_type,
                invocation_id,
                payload_json,
            )
            return existing
        except Exception:
            await self._session.rollback()
            raise

    async def list_after(
        self,
        run_id: str,
        after_sequence: int = 0,
        *,
        limit: int = 500,
    ) -> list[AgentRunEvent]:
        bounded_limit = max(1, min(limit, 1000))
        statement = (
            select(AgentRunEvent)
            .where(
                AgentRunEvent.run_id == run_id,
                AgentRunEvent.sequence > after_sequence,
            )
            .order_by(AgentRunEvent.sequence)
            .limit(bounded_limit)
        )
        return list((await self._session.execute(statement)).scalars().all())

    async def _get_by_id(self, event_id: str) -> AgentRunEvent | None:
        return await self._session.get(AgentRunEvent, event_id)

    async def _get_by_sequence(self, run_id: str, sequence: int) -> AgentRunEvent | None:
        statement = select(AgentRunEvent).where(
            AgentRunEvent.run_id == run_id,
            AgentRunEvent.sequence == sequence,
        )
        return (await self._session.execute(statement)).scalars().one_or_none()

    @staticmethod
    def _ensure_same(
        existing: AgentRunEvent,
        run_id: str,
        sequence: int,
        event_type: str,
        invocation_id: str | None,
        payload_json: str,
    ) -> None:
        if (
            existing.run_id != run_id
            or existing.sequence != sequence
            or existing.event_type != event_type
            or existing.invocation_id != invocation_id
            or existing.payload_json != payload_json
        ):
            raise EventConflict(
                f"event identity conflict for run {run_id} sequence {sequence}"
            )

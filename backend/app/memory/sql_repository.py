"""SQL-backed memory repository — MEMORY-002.

Persists typed memory records in the ``agent_memory`` table via
SQLModel/SQLAlchemy async sessions.

Implements ``MemoryRepository`` without leaking the session to the
service layer.
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
from typing import Any, cast

from sqlalchemy import and_, or_
from sqlmodel import select, func, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.memory.interfaces import MemoryRepository
from app.models.agent_memory import AgentMemory
from app.models.user import User
from app.core.logging import get_logger

logger = get_logger(__name__)

_LONG_TERM_KINDS = ("semantic", "profile")

_MEMORY_USER_ID = cast(Any, AgentMemory.user_id)
_MEMORY_KIND = cast(Any, AgentMemory.kind)
_MEMORY_THREAD_ID = cast(Any, AgentMemory.thread_id)
_MEMORY_FACT_ID = cast(Any, AgentMemory.fact_id)
_MEMORY_CREATED_AT = cast(Any, AgentMemory.created_at)
_MEMORY_ID = cast(Any, AgentMemory.id)
_USER_ID = cast(Any, User.id)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _require_user_id(user_id: int | None) -> int:
    if user_id is None or user_id <= 0:
        raise ValueError("user_id must be a positive integer")
    return user_id


class SqlMemoryRepository(MemoryRepository):
    """Persists memory facts in the ``agent_memory`` SQL table.

    Each call requires an ``AsyncSession`` (passed at construction or
    per-operation) to remain compatible with FastAPI dependency injection.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # ------------------------------------------------------------------
    # MemoryRepository interface
    # ------------------------------------------------------------------

    async def put_fact(
        self,
        thread_id: str,
        fact_id: str,
        content: str,
        importance: float,
        source: str,
        user_id: int | None = None,
        kind: str = "episodic",
        metadata: dict[str, Any] | None = None,
    ) -> None:
        owner_id = _require_user_id(user_id)
        record = AgentMemory(
            fact_id=fact_id,
            user_id=owner_id,
            thread_id=thread_id,
            kind=kind,
            content=content,
            importance=importance,
            source=source,
            created_at=_utc_now(),
            metadata_json=json.dumps(
                metadata or {},
                ensure_ascii=False,
                allow_nan=False,
                sort_keys=True,
            ),
        )
        self._session.add(record)
        await self._session.flush()

    async def get_facts(
        self,
        thread_id: str,
        user_id: int | None = None,
        kind: str | None = None,
        offset: int = 0,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        owner_id = _require_user_id(user_id)
        if offset < 0:
            raise ValueError("offset must be non-negative")
        if limit <= 0 or limit > 1000:
            raise ValueError("limit must be between 1 and 1000")
        stmt = select(AgentMemory).where(_MEMORY_USER_ID == owner_id)
        stmt = self._apply_scope(stmt, thread_id, kind)
        stmt = stmt.order_by(_MEMORY_CREATED_AT, _MEMORY_ID).offset(offset).limit(limit)

        result = await self._session.execute(stmt)
        rows = result.scalars().all()

        return [self._row_to_dict(r) for r in rows]

    async def delete_fact(
        self,
        thread_id: str,
        fact_id: str,
        user_id: int | None = None,
        kind: str | None = None,
    ) -> bool:
        """Delete an owned fact by its stable external identifier."""
        owner_id = _require_user_id(user_id)
        stmt = (
            delete(AgentMemory)
            .where(_MEMORY_FACT_ID == fact_id)
            .where(_MEMORY_USER_ID == owner_id)
        )
        if kind is not None:
            stmt = stmt.where(_MEMORY_KIND == kind)
        if kind not in _LONG_TERM_KINDS:
            stmt = stmt.where(_MEMORY_THREAD_ID == thread_id)
        result: Any = await self._session.execute(stmt)
        await self._session.flush()
        if result.rowcount:
            logger.info(
                "memory_fact_deleted",
                extra={"fact_id": fact_id, "thread_id": thread_id},
            )
        return bool(result.rowcount)

    async def count_facts(
        self,
        thread_id: str,
        user_id: int | None = None,
        kind: str | None = None,
    ) -> int:
        owner_id = _require_user_id(user_id)
        stmt = (
            select(func.count())
            .select_from(AgentMemory)
            .where(_MEMORY_USER_ID == owner_id)
        )
        stmt = self._apply_scope(stmt, thread_id, kind)

        result = await self._session.execute(stmt)
        return result.scalar_one()

    async def lock_owner(self, user_id: int) -> None:
        owner_id = _require_user_id(user_id)
        await self._session.execute(
            select(_USER_ID).where(_USER_ID == owner_id).with_for_update()
        )

    async def commit(self) -> None:
        await self._session.commit()

    async def rollback(self) -> None:
        await self._session.rollback()

    # -- public helpers --------------------------------------------------

    async def clear_user_memory(
        self,
        user_id: int,
        kind: str | None = None,
    ) -> int:
        """Delete all memory for a user (optionally filtered by kind).

        Returns the number of deleted rows.
        """
        owner_id = _require_user_id(user_id)
        stmt = delete(AgentMemory).where(_MEMORY_USER_ID == owner_id)
        if kind is not None:
            stmt = stmt.where(_MEMORY_KIND == kind)
        result: Any = await self._session.execute(stmt)
        await self._session.commit()
        return result.rowcount or 0

    async def clear_thread_memory(self, thread_id: str, user_id: int) -> int:
        """Delete all memory for a specific thread.

        Returns the number of deleted rows.
        """
        owner_id = _require_user_id(user_id)
        stmt = (
            delete(AgentMemory)
            .where(_MEMORY_THREAD_ID == thread_id)
            .where(_MEMORY_USER_ID == owner_id)
        )
        result: Any = await self._session.execute(stmt)
        await self._session.commit()
        return result.rowcount or 0

    # -- internal helpers -------------------------------------------------

    @staticmethod
    def _apply_scope(stmt, thread_id: str, kind: str | None):
        """Apply episodic thread scope or long-term owner scope."""
        if kind == "episodic":
            return stmt.where(
                _MEMORY_KIND == kind,
                _MEMORY_THREAD_ID == thread_id,
            )
        if kind in _LONG_TERM_KINDS:
            return stmt.where(_MEMORY_KIND == kind)
        if kind is not None:
            return stmt.where(
                _MEMORY_KIND == kind,
                _MEMORY_THREAD_ID == thread_id,
            )
        return stmt.where(
            or_(
                and_(
                    _MEMORY_KIND == "episodic",
                    _MEMORY_THREAD_ID == thread_id,
                ),
                _MEMORY_KIND.in_(_LONG_TERM_KINDS),
            )
        )

    @staticmethod
    def _row_to_dict(row: AgentMemory) -> dict[str, Any]:
        metadata = json.loads(row.metadata_json) if row.metadata_json else {}
        provenance = metadata.get("provenance")
        if not isinstance(provenance, dict):
            provenance = {}
        return {
            "id": row.fact_id,
            "user_id": row.user_id,
            "thread_id": row.thread_id,
            "kind": row.kind,
            "content": row.content,
            "importance": row.importance,
            "source": row.source,
            "timestamp": row.created_at.isoformat() if row.created_at else "",
            "metadata": metadata,
            "source_type": provenance.get("source_type", "legacy"),
            "source_id": provenance.get("source_id"),
            "confidence": provenance.get("confidence", 0.5),
            "verified": bool(provenance.get("verified", False)),
            "expires_at": provenance.get("expires_at"),
        }

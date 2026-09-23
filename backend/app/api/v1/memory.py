"""User memory management endpoints for MEMORY-002.

Provides authenticated deletion of user memory records with optional
kind filtering.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.database import get_session
from app.schemas.user import UserRead
from app.memory.sql_repository import SqlMemoryRepository
from app.memory.types import MemoryKind
from app.core.logging import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/memory", tags=["Memory"])


@router.delete("")
async def delete_user_memory(
    kind: MemoryKind | None = None,
    user: UserRead = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
):
    """Delete the authenticated user's memory records.

    Optionally filter by ``kind`` (episodic / semantic / profile).
    Returns the number of deleted records.
    """
    repository = SqlMemoryRepository(db)
    deleted = await repository.clear_user_memory(
        user.id,
        kind=kind.value if kind is not None else None,
    )
    logger.info(
        "user_memory_deleted",
        extra={
            "user_id": user.id,
            "kind": kind.value if kind is not None else None,
            "deleted_count": deleted,
        },
    )
    return {
        "status": "ok",
        "user_id": user.id,
        "kind": kind.value if kind is not None else None,
        "deleted": deleted,
    }

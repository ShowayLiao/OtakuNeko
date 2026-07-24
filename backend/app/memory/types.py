"""Typed memory records for MEMORY-002.

Defines ``MemoryKind`` (episodic, semantic, profile) and ``MemoryRecord``
as a validated dataclass that carries user, thread, kind, content, and
metadata fields.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any


class MemoryKind(StrEnum):
    """Categorisation of memory records.

    - ``episodic``: user events and interactions (e.g. "watched anime X").
    - ``semantic``: extracted preferences and facts.
    - ``profile``: stable user model (e.g. favourite genres).
    """

    EPISODIC = "episodic"
    SEMANTIC = "semantic"
    PROFILE = "profile"


_DEFAULT_IMPORTANCE_RANGE = (0.0, 1.0)


def _validate_importance(value: float) -> float:
    if not _DEFAULT_IMPORTANCE_RANGE[0] <= value <= _DEFAULT_IMPORTANCE_RANGE[1]:
        raise ValueError(
            f"importance must be in [{_DEFAULT_IMPORTANCE_RANGE[0]}, "
            f"{_DEFAULT_IMPORTANCE_RANGE[1]}], got {value}"
        )
    return value


def _validate_kind(value: str) -> MemoryKind:
    try:
        return MemoryKind(value)
    except ValueError:
        raise ValueError(
            f"invalid MemoryKind '{value}'; expected one of "
            f"{[k.value for k in MemoryKind]}"
        )


@dataclass
class MemoryRecord:
    """A single memory record with typed metadata.

    ``id`` is assigned by the repository on creation.  ``user_id`` is the
    owning user (required).  ``thread_id`` is optional — episodic records
    always have a thread; semantic and profile records may omit it.
    """

    user_id: int
    content: str
    id: int | None = None
    thread_id: str | None = None
    kind: MemoryKind = MemoryKind.EPISODIC
    importance: float = 0.5
    source: str = "conversation"
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.user_id <= 0:
            raise ValueError("user_id must be a positive integer")
        self.importance = _validate_importance(self.importance)
        if isinstance(self.kind, str):
            self.kind = _validate_kind(self.kind)
        if self.kind is MemoryKind.EPISODIC and not self.thread_id:
            raise ValueError("thread_id is required for episodic memory")

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-compatible dict."""
        return {
            "id": self.id,
            "user_id": self.user_id,
            "thread_id": self.thread_id,
            "kind": self.kind.value,
            "content": self.content,
            "importance": self.importance,
            "source": self.source,
            "created_at": self.created_at.isoformat(),
            "metadata": self.metadata,
        }

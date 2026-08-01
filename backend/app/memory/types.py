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


class MemorySourceType(StrEnum):
    """Trust-bearing origin of a memory value."""

    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"
    EXTERNAL = "external"
    SYSTEM = "system"
    LEGACY = "legacy"


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


def _validate_confidence(value: float) -> float:
    value = float(value)
    if not 0.0 <= value <= 1.0:
        raise ValueError(f"confidence must be in [0.0, 1.0], got {value}")
    return value


def _parse_datetime(value: Any) -> datetime | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        parsed = value
    else:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


@dataclass
class MemoryFact:
    """A memory fact with explicit provenance and trust semantics."""

    content: str
    source_type: MemorySourceType = MemorySourceType.LEGACY
    source_id: str | None = None
    confidence: float = 0.5
    verified: bool = False
    expires_at: datetime | None = None
    id: str | int | None = None
    user_id: int | None = None
    thread_id: str | None = None
    kind: MemoryKind = MemoryKind.SEMANTIC
    importance: float = 0.5
    source: str = "conversation"
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if isinstance(self.source_type, str):
            try:
                self.source_type = MemorySourceType(self.source_type)
            except ValueError:
                self.source_type = MemorySourceType.LEGACY
        self.confidence = _validate_confidence(self.confidence)
        self.importance = _validate_importance(float(self.importance))
        if isinstance(self.kind, str):
            self.kind = _validate_kind(self.kind)
        self.expires_at = _parse_datetime(self.expires_at)
        self.created_at = _parse_datetime(self.created_at) or datetime.now(timezone.utc)
        if self.source_type in {
            MemorySourceType.TOOL,
            MemorySourceType.EXTERNAL,
            MemorySourceType.LEGACY,
        }:
            self.verified = False

    @property
    def trusted(self) -> bool:
        """Whether the fact may be used as high-trust profile context."""
        return (
            self.verified
            and self.confidence >= 0.8
            and self.source_type in {
                MemorySourceType.USER,
                MemorySourceType.SYSTEM,
            }
            and not self.is_expired()
        )

    def is_expired(self, now: datetime | None = None) -> bool:
        if self.expires_at is None:
            return False
        current = now or datetime.now(timezone.utc)
        if current.tzinfo is None:
            current = current.replace(tzinfo=timezone.utc)
        return self.expires_at <= current

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "MemoryFact":
        """Map new metadata and old rows to a safe typed fact."""
        metadata = dict(value.get("metadata") or {})
        provenance = metadata.get("provenance")
        if not isinstance(provenance, dict):
            provenance = {}
        source_type = value.get("source_type", provenance.get("source_type"))
        if source_type is None:
            source_type = MemorySourceType.LEGACY
        source_id = value.get("source_id", provenance.get("source_id"))
        confidence = value.get("confidence", provenance.get("confidence", 0.5))
        verified = value.get("verified", provenance.get("verified", False))
        expires_at = value.get("expires_at", provenance.get("expires_at"))
        kind = value.get("kind", MemoryKind.SEMANTIC)
        if kind == MemoryKind.EPISODIC and not value.get("thread_id"):
            kind = MemoryKind.SEMANTIC
        return cls(
            content=str(value.get("content", "")),
            source_type=source_type,
            source_id=str(source_id) if source_id is not None else None,
            confidence=confidence,
            verified=bool(verified),
            expires_at=expires_at,
            id=value.get("id"),
            user_id=value.get("user_id"),
            thread_id=value.get("thread_id"),
            kind=kind,
            importance=value.get("importance", 0.5),
            source=value.get("source", "conversation"),
            created_at=value.get("created_at", value.get("timestamp")),
            metadata=metadata,
        )

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-compatible representation with provenance."""
        metadata = dict(self.metadata)
        metadata["provenance"] = {
            "source_type": self.source_type.value,
            "source_id": self.source_id,
            "confidence": self.confidence,
            "verified": self.verified,
            "expires_at": (
                self.expires_at.isoformat() if self.expires_at else None
            ),
        }
        return {
            "id": self.id,
            "user_id": self.user_id,
            "thread_id": self.thread_id,
            "kind": self.kind.value,
            "content": self.content,
            "importance": self.importance,
            "source": self.source,
            "source_type": self.source_type.value,
            "source_id": self.source_id,
            "confidence": self.confidence,
            "verified": self.verified,
            "expires_at": (
                self.expires_at.isoformat() if self.expires_at else None
            ),
            "created_at": self.created_at.isoformat(),
            "metadata": metadata,
        }


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
    source_type: MemorySourceType = MemorySourceType.LEGACY
    source_id: str | None = None
    confidence: float = 0.5
    verified: bool = False
    expires_at: datetime | None = None

    def __post_init__(self) -> None:
        if self.user_id <= 0:
            raise ValueError("user_id must be a positive integer")
        self.importance = _validate_importance(self.importance)
        if isinstance(self.kind, str):
            self.kind = _validate_kind(self.kind)
        if self.kind is MemoryKind.EPISODIC and not self.thread_id:
            raise ValueError("thread_id is required for episodic memory")
        if isinstance(self.source_type, str):
            try:
                self.source_type = MemorySourceType(self.source_type)
            except ValueError:
                self.source_type = MemorySourceType.LEGACY
        self.confidence = _validate_confidence(self.confidence)
        self.expires_at = _parse_datetime(self.expires_at)
        if self.source_type in {
            MemorySourceType.TOOL,
            MemorySourceType.EXTERNAL,
            MemorySourceType.LEGACY,
        }:
            self.verified = False

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
            "source_type": self.source_type.value,
            "source_id": self.source_id,
            "confidence": self.confidence,
            "verified": self.verified,
            "expires_at": (
                self.expires_at.isoformat() if self.expires_at else None
            ),
            "created_at": self.created_at.isoformat(),
            "metadata": self.metadata,
        }

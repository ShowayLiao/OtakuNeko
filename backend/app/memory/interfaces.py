"""Memory architecture interfaces.

Defines the contracts for the MemoryService, MemoryRepository, and
MemoryExtractor layers. The existing MemoryManager satisfies these
interfaces without modification — this is an additive abstraction.

MEMORY-002 extends signatures with ``user_id`` and ``kind`` parameters
while keeping backward-compatible defaults.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class MemoryContext:
    """Result of a memory retrieval operation."""

    short_term_messages: list[dict[str, Any]] = field(default_factory=list)
    long_term_facts: list[dict[str, Any]] = field(default_factory=list)
    summary: str = ""


class MemoryRepository(ABC):
    """Persistence access for facts and memory data.

    Agents and services depend on this abstraction — never on
    concrete storage backends (LangGraph Store, database, etc.).
    """

    @abstractmethod
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
        """Store or update a single fact."""

    @abstractmethod
    async def get_facts(
        self,
        thread_id: str,
        user_id: int | None = None,
        kind: str | None = None,
        offset: int = 0,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """Retrieve facts for a thread, optionally filtered by user and kind."""

    @abstractmethod
    async def delete_fact(
        self,
        thread_id: str,
        fact_id: str,
        user_id: int | None = None,
        kind: str | None = None,
    ) -> bool:
        """Remove an owned fact, returning whether a row was deleted."""

    @abstractmethod
    async def count_facts(
        self,
        thread_id: str,
        user_id: int | None = None,
        kind: str | None = None,
    ) -> int:
        """Return the number of facts stored for a thread."""

    async def lock_owner(self, user_id: int) -> None:
        """Serialize durable writes for one owner when supported."""

    async def commit(self) -> None:
        """Commit a repository unit of work when supported."""

    async def rollback(self) -> None:
        """Roll back a repository unit of work when supported."""


class MemoryExtractor(ABC):
    """Fact extraction from conversation data.

    Implementations may use LLMs, heuristics, or any other method
    to produce structured facts from raw messages.
    """

    @abstractmethod
    async def extract(self, messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Extract facts from a list of conversation messages.

        Returns a list of fact dicts, each with at least:
        ``{"content": str, "importance": float}``.
        """


class MemoryService(ABC):
    """Stable interface for memory operations.

    Agents depend on this abstraction to store, retrieve, and
    search across conversation memory. Concrete implementations
    coordinate the repository and extractor layers.
    """

    @abstractmethod
    async def store_fact(
        self,
        thread_id: str,
        content: str,
        importance: float = 0.5,
        source: str = "conversation",
        user_id: int | None = None,
        kind: str = "episodic",
    ) -> str | None:
        """Persist a single fact. Returns fact_id or None if duplicate."""

    @abstractmethod
    async def retrieve_context(
        self,
        thread_id: str,
        query: str,
        top_k: int = 5,
        user_id: int | None = None,
        kind: str | None = None,
    ) -> MemoryContext:
        """Retrieve relevant memory context for the current query."""

    @abstractmethod
    async def extract_and_store_facts(self, thread_id: str, user_id: int | None = None) -> int:
        """Extract facts from recent conversation and persist them.

        Returns the number of new facts stored.
        """

    @abstractmethod
    async def search_facts(
        self,
        thread_id: str,
        query: str,
        top_k: int = 10,
        user_id: int | None = None,
        kind: str | None = None,
    ) -> list[dict[str, Any]]:
        """Semantic search across stored facts."""

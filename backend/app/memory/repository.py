"""Memory repository backed by a LangGraph Store.

Encapsulates raw Store access so the service layer never touches
storage APIs directly. The store can be InMemoryStore (dev) or
AsyncPostgresStore (prod) — this repository works with both.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.memory.interfaces import MemoryRepository
from app.core.logging import get_logger

logger = get_logger(__name__)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class StoreMemoryRepository(MemoryRepository):
    """Persists facts through a LangGraph-compatible BaseStore.

    The store is expected to support ``aput``, ``asearch``, and
    ``adelete`` with the standard (namespace, key, value) signature.
    """

    def __init__(self, store: Any) -> None:
        self._store = store

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
        namespace = self._namespace(thread_id, user_id, kind)
        value = {
            "content": content,
            "importance": importance,
            "source": source,
            "thread_id": thread_id,
            "timestamp": _utc_now_iso(),
            "user_id": user_id,
            "kind": kind,
            "metadata": metadata or {},
        }
        await self._store.aput(namespace, fact_id, value)

    async def get_facts(
        self,
        thread_id: str,
        user_id: int | None = None,
        kind: str | None = None,
        offset: int = 0,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        kinds = [kind] if kind is not None else ["episodic", "semantic", "profile"]
        items = []
        for memory_kind in kinds:
            items.extend(
                await self._store.asearch(
                    self._namespace(thread_id, user_id, memory_kind)
                )
            )
        facts: list[dict[str, Any]] = []
        for item in items:
            val = item.value
            facts.append(
                {
                    "id": item.key,
                    "content": val.get("content", ""),
                    "importance": val.get("importance", 0.5),
                    "timestamp": val.get("timestamp", ""),
                    "source": val.get("source", "conversation"),
                    "thread_id": val.get("thread_id"),
                    "embedding": val.get("embedding", []),
                    "user_id": val.get("user_id"),
                    "kind": val.get("kind", "episodic"),
                    "metadata": val.get("metadata", {}),
                }
            )
        facts.sort(key=lambda fact: (fact["timestamp"], fact["id"]))
        return facts[offset : offset + limit]

    async def delete_fact(
        self,
        thread_id: str,
        fact_id: str,
        user_id: int | None = None,
        kind: str | None = None,
    ) -> bool:
        memory_kind = kind or "episodic"
        await self._store.adelete(
            self._namespace(thread_id, user_id, memory_kind), fact_id
        )
        return True

    async def count_facts(
        self,
        thread_id: str,
        user_id: int | None = None,
        kind: str | None = None,
    ) -> int:
        return len(
            await self.get_facts(thread_id, user_id=user_id, kind=kind, limit=1000)
        )

    @staticmethod
    def _namespace(
        thread_id: str,
        user_id: int | None,
        kind: str,
    ) -> tuple[str, str, str, str]:
        scope = thread_id if kind == "episodic" else "__user__"
        return ("facts", str(user_id or 0), kind, scope)

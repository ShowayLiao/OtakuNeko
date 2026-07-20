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
    ) -> None:
        namespace = ("facts", thread_id)
        value = {
            "content": content,
            "importance": importance,
            "source": source,
            "timestamp": _utc_now_iso(),
        }
        await self._store.aput(namespace, fact_id, value)

    async def get_facts(self, thread_id: str) -> list[dict[str, Any]]:
        items = await self._store.asearch(("facts", thread_id))
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
                    "embedding": val.get("embedding", []),
                }
            )
        return facts

    async def delete_fact(self, thread_id: str, fact_id: str) -> None:
        await self._store.adelete(("facts", thread_id), fact_id)

    async def count_facts(self, thread_id: str) -> int:
        items = await self._store.asearch(("facts", thread_id))
        return sum(1 for _ in items)

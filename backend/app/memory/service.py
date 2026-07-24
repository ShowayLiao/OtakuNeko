"""Memory service implementation — MEMORY-002.

Coordinates the repository and extractor layers with kind-aware,
user-scoped store, retrieve, and retention operations.

Retention limits per kind:
- episodic: 1000
- semantic: 500
- profile: 50 (never evicted by other kinds' retention)
"""

from __future__ import annotations

import asyncio
import uuid
from typing import Any
from weakref import WeakKeyDictionary

from app.memory.interfaces import (
    MemoryContext,
    MemoryExtractor,
    MemoryRepository,
    MemoryService,
)
from app.memory.retrievers.bm25_retriever import BM25Retriever
from app.memory.retrievers.vector_retriever import VectorRetriever
from app.memory.retrievers.hybrid_retriever import HybridRetriever
from app.core.logging import get_logger

logger = get_logger(__name__)

# Per-kind capacity limits (MEMORY-002 Step 04).
_RETENTION_LIMITS: dict[str, int] = {
    "episodic": 1000,
    "semantic": 500,
    "profile": 50,
}

_DEFAULT_KIND = "episodic"
_LOCK_STRIPES = 64
_WRITE_LOCKS: WeakKeyDictionary[
    asyncio.AbstractEventLoop, list[asyncio.Lock]
] = WeakKeyDictionary()


def _write_lock(user_id: int | None, thread_id: str, kind: str) -> asyncio.Lock:
    loop = asyncio.get_running_loop()
    locks = _WRITE_LOCKS.get(loop)
    if locks is None:
        locks = [asyncio.Lock() for _ in range(_LOCK_STRIPES)]
        _WRITE_LOCKS[loop] = locks
    scope = thread_id if kind == "episodic" else "__user__"
    index = hash((user_id, scope, kind)) % _LOCK_STRIPES
    return locks[index]


class MemoryServiceImpl(MemoryService):
    """Memory service backed by a repository and extractor.

    Coordinates fact storage, retrieval, and extraction through
    the abstract repository and extractor layers. The hybrid
    retriever (BM25 + vector) is used for semantic search.
    """

    def __init__(
        self,
        repository: MemoryRepository,
        extractor: MemoryExtractor,
        api_key: str,
        base_url: str,
        checkpointer: Any = None,
        max_facts: int = 500,
        default_user_id: int | None = None,
    ) -> None:
        self._repo = repository
        self._extractor = extractor
        self.checkpointer = checkpointer
        self.max_facts = max_facts
        self.default_user_id = default_user_id

        self._bm25 = BM25Retriever()
        self._vector = VectorRetriever(api_key, base_url)
        self._hybrid = HybridRetriever(self._bm25, self._vector)

    # ------------------------------------------------------------------
    # MemoryService interface
    # ------------------------------------------------------------------

    async def store_fact(
        self,
        thread_id: str,
        content: str,
        importance: float = 0.5,
        source: str = "conversation",
        user_id: int | None = None,
        kind: str = "episodic",
    ) -> str | None:
        """Persist a fact after deduplication against existing facts.

        Deduplication and retention are scoped to the same user+kind+thread.
        """
        owner_id = user_id if user_id is not None else self.default_user_id
        async with _write_lock(owner_id, thread_id, kind):
            try:
                if owner_id is not None:
                    await self._repo.lock_owner(owner_id)
                existing = await self._repo.get_facts(
                    thread_id,
                    user_id=owner_id,
                    kind=kind,
                    limit=1000,
                )

                if existing:
                    all_contents = [f["content"] for f in existing] + [content]
                    vecs = await self._vector.embed(all_contents)
                    new_vec = vecs[-1]
                    for existing_vec in vecs[:-1]:
                        if (
                            VectorRetriever.cosine_similarity(
                                new_vec, existing_vec
                            )
                            > 0.9
                        ):
                            await self._repo.commit()
                            return None
                else:
                    await self._vector.embed([content])

                fact_id = str(uuid.uuid4())
                await self._repo.put_fact(
                    thread_id,
                    fact_id,
                    content,
                    importance,
                    source,
                    user_id=owner_id,
                    kind=kind,
                )

                # Profile changes only through explicit replacement/deletion.
                limit = min(
                    _RETENTION_LIMITS.get(kind, self.max_facts),
                    self.max_facts,
                )
                if kind != "profile" and len(existing) + 1 > limit:
                    facts_sorted = sorted(
                        existing,
                        key=lambda f: (
                            f.get("importance", 0),
                            f.get("timestamp", ""),
                            f.get("id", ""),
                        ),
                    )
                    overflow = len(existing) + 1 - limit
                    for old in facts_sorted[:overflow]:
                        await self._repo.delete_fact(
                            thread_id,
                            old["id"],
                            user_id=owner_id,
                            kind=kind,
                        )
                await self._repo.commit()
                return fact_id
            except BaseException:
                await self._repo.rollback()
                raise

    async def retrieve_context(
        self,
        thread_id: str,
        query: str,
        top_k: int = 5,
        user_id: int | None = None,
        kind: str | None = None,
    ) -> MemoryContext:
        """Retrieve short-term and long-term context for a query."""
        short: list[dict[str, Any]] = []
        completed_steps: list[str] = []
        terminal_output: str = ""

        if self.checkpointer:
            config = {
                "configurable": {"thread_id": thread_id, "checkpoint_ns": ""}
            }
            cp = await self.checkpointer.aget_tuple(config)
            if cp:
                short = self._messages_from_checkpoint(cp.checkpoint)
                channel_values = cp.checkpoint.get("channel_values", {})
                completed_steps = channel_values.get("completed_steps", [])
                terminal_output = channel_values.get("last_terminal_output", "")

        long_facts: list[dict[str, Any]] = []
        owner_id = user_id if user_id is not None else self.default_user_id
        all_facts = await self._repo.get_facts(
            thread_id, user_id=owner_id, kind=kind, limit=1000
        )
        if all_facts:
            long_facts = await self._hybrid.retrieve(
                query, all_facts, top_k=top_k
            )

        parts: list[str] = []
        if long_facts:
            parts.append("[长期记忆] 相关历史信息：")
            for f in long_facts:
                parts.append(f"- {f['content']}")
        if completed_steps:
            parts.append(
                f"[执行进度] 已完成步骤: {', '.join(completed_steps)}"
            )
        if terminal_output:
            parts.append(f"[终端输出] {terminal_output[:500]}")
        if short:
            parts.append("[近期对话]")
            for m in short[-6:]:
                role_label = "用户" if m["role"] in ("human", "user") else "AI"
                parts.append(f"- [{role_label}] {m['content'][:200]}")

        logger.info(
            "context_loaded",
            extra={
                "thread_id": thread_id,
                "short_msg_count": len(short),
                "fact_count": len(long_facts),
                "completed_steps": completed_steps,
                "has_terminal": bool(terminal_output),
            },
        )

        return MemoryContext(
            short_term_messages=short,
            long_term_facts=long_facts,
            summary="\n".join(parts) if parts else "",
        )

    async def extract_and_store_facts(
        self, thread_id: str, user_id: int | None = None
    ) -> int:
        """Extract facts from recent conversation and persist them.

        Returns the number of new facts stored.  Extraction failure
        returns 0 (does not fail the calling operation).
        """
        messages: list[dict[str, Any]] = []
        if self.checkpointer:
            config = {
                "configurable": {"thread_id": thread_id, "checkpoint_ns": ""}
            }
            cp = await self.checkpointer.aget_tuple(config)
            if cp:
                messages = self._messages_from_checkpoint(cp.checkpoint)[-20:]

        owner_id = user_id if user_id is not None else self.default_user_id
        if owner_id is None:
            return 0

        try:
            facts = await self._extractor.extract(messages)
        except Exception:
            logger.exception("extract_and_store_facts failed")
            return 0

        count = 0
        for fact in facts:
            content = fact.get("content", "")
            importance = float(fact.get("importance", 0.5))
            if content:
                fact_id = await self.store_fact(
                    thread_id, content, importance=importance,
                    user_id=owner_id,
                    kind="semantic",
                )
                if fact_id:
                    count += 1
        return count

    async def search_facts(
        self,
        thread_id: str,
        query: str,
        top_k: int = 10,
        user_id: int | None = None,
        kind: str | None = None,
    ) -> list[dict[str, Any]]:
        """Semantic search across stored facts using hybrid retrieval."""
        owner_id = user_id if user_id is not None else self.default_user_id
        all_facts = await self._repo.get_facts(
            thread_id, user_id=owner_id, kind=kind, limit=1000
        )
        if not all_facts:
            return []
        return await self._hybrid.retrieve(query, all_facts, top_k=top_k)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _messages_from_checkpoint(checkpoint: Any) -> list[dict[str, Any]]:
        messages: list[dict[str, Any]] = []
        channel_values = checkpoint.get("channel_values", {})
        raw = channel_values.get("messages", [])
        for m in raw:
            if hasattr(m, "type") and hasattr(m, "content"):
                messages.append({"role": m.type, "content": str(m.content)})
        return messages

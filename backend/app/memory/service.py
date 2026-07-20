"""Memory service implementation.

Wraps the existing MemoryManager through the new layered interfaces
(MemoryRepository + MemoryExtractor). Produces identical behavior
to the current MemoryManager while satisfying the MemoryService
contract.
"""

from __future__ import annotations

import uuid
from typing import Any

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
    ) -> None:
        self._repo = repository
        self._extractor = extractor
        self.checkpointer = checkpointer
        self.max_facts = max_facts

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
    ) -> str | None:
        """Persist a fact after deduplication against existing facts."""
        existing = await self._repo.get_facts(thread_id)

        if existing:
            all_contents = [f["content"] for f in existing] + [content]
            vecs = await self._vector.embed(all_contents)
            new_vec = vecs[-1]
            for i, existing_vec in enumerate(vecs[:-1]):
                if VectorRetriever.cosine_similarity(new_vec, existing_vec) > 0.9:
                    return None
        else:
            new_vec = (await self._vector.embed([content]))[0]

        fact_id = str(uuid.uuid4())
        await self._repo.put_fact(thread_id, fact_id, content, importance, source)

        overflow = len(existing) + 1 - self.max_facts
        if overflow > 0:
            facts_sorted = sorted(
                existing,
                key=lambda f: (f.get("importance", 0), f.get("timestamp", "")),
            )
            for old in facts_sorted[:overflow]:
                await self._repo.delete_fact(thread_id, old["id"])

        return fact_id

    async def retrieve_context(
        self,
        thread_id: str,
        query: str,
        top_k: int = 5,
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
        all_facts = await self._repo.get_facts(thread_id)
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

    async def extract_and_store_facts(self, thread_id: str) -> int:
        """Extract facts from recent conversation and persist them."""
        messages: list[dict[str, Any]] = []
        if self.checkpointer:
            config = {
                "configurable": {"thread_id": thread_id, "checkpoint_ns": ""}
            }
            cp = await self.checkpointer.aget_tuple(config)
            if cp:
                messages = self._messages_from_checkpoint(cp.checkpoint)[-20:]

        facts = await self._extractor.extract(messages)

        count = 0
        for fact in facts:
            content = fact.get("content", "")
            importance = float(fact.get("importance", 0.5))
            if content:
                fact_id = await self.store_fact(
                    thread_id, content, importance=importance
                )
                if fact_id:
                    count += 1
        return count

    async def search_facts(
        self,
        thread_id: str,
        query: str,
        top_k: int = 10,
    ) -> list[dict[str, Any]]:
        """Semantic search across stored facts using hybrid retrieval."""
        all_facts = await self._repo.get_facts(thread_id)
        if not all_facts:
            return []
        return await self._hybrid.retrieve(query, all_facts, top_k=top_k)

    # ------------------------------------------------------------------
    # Internal helpers (mirror MemoryManager's private methods)
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

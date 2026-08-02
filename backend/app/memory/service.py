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
import os
import uuid
from datetime import datetime
from typing import Any
from weakref import WeakKeyDictionary

from app.memory.interfaces import (
    ContextCompiler,
    MemoryContext,
    MemoryExtractor,
    MemoryRepository,
    MemoryService,
)
from app.memory.types import MemoryFact, MemorySourceType
from app.memory.retrievers.bm25_retriever import BM25Retriever
from app.memory.retrievers.vector_retriever import VectorRetriever
from app.memory.retrievers.hybrid_retriever import HybridRetriever
from app.core.logging import get_logger
from app.harness.budget import CancellationToken, RunBudget
from app.harness.checkpoint import run_checkpoint_config

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
        run_id: str | None = None,
    ) -> None:
        self._repo = repository
        self._extractor = extractor
        self.checkpointer = checkpointer
        self.max_facts = max_facts
        self.default_user_id = default_user_id
        self.run_id = run_id
        self.last_model_call = None

        self._bm25 = BM25Retriever()
        self._vector = VectorRetriever(api_key, base_url)
        self._hybrid = HybridRetriever(self._bm25, self._vector)
        self._compiler = ContextCompiler()

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
        source_type: str | None = None,
        source_id: str | None = None,
        confidence: float = 0.5,
        verified: bool = False,
        expires_at: datetime | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> str | None:
        """Persist a fact after deduplication against existing facts.

        Deduplication and retention are scoped to the same user+kind+thread.
        """
        if (
            os.getenv("MEMORY_TRUST_MODE") == "legacy-read-safe"
            and source_type is None
        ):
            logger.warning(
                "memory_write_blocked_legacy_read_safe",
                extra={"kind": kind},
            )
            return None
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
                fact = MemoryFact(
                    content=content,
                    source_type=source_type or MemorySourceType.USER,
                    source_id=source_id,
                    confidence=confidence,
                    verified=verified,
                    expires_at=expires_at,
                    id=fact_id,
                    user_id=owner_id,
                    thread_id=thread_id,
                    kind=kind,
                    importance=importance,
                    source=source,
                    metadata=metadata or {},
                )
                await self._repo.put_fact(
                    thread_id,
                    fact_id,
                    content,
                    importance,
                    source,
                    user_id=owner_id,
                    kind=kind,
                    metadata=fact.to_dict()["metadata"],
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
        run_id: str | None = None,
    ) -> MemoryContext:
        """Retrieve short-term and long-term context for a query."""
        short: list[dict[str, Any]] = []
        completed_steps: list[str] = []
        terminal_output: str = ""

        if self.checkpointer:
            config = run_checkpoint_config(thread_id, run_id or self.run_id)
            cp = await self.checkpointer.aget_tuple(config)
            if cp:
                short = self._messages_from_checkpoint(cp.checkpoint)
                channel_values = cp.checkpoint.get("channel_values", {})
                completed_steps = channel_values.get("completed_steps", [])
                terminal_output = channel_values.get("last_terminal_output", "")

        long_facts: list[dict[str, Any]] = []
        owner_id = user_id if user_id is not None else self.default_user_id
        if owner_id is None:
            return MemoryContext(short_term_messages=short)
        all_facts = await self._repo.get_facts(
            thread_id, user_id=owner_id, kind=kind, limit=1000
        )
        typed_facts: list[MemoryFact] = []
        for raw_fact in all_facts:
            fact = MemoryFact.from_dict(raw_fact)
            if not fact.is_expired():
                typed_facts.append(fact)
        if typed_facts:
            ranked_facts = await self._hybrid.retrieve(
                query,
                [fact.to_dict() for fact in typed_facts],
                top_k=top_k,
            )
            long_facts = _restore_fact_provenance(ranked_facts, typed_facts)

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

        memory_facts = [MemoryFact.from_dict(fact) for fact in long_facts]
        tool_outputs: list[Any] = []
        if completed_steps:
            tool_outputs.append({
                "kind": "execution_progress",
                "completed_steps": [
                    str(step)[:100] for step in completed_steps[:20]
                ],
            })
        if terminal_output:
            tool_outputs.append({
                "kind": "terminal_output",
                "data": str(terminal_output),
            })
        envelopes = self._compiler.compile(
            memory_facts=memory_facts,
            tool_outputs=tool_outputs,
        )
        compiled_summary = self._compiler.render(envelopes)

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
            summary=compiled_summary,
            memory_facts=memory_facts,
            envelopes=envelopes,
        )

    async def extract_and_store_facts(
        self,
        thread_id: str,
        user_id: int | None = None,
        *,
        run_id: str | None = None,
        budget: RunBudget | None = None,
        cancellation: CancellationToken | None = None,
        trace_id: str | None = None,
        messages: list[dict[str, Any]] | None = None,
        call_id: str | None = None,
    ) -> int:
        """Extract facts from recent conversation and persist them.

        Returns the number of new facts stored.  Extraction failure
        returns 0 (does not fail the calling operation).
        """
        self.last_model_call = None
        recent_messages = list(messages or [])
        if messages is None and self.checkpointer:
            config = run_checkpoint_config(thread_id, run_id or self.run_id)
            cp = await self.checkpointer.aget_tuple(config)
            if cp:
                recent_messages = self._messages_from_checkpoint(cp.checkpoint)[-20:]

        owner_id = user_id if user_id is not None else self.default_user_id
        if owner_id is None:
            return 0

        user_messages = [
            message for message in recent_messages[-20:]
            if message.get("role") in {"user", "human"}
        ]
        try:
            if budget is not None:
                budget.check_deadline()
            if cancellation is not None:
                cancellation.raise_if_cancelled()
            run_extractor = getattr(self._extractor, "extract_for_run", None)
            if run_extractor is None:
                facts = await self._extractor.extract(user_messages)
            else:
                facts = await run_extractor(
                    user_messages,
                    run_id=run_id or self.run_id,
                    trace_id=trace_id,
                    budget=budget,
                    cancellation=cancellation,
                    call_id=call_id,
                )
            self.last_model_call = getattr(self._extractor, "last_model_call", None)
        except Exception:
            logger.exception("extract_and_store_facts failed")
            return 0

        count = 0
        for fact in facts:
            content = fact.get("content", "")
            if not isinstance(content, str):
                continue
            try:
                importance = min(
                    1.0, max(0.0, float(fact.get("importance", 0.5)))
                )
            except (TypeError, ValueError):
                importance = 0.5
            source_type = fact.get(
                "source_type", MemorySourceType.USER.value
            )
            if (
                content
                and source_type == MemorySourceType.USER.value
                and not _looks_like_instruction_or_secret(str(content))
            ):
                fact_id = await self.store_fact(
                    thread_id, content, importance=importance,
                    user_id=owner_id,
                    kind="semantic",
                    source="extraction",
                    source_type=source_type,
                    source_id=fact.get("source_id") or thread_id,
                    confidence=_bounded_confidence(fact.get("confidence", 0.5)),
                    verified=False,
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
        if owner_id is None:
            return []
        all_facts = await self._repo.get_facts(
            thread_id, user_id=owner_id, kind=kind, limit=1000
        )
        active_facts: list[MemoryFact] = []
        for raw_fact in all_facts:
            fact = MemoryFact.from_dict(raw_fact)
            if not fact.is_expired():
                active_facts.append(fact)
        if not active_facts:
            return []
        ranked_facts = await self._hybrid.retrieve(
            query,
            [fact.to_dict() for fact in active_facts],
            top_k=top_k,
        )
        return _restore_fact_provenance(ranked_facts, active_facts)

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


def _looks_like_instruction_or_secret(content: str) -> bool:
    lowered = content.lower()
    markers = (
        "ignore previous",
        "ignore system",
        "ignore policy",
        "system prompt",
        "api key",
        "access token",
        "泄露",
        "忽略系统",
        "系统策略",
        "批准写",
    )
    return any(marker in lowered for marker in markers)


def _bounded_confidence(value: Any) -> float:
    try:
        return min(1.0, max(0.0, float(value)))
    except (TypeError, ValueError):
        return 0.5


def _restore_fact_provenance(
    ranked_facts: list[dict[str, Any]],
    source_facts: list[MemoryFact],
) -> list[dict[str, Any]]:
    """Reattach provenance after a retriever returns ranked projections."""
    by_content: dict[str, list[MemoryFact]] = {}
    for fact in source_facts:
        by_content.setdefault(fact.content, []).append(fact)

    restored: list[dict[str, Any]] = []
    for ranked in ranked_facts:
        content = str(ranked.get("content", ""))
        candidates = by_content.get(content, [])
        fact = candidates.pop(0) if candidates else MemoryFact.from_dict(ranked)
        value = fact.to_dict()
        for key in ("score", "timestamp", "embedding"):
            if key in ranked:
                value[key] = ranked[key]
        restored.append(value)
    return restored


class LegacyMemoryServiceAdapter(MemoryService):
    """Deprecated read-compatible adapter for the old MemoryManager path."""

    def __init__(self, manager: Any, default_user_id: int | None = None) -> None:
        self._manager = manager
        self.default_user_id = default_user_id

    def _scope(
        self, thread_id: str, user_id: int | None, kind: str | None = None
    ) -> str:
        owner = user_id if user_id is not None else self.default_user_id
        if owner is None:
            return ""
        scope = "user" if kind in {"semantic", "profile"} else f"thread:{thread_id}"
        return f"legacy-user:{owner}:{scope}"

    def _deprecated(self) -> None:
        logger.warning(
            "deprecated_memory_manager_path",
            extra={
                "adapter": "legacy_memory_service",
                "operation": "memory",
            },
        )

    async def store_fact(
        self,
        thread_id: str,
        content: str,
        importance: float = 0.5,
        source: str = "conversation",
        user_id: int | None = None,
        kind: str = "episodic",
        **kwargs: Any,
    ) -> str | None:
        self._deprecated()
        scoped = self._scope(thread_id, user_id, kind)
        if not scoped or not getattr(self._manager, "_store", None):
            return None
        return await self._manager._add_fact(
            scoped, content, importance=importance, source=source
        )

    async def retrieve_context(
        self,
        thread_id: str,
        query: str,
        top_k: int = 5,
        user_id: int | None = None,
        kind: str | None = None,
        run_id: str | None = None,
    ) -> MemoryContext:
        self._deprecated()
        scoped = self._scope(thread_id, user_id, kind)
        if not scoped:
            return MemoryContext()
        legacy_context = await self._manager.load_context(
            scoped, query, top_k=top_k, run_id=run_id
        )
        facts = []
        for raw_fact in legacy_context.long_term_facts:
            fact = MemoryFact.from_dict(raw_fact)
            if not fact.is_expired():
                facts.append(fact)
        tool_outputs = [
            message.get("content", "")
            for message in legacy_context.short_term_messages
            if message.get("role") == "tool"
        ]
        envelopes = ContextCompiler().compile(
            memory_facts=facts,
            tool_outputs=tool_outputs,
        )
        return MemoryContext(
            short_term_messages=legacy_context.short_term_messages,
            long_term_facts=[fact.to_dict() for fact in facts],
            summary=legacy_context.summary,
            memory_facts=facts,
            envelopes=envelopes,
        )

    async def extract_and_store_facts(
        self,
        thread_id: str,
        user_id: int | None = None,
        *,
        run_id: str | None = None,
        budget: RunBudget | None = None,
        cancellation: CancellationToken | None = None,
        trace_id: str | None = None,
    ) -> int:
        self._deprecated()
        scoped = self._scope(thread_id, user_id, "semantic")
        if not scoped:
            return 0
        return await self._manager.extract_and_store_facts(scoped, run_id=run_id)

    async def search_facts(
        self,
        thread_id: str,
        query: str,
        top_k: int = 10,
        user_id: int | None = None,
        kind: str | None = None,
    ) -> list[dict[str, Any]]:
        context = await self.retrieve_context(
            thread_id, query, top_k=top_k, user_id=user_id, kind=kind
        )
        return context.long_term_facts


MemoryManagerAdapter = LegacyMemoryServiceAdapter

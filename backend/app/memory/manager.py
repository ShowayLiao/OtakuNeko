import uuid
from datetime import datetime
from dataclasses import dataclass, field
from typing import Any, List, Optional, TYPE_CHECKING, cast

from app.memory.retrievers.bm25_retriever import BM25Retriever
from app.memory.retrievers.vector_retriever import VectorRetriever
from app.memory.retrievers.hybrid_retriever import HybridRetriever
from app.core.logging import get_logger
from app.harness.checkpoint import run_checkpoint_config

if TYPE_CHECKING:
    from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

logger = get_logger(__name__)


@dataclass
class MemoryContext:
    short_term_messages: list[dict] = field(default_factory=list)
    long_term_facts: list[dict] = field(default_factory=list)
    summary: str = ""


class MemoryManager:
    def __init__(
        self,
        api_key: str,
        base_url: str,
        checkpointer: Optional["AsyncSqliteSaver"] = None,
        store=None,
        max_facts: int = 500,
        fact_model: str = "gpt-3.5-turbo",
        run_id: str | None = None,
    ):
        self.checkpointer = checkpointer
        self._store = store
        self.max_facts = max_facts
        self.fact_model = fact_model
        self.run_id = run_id
        self.bm25 = BM25Retriever()
        self.vector = VectorRetriever(api_key, base_url)
        self.hybrid = HybridRetriever(self.bm25, self.vector)

    def _messages_from_checkpoint(self, checkpoint) -> List[dict]:
        messages = []
        channel_values = checkpoint.get("channel_values", {})
        raw = channel_values.get("messages", [])
        for m in raw:
            if hasattr(m, "type") and hasattr(m, "content"):
                messages.append({"role": m.type, "content": str(m.content)})
        return messages

    async def _get_facts(self, thread_id: str) -> list[dict]:
        if not self._store:
            return []
        items = await self._store.asearch(("facts", thread_id))
        facts = []
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

    async def _add_fact(
        self,
        thread_id: str,
        content: str,
        importance: float = 0.5,
        source: str = "conversation",
    ) -> Optional[str]:
        if not self._store:
            return None

        existing = await self._get_facts(thread_id)
        if existing:
            all_contents = [f["content"] for f in existing] + [content]
            vecs = await self.vector.embed(all_contents)
            new_vec = vecs[-1]
            for i, existing_vec in enumerate(vecs[:-1]):
                if VectorRetriever.cosine_similarity(new_vec, existing_vec) > 0.9:
                    return None
        else:
            new_vec = (await self.vector.embed([content]))[0]

        fact_id = str(uuid.uuid4())
        await self._store.aput(
            ("facts", thread_id),
            fact_id,
            {
                "content": content,
                "importance": importance,
                "source": source,
                "timestamp": datetime.utcnow().isoformat(),
                "embedding": new_vec,
            },
        )

        if len(existing) > self.max_facts:
            facts_sorted = sorted(
                existing, key=lambda f: (f.get("importance", 0), f.get("timestamp", ""))
            )
            for old in facts_sorted[: -(self.max_facts)]:
                await self._store.adelete(("facts", thread_id), old["id"])

        return fact_id

    async def load_context(
        self,
        thread_id: str,
        current_query: str,
        top_k: int = 5,
        run_id: str | None = None,
    ) -> MemoryContext:
        short = []
        completed_steps = []
        terminal_output = ""
        if self.checkpointer:
            config = run_checkpoint_config(thread_id, run_id or self.run_id)
            cp = await self.checkpointer.aget_tuple(cast(Any, config))
            if cp:
                short = self._messages_from_checkpoint(cp.checkpoint)
                channel_values = cp.checkpoint.get("channel_values", {})
                completed_steps = channel_values.get("completed_steps", [])
                terminal_output = channel_values.get("last_terminal_output", "")

        long_facts = []
        all_facts = await self._get_facts(thread_id)
        if all_facts and self._store:
            long_facts = await self.hybrid.retrieve(
                current_query, all_facts, top_k=top_k
            )

        parts = []
        if long_facts:
            parts.append("[长期记忆] 相关历史信息：")
            for f in long_facts:
                parts.append(f"- {f['content']}")
        if completed_steps:
            parts.append(f"[执行进度] 已完成步骤: {', '.join(completed_steps)}")
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
        self,
        thread_id: str,
        run_id: str | None = None,
    ) -> int:
        if not self._store:
            return 0

        messages = []
        if self.checkpointer:
            config = run_checkpoint_config(thread_id, run_id or self.run_id)
            cp = await self.checkpointer.aget_tuple(cast(Any, config))
            if cp:
                messages = self._messages_from_checkpoint(cp.checkpoint)[-20:]

        if len(messages) < 4:
            return 0

        conv_text = "\n".join(
            f"{'用户' if m['role'] in ('human', 'user') else 'AI'}: {m['content']}"
            for m in messages
        )
        system_prompt = (
            "请从以下对话中提取关于用户的重要信息（偏好、习惯、个人信息、重要决策），"
            "每条信息简洁概括（一句话）。不要提取琐碎的闲聊内容。\n"
            '只返回 JSON 格式：{"facts": [{"content": "...", "importance": 0.8}]}'
        )

        try:
            response = await self.vector.client.chat.completions.create(
                model=self.fact_model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": conv_text},
                ],
                response_format={"type": "json_object"},
                temperature=0.3,
            )
            import json

            result = json.loads(response.choices[0].message.content or "{}")
            facts = result.get("facts", [])

            count = 0
            for fact in facts:
                content = fact.get("content", "")
                importance = float(fact.get("importance", 0.5))
                if content:
                    fact_id = await self._add_fact(
                        thread_id, content, importance=importance
                    )
                    if fact_id:
                        count += 1
            return count
        except Exception:
            return 0

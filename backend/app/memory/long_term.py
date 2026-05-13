import uuid
from datetime import datetime

from app.memory.stores.json_store import JsonStore
from app.memory.retrievers.bm25_retriever import BM25Retriever
from app.memory.retrievers.vector_retriever import VectorRetriever
from app.memory.retrievers.hybrid_retriever import HybridRetriever

LONG_TERM_DIR = "data/memory/long_term"


class LongTermMemory:
    def __init__(self, api_key: str, base_url: str, max_facts: int = 500):
        self.store = JsonStore(LONG_TERM_DIR)
        self.max_facts = max_facts
        self.bm25 = BM25Retriever()
        self.vector = VectorRetriever(api_key, base_url)
        self.hybrid = HybridRetriever(self.bm25, self.vector)

    async def _load_facts(self, thread_id: str) -> dict:
        return await self.store.read(f"{thread_id}_facts.json")

    async def _save_facts(self, thread_id: str, data: dict) -> None:
        await self.store.write(f"{thread_id}_facts.json", data)

    async def add_fact(self, thread_id: str, content: str,
                       importance: float = 0.5, source: str = "conversation") -> str | None:
        data = await self._load_facts(thread_id)
        facts: list = data.get("facts", [])
        now = datetime.utcnow().isoformat()

        if facts:
            all_contents = [f["content"] for f in facts] + [content]
            vecs = await self.vector.embed(all_contents)
            new_vec = vecs[-1]
            for i, existing_vec in enumerate(vecs[:-1]):
                if VectorRetriever.cosine_similarity(new_vec, existing_vec) > 0.9:
                    return None
        else:
            new_vec = (await self.vector.embed([content]))[0]

        fact_id = str(uuid.uuid4())
        facts.append({
            "id": fact_id, "content": content, "embedding": new_vec,
            "source": source, "timestamp": now, "importance": importance,
        })

        if len(facts) > self.max_facts:
            facts.sort(key=lambda f: (f["importance"], f["timestamp"]))
            facts = facts[-(self.max_facts):]

        data["facts"] = facts
        data["updated_at"] = now
        await self._save_facts(thread_id, data)
        return fact_id

    async def retrieve(self, thread_id: str, query: str, top_k: int = 5) -> list[dict]:
        data = await self._load_facts(thread_id)
        facts = data.get("facts", [])
        if not facts:
            return []
        return await self.hybrid.retrieve(query, facts, top_k=top_k)

    async def get_all_facts(self, thread_id: str) -> list[dict]:
        data = await self._load_facts(thread_id)
        return [
            {k: v for k, v in f.items() if k != "embedding"}
            for f in data.get("facts", [])
        ]

    async def export_markdown(self, thread_id: str) -> str:
        facts = await self.get_all_facts(thread_id)
        lines = [f"# 长期记忆 - {thread_id}", ""]
        for f in sorted(facts, key=lambda x: x.get("timestamp", "")):
            lines.append(f"- [{f.get('importance', 0):.1f}] {f['content']}")
        return "\n".join(lines)

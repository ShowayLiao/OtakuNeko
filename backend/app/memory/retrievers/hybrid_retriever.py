from app.memory.retrievers.bm25_retriever import BM25Retriever
from app.memory.retrievers.vector_retriever import VectorRetriever


class HybridRetriever:
    def __init__(self, bm25: BM25Retriever, vector: VectorRetriever, alpha: float = 0.3):
        self.bm25 = bm25
        self.vector = vector
        self.alpha = alpha

    async def retrieve(self, query: str, facts: list[dict], top_k: int = 5) -> list[dict]:
        facts_text = [f["content"] for f in facts]
        bm25_results = self.bm25.search(query, top_k=len(facts), facts=facts_text)
        vector_results = await self.vector.search(query, facts, top_k=len(facts))

        scores: dict[int, float] = {}
        for i, s in bm25_results:
            scores[i] = self.alpha * s
        for i, s in vector_results:
            scores[i] = scores.get(i, 0) + (1 - self.alpha) * s

        ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        return [
            {
                "content": facts[i]["content"],
                "score": round(s, 4),
                "importance": facts[i].get("importance", 0.5),
                "timestamp": facts[i].get("timestamp", ""),
            }
            for i, s in ranked[:top_k]
        ]

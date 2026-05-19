import math

from openai import AsyncOpenAI


class VectorRetriever:
    def __init__(self, api_key: str, base_url: str, model: str = "text-embedding-3-small"):
        self.client = AsyncOpenAI(api_key=api_key, base_url=base_url)
        self.model = model

    @staticmethod
    def cosine_similarity(vec_a: list[float], vec_b: list[float]) -> float:
        dot = sum(a * b for a, b in zip(vec_a, vec_b))
        norm_a = math.sqrt(sum(a * a for a in vec_a))
        norm_b = math.sqrt(sum(b * b for b in vec_b))
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return dot / (norm_a * norm_b)

    async def embed(self, texts: list[str]) -> list[list[float]]:
        response = await self.client.embeddings.create(model=self.model, input=texts)
        return [item.embedding for item in response.data]

    async def search(self, query: str, facts: list[dict], top_k: int = 5) -> list[tuple[int, float]]:
        no_emb = [(i, f) for i, f in enumerate(facts) if not f.get("embedding")]
        if no_emb:
            texts = [f["content"] for _, f in no_emb]
            emb_list = await self.embed(texts)
            for (i, _), emb in zip(no_emb, emb_list):
                facts[i]["embedding"] = emb

        query_emb = (await self.embed([query]))[0]
        scores = [self.cosine_similarity(query_emb, f.get("embedding", [])) for f in facts]
        ranked = sorted(enumerate(scores), key=lambda x: x[1], reverse=True)
        return [(int(i), float(s)) for i, s in ranked[:top_k] if s > 0]

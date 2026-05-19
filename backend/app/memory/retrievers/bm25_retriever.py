from rank_bm25 import BM25Okapi


class BM25Retriever:
    def __init__(self):
        self.facts: list[str] = []
        self.bm25 = None
        self._dirty = True

    def _ensure_index(self, facts: list[str]):
        if self._dirty or self.facts != facts:
            self.facts = list(facts)
            tokenized = [f.split() for f in self.facts]
            self.bm25 = BM25Okapi(tokenized)
            self._dirty = False

    def search(self, query: str, top_k: int = 5, facts: list[str] | None = None) -> list[tuple[int, float]]:
        if facts is not None:
            self._ensure_index(facts)
        if not self.bm25:
            return []
        tokenized_query = query.split()
        scores = self.bm25.get_scores(tokenized_query)
        max_score = max(scores) if max(scores) and max(scores) > 0 else 1
        ranked = sorted(enumerate(scores), key=lambda x: x[1], reverse=True)
        return [(int(i), float(s / max_score)) for i, s in ranked[:top_k] if s > 0]

import re

from rank_bm25 import BM25Okapi


_TOKEN_PATTERN = re.compile(r"[A-Za-z0-9_]+|[\u4e00-\u9fff]")


def _tokenize(text: str) -> list[str]:
    tokens = _TOKEN_PATTERN.findall(text.casefold())
    return tokens or [text.casefold()]


class BM25Retriever:
    def __init__(self):
        self.facts: list[str] = []
        self.bm25 = None
        self._dirty = True

    def _ensure_index(self, facts: list[str]):
        if self._dirty or self.facts != facts:
            self.facts = list(facts)
            tokenized = [_tokenize(f) for f in self.facts]
            self.bm25 = BM25Okapi(tokenized)
            self._dirty = False

    def search(self, query: str, top_k: int = 5, facts: list[str] | None = None) -> list[tuple[int, float]]:
        if facts is not None:
            self._ensure_index(facts)
        if not self.bm25:
            return []
        tokenized_query = _tokenize(query)
        scores = self.bm25.get_scores(tokenized_query)
        max_score = max(scores) if max(scores) and max(scores) > 0 else 1
        ranked = sorted(enumerate(scores), key=lambda x: x[1], reverse=True)
        positive = [
            (int(i), float(s / max_score))
            for i, s in ranked[:top_k]
            if s > 0
        ]
        if positive:
            return positive

        # BM25 can produce no positive IDF when the corpus is very small.
        # Preserve exact keyword retrieval instead of hiding matching facts.
        query_terms = set(tokenized_query)
        overlap = [
            (i, len(query_terms & set(_tokenize(fact))))
            for i, fact in enumerate(self.facts)
        ]
        max_overlap = max((score for _, score in overlap), default=0)
        if max_overlap == 0:
            return []
        return [
            (int(i), float(score / max_overlap))
            for i, score in sorted(
                overlap, key=lambda item: item[1], reverse=True
            )[:top_k]
            if score > 0
        ]

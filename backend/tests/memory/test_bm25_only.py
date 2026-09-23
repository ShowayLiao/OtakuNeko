import pytest

from app.memory.retrievers.bm25_retriever import BM25Retriever
from app.memory.retrievers.hybrid_retriever import HybridRetriever


@pytest.mark.asyncio
async def test_hybrid_retriever_without_vector_uses_bm25_only():
    retriever = HybridRetriever(BM25Retriever(), None)
    facts = [
        {"content": "user likes science fiction", "importance": 0.8},
        {"content": "user dislikes horror movies", "importance": 0.5},
        {"content": "user watches documentaries", "importance": 0.5},
    ]

    results = await retriever.retrieve("science fiction", facts)

    assert results[0]["content"] == "user likes science fiction"


def test_bm25_retrieves_a_matching_fact_from_a_single_fact_corpus():
    retriever = BM25Retriever()

    results = retriever.search("fact", facts=["alice fact"])

    assert results == [(0, 1.0)]


def test_bm25_tokenizes_chinese_text_without_spaces():
    retriever = BM25Retriever()

    results = retriever.search(
        "喜欢科幻",
        facts=["喜欢科幻", "讨厌恐怖片", "喜欢纪录片"],
    )

    assert results[0][0] == 0

"""Tests for MULTI-AGENT-001 Step 03: RecommendationAgent."""

from __future__ import annotations

import pytest

from app.agents.recommendation_agent import RecommendationAgent
from app.harness.task import AgentTask


class StubCapability:
    """Fake capability that returns controlled results."""

    def __init__(self, profile=None, fail=False):
        self._profile = profile or {
            "llm_summary": {"total_rated": 10, "taste_dictionary": {"科幻": [3, 8.0]}},
            "candidates": [{"id": 1, "name": "星际牛仔", "score": 9}],
            "chart_data": {
                "radar": [{"label": "科幻", "value": 80}],
                "bar_count": [{"name": "星际牛仔", "score": 9}],
            },
            "watched_ids": [],
        }
        self._fail = fail

    async def execute(self, action, **kwargs):
        if self._fail:
            return {"success": False, "error": "service_failed"}
        return {
            "success": True,
            "profile": self._profile,
            "evidence": {"source": "profile", "total_rated": 10, "taste_tags": ["科幻"]},
        }


class RecordingMemory:
    def __init__(self):
        self.calls = []

    async def retrieve_context(self, thread_id, query, **kwargs):
        self.calls.append((thread_id, query, kwargs))
        return type("Context", (), {"summary": "prefers science fiction", "long_term_facts": []})()


class StubAnimeCapability:
    async def execute(self, action, **kwargs):
        assert action == "search"
        return {
            "success": True,
            "results": [
                {"id": 99, "name": "攻壳机动队", "score": 9.0},
            ],
        }


class FailingAnimeCapability:
    async def execute(self, action, **kwargs):
        return {"success": False, "error": "upstream_unavailable"}


class StubResponseGenerator:
    def __init__(self):
        self.calls = 0

    async def generate(self, goal, candidates, profile):
        self.calls += 1
        return "模型生成的推荐"


class TestRecommendationAgent:
    @pytest.mark.asyncio
    async def test_personalized_recommendation(self):
        agent = RecommendationAgent(StubCapability())
        task = AgentTask(user_id=1, goal="推荐动漫")
        result = await agent.execute(task)

        assert result["role"] == "assistant"
        assert len(result["candidates"]) > 0
        assert "根据你的偏好" in result["content"]

    @pytest.mark.asyncio
    async def test_cold_start_returns_fallback(self):
        cap = StubCapability(profile={
            "llm_summary": {"total_rated": 0, "taste_dictionary": {}},
            "chart_data": {"radar": [], "bar_count": [], "bar_score": []},
            "watched_ids": [],
        })
        agent = RecommendationAgent(cap)
        task = AgentTask(user_id=1, goal="推荐动漫")
        result = await agent.execute(task)

        assert result["role"] == "assistant"
        assert len(result["candidates"]) == 0
        assert "暂时没有" in result["content"] or "暂时" in result["content"] or "暂无" in result.get("content", "")

    @pytest.mark.asyncio
    async def test_capability_failure_returns_honest_fallback(self):
        agent = RecommendationAgent(StubCapability(fail=True))
        task = AgentTask(user_id=1, goal="推荐动漫")
        result = await agent.execute(task)

        assert result.get("content", "")
        assert "暂时无法" in result["content"]
        assert result["evidence"]["source"] == "fallback"

    @pytest.mark.asyncio
    async def test_candidate_search_failure_returns_honest_fallback(self):
        agent = RecommendationAgent(
            StubCapability(profile={
                "llm_summary": {"total_rated": 10, "taste_dictionary": {"科幻": [3, 8.0]}},
                "chart_data": {"radar": [], "bar_count": []},
                "watched_ids": [],
            }),
            anime_capability=FailingAnimeCapability(),
        )

        result = await agent.execute(AgentTask(user_id=1, goal="推荐动漫"))

        assert result["evidence"] == {
            "source": "fallback",
            "reason": "candidate_search_failed",
        }
        assert "推荐服务暂时不可用" in result["content"]

    @pytest.mark.asyncio
    async def test_memory_is_retrieved_and_model_budget_is_enforced(self):
        memory = RecordingMemory()
        agent = RecommendationAgent(
            StubCapability(profile={
                "llm_summary": {"total_rated": 10, "taste_dictionary": {"科幻": [3, 8.0]}},
                "chart_data": {"radar": [], "bar_count": []},
                "watched_ids": [],
            }),
            anime_capability=StubAnimeCapability(),
            memory_service=memory,
            max_model_calls=1,
        )
        task = AgentTask(
            user_id=7,
            goal="推荐动漫",
            metadata={"thread_id": "thread-7", "collections": [{"id": 1}]},
        )

        result = await agent.execute(task)

        assert memory.calls == [("thread-7", "推荐动漫", {"user_id": 7})]
        assert result["candidates"] == [{"id": 99, "name": "攻壳机动队", "score": 9.0}]

        generator = StubResponseGenerator()
        generated = RecommendationAgent(
            StubCapability(),
            anime_capability=StubAnimeCapability(),
            response_generator=generator,
            max_model_calls=1,
        )
        generated_result = await generated.execute(task)
        assert generated_result["content"] == "模型生成的推荐"
        assert generator.calls == 1

        exhausted = RecommendationAgent(
            StubCapability(),
            response_generator=StubResponseGenerator(),
            max_model_calls=0,
        )
        fallback = await exhausted.execute(task)
        assert fallback["evidence"]["reason"] == "model_budget_exhausted"

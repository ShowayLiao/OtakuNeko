"""Tests for MULTI-AGENT-001 Step 03: RecommendationAgent."""

from __future__ import annotations

import pytest

from app.agents.recommendation_agent import RecommendationAgent
from app.harness.task import AgentTask
from app.trace import AgentTrace
from app.trace.recorder import bind_trace


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
    def __init__(self, results=None):
        self.results = results or [
            {"id": 99, "name": "攻壳机动队", "score": 9.0},
        ]
        self.last_kwargs = None

    async def execute(self, action, **kwargs):
        assert action == "search"
        self.last_kwargs = kwargs
        return {
            "success": True,
            "results": self.results,
        }


class MultiRouteAnimeCapability:
    def __init__(self, responses):
        self.responses = responses
        self.calls = []

    async def execute(self, action, **kwargs):
        assert action == "search"
        self.calls.append(kwargs)
        tag = (kwargs.get("tags") or [None])[0]
        return self.responses[tag]


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

        assert result["evidence"]["source"] == "fallback"
        assert result["evidence"]["reason"] == "candidate_search_failed"
        assert result["evidence"]["candidate_search"]["failed_searches"] == 1
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

    @pytest.mark.asyncio
    async def test_candidate_search_uses_favorites_and_filters_avoid_tags(self):
        profile = {
            "llm_summary": {
                "total_rated": 8,
                "taste_dictionary": {"校园": [4, 8.0]},
                "favorite_tags": ["科幻"],
                "avoid_tags": ["校园"],
                "strong_avoid_tags": ["校园"],
            },
            "watched_ids": [1],
        }
        anime = StubAnimeCapability(
            results=[
                {"id": 1, "name": "已看", "tags": ["科幻"]},
                {"id": 2, "name": "雷区作品", "tags": ["科幻", "校园"]},
                {"id": 3, "name": "合适作品", "tags": ["科幻"]},
            ]
        )
        agent = RecommendationAgent(
            StubCapability(profile=profile),
            anime_capability=anime,
        )

        result = await agent.execute(AgentTask(user_id=1, goal="推荐动漫"))

        assert [item["id"] for item in result["candidates"]] == [3]
        assert anime.last_kwargs["tags"] == ["科幻"]

    @pytest.mark.asyncio
    async def test_candidates_without_tags_are_not_dropped(self):
        profile = {
            "llm_summary": {
                "total_rated": 2,
                "taste_dictionary": {"科幻": [2, 8.0]},
                "favorite_tags": ["科幻"],
                "avoid_tags": ["校园"],
            },
            "watched_ids": [],
        }
        anime = StubAnimeCapability(results=[{"id": 2, "name": "未知标签"}])
        agent = RecommendationAgent(
            StubCapability(profile=profile),
            anime_capability=anime,
        )

        result = await agent.execute(AgentTask(user_id=1, goal="推荐动漫"))

        assert result["candidates"] == [{"id": 2, "name": "未知标签"}]
    @pytest.mark.asyncio
    async def test_candidate_search_uses_independent_routes_and_strong_avoid_filter(self):
        profile = {
            "llm_summary": {
                "total_rated": 8,
                "favorite_tags": ["tag-a", "tag-b", "tag-c"],
                "avoid_tags": ["soft-avoid"],
                "strong_avoid_tags": ["hard-avoid"],
                "tag_preferences": {
                    "tag-a": {"preference_score": 80, "preference_delta": 1.0},
                    "tag-b": {"preference_score": 70, "preference_delta": 0.8},
                    "tag-c": {"preference_score": 60, "preference_delta": 0.5},
                    "soft-avoid": {"preference_score": 30, "preference_delta": -0.4},
                },
            },
            "watched_ids": [1],
        }
        anime = MultiRouteAnimeCapability({
            "tag-a": {"success": True, "results": [
                {"id": 1, "name": "watched", "tags": ["tag-a"]},
                {"id": 2, "name": "soft", "tags": ["tag-a", "soft-avoid"]},
                {"id": 3, "name": "hard", "tags": ["tag-a", "hard-avoid"]},
            ]},
            "tag-b": {"success": True, "results": [
                {"id": 2, "name": "soft-duplicate", "tags": ["tag-b", "soft-avoid"]},
                {"id": 4, "name": "plain", "tags": ["tag-b"]},
            ]},
            "tag-c": {"success": True, "results": [
                {"id": 5, "name": "third", "tags": ["tag-c"]},
            ]},
        })

        agent = RecommendationAgent(
            StubCapability(profile=profile),
            anime_capability=anime,
            max_candidates=3,
        )

        result = await agent.execute(AgentTask(user_id=1, goal="recommend"))

        assert [call["keyword"] for call in anime.calls] == ["", "", ""]
        assert [call["tags"] for call in anime.calls] == [["tag-a"], ["tag-b"], ["tag-c"]]
        assert all(call["limit"] >= 20 for call in anime.calls)
        assert {item["id"] for item in result["candidates"]} == {2, 4, 5}

    @pytest.mark.asyncio
    async def test_candidate_search_continues_after_one_route_fails(self):
        profile = {
            "llm_summary": {
                "total_rated": 3,
                "favorite_tags": ["tag-a", "tag-b", "tag-c"],
                "strong_avoid_tags": [],
            },
            "watched_ids": [],
        }
        anime = MultiRouteAnimeCapability({
            "tag-a": {"success": False, "error": "timeout"},
            "tag-b": {"success": True, "results": [{"id": 2, "name": "second"}]},
            "tag-c": {"success": True, "results": [{"id": 3, "name": "third"}]},
        })

        agent = RecommendationAgent(
            StubCapability(profile=profile),
            anime_capability=anime,
        )

        result = await agent.execute(AgentTask(user_id=1, goal="recommend"))

        assert {item["id"] for item in result["candidates"]} == {2, 3}
        assert result["evidence"]["source"] == "profile"

    @pytest.mark.asyncio
    async def test_successful_search_with_no_results_has_distinct_reason(self):
        profile = {
            "llm_summary": {"favorite_tags": ["tag-a"], "strong_avoid_tags": []},
            "watched_ids": [],
        }
        anime = MultiRouteAnimeCapability({
            "tag-a": {"success": True, "results": []},
        })

        result = await RecommendationAgent(
            StubCapability(profile=profile), anime_capability=anime
        ).execute(AgentTask(user_id=1, goal="recommend"))

        assert result["evidence"]["reason"] == "no_search_results"
        assert result["evidence"]["candidate_search"]["successful_searches"] == 1

    @pytest.mark.asyncio
    async def test_filtered_candidates_have_distinct_reason_and_counts(self):
        profile = {
            "llm_summary": {
                "favorite_tags": ["tag-a"],
                "strong_avoid_tags": ["hard-avoid"],
            },
            "watched_ids": [1],
        }
        anime = MultiRouteAnimeCapability({
            "tag-a": {"success": True, "results": [
                {"id": 1, "name": "watched"},
                {"id": 2, "name": "hard", "tags": ["hard-avoid"]},
            ]},
        })

        result = await RecommendationAgent(
            StubCapability(profile=profile), anime_capability=anime
        ).execute(AgentTask(user_id=1, goal="recommend"))

        assert result["evidence"]["reason"] == "no_unseen_safe_candidates"
        assert result["evidence"]["candidate_search"]["filtered_watched"] == 1
        assert result["evidence"]["candidate_search"]["filtered_strong_avoid"] == 1

    @pytest.mark.asyncio
    async def test_candidate_search_stats_are_recorded_without_private_values(self):
        profile = {
            "llm_summary": {"favorite_tags": ["tag-a"], "strong_avoid_tags": []},
            "watched_ids": [],
        }
        anime = MultiRouteAnimeCapability({
            "tag-a": {"success": True, "results": [{"id": 1, "name": "one"}]},
        })
        trace = AgentTrace(user_id=1, agent_name="recommendation")

        with bind_trace(trace):
            await RecommendationAgent(
                StubCapability(profile=profile), anime_capability=anime
            ).execute(AgentTask(user_id=1, goal="recommend"))

        event = next(
            event
            for step in trace.steps
            for event in step.events
            if event.data.get("operation") == "recommendation.candidate_search"
        )
        assert event.data["final_candidates"] == 1
        assert "tag-a" not in event.data

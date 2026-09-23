"""Integration tests for MULTI-AGENT-001 Step 04: runtime multi-agent flow."""

from __future__ import annotations

import pytest

from app.agents.agent_registry import AgentRegistry
from app.agents.recommendation_agent import RecommendationAgent
from app.agents.router import AgentRouter
from app.harness.task import AgentTask
from app.harness.state import AgentState
from app.harness.routing_adapter import FeatureFlagRoutingAdapter


class StubCapability:
    async def execute(self, action, **kwargs):
        return {
            "success": True,
            "profile": {
                "llm_summary": {"total_rated": 5, "taste_dictionary": {"热血": [2, 8]}},
                "candidates": [{"id": 1, "name": "鬼灭之刃", "score": 9}],
                "chart_data": {"radar": [{"label": "热血", "value": 80}], "bar_count": [{"name": "鬼灭之刃", "score": 9}], "bar_score": []},
                "watched_ids": [],
            },
            "evidence": {"source": "profile", "total_rated": 5, "taste_tags": ["热血"]},
        }


@pytest.fixture
def registry():
    r = AgentRegistry()
    r.register("recommendation", RecommendationAgent(StubCapability()))
    return r


@pytest.fixture
def router(registry):
    return AgentRouter(registry)


class TestRouterIntegration:
    @pytest.mark.asyncio
    async def test_feature_on_routes_recommendation(self, router):
        d = router.route("推荐一些好看的")
        assert d.selected_agent == "recommendation"

    @pytest.mark.asyncio
    async def test_unknown_falls_back(self, router):
        d = router.route("讲个笑话")
        assert d.selected_agent == "fallback"

    @pytest.mark.asyncio
    async def test_recommendation_produces_results(self, registry):
        agent = registry.get("recommendation")
        task = AgentTask(user_id=1, goal="推荐动漫")
        result = await agent.execute(task)
        assert len(result.get("candidates", [])) > 0
        assert "根据你的偏好" in result.get("content", "")

    @pytest.mark.asyncio
    async def test_feature_flag_adapter_rejects_direct_specialist_execution(self):
        class Fallback:
            async def stream(self, state, **kwargs):
                yield {"type": "message_chunk", "content": "legacy"}

        class Specialist:
            async def execute(self, task):
                return {"content": "specialist", "candidates": [{"name": "X"}]}

        class Registry:
            def list_agents(self):
                return ["recommendation"]

            def get(self, name):
                return Specialist()

        router = AgentRouter(Registry())
        task = AgentTask(user_id=1, goal="推荐动漫")
        state = AgentState(task=task)
        adapter = FeatureFlagRoutingAdapter(Fallback(), router, enabled=True)
        with pytest.raises(RuntimeError, match="Dispatcher"):
            [chunk async for chunk in adapter.stream(state, messages=[])]

        off = FeatureFlagRoutingAdapter(Fallback(), router, enabled=False)
        assert [chunk async for chunk in off.stream(state)] == [
            {"type": "message_chunk", "content": "legacy"}
        ]

    @pytest.mark.asyncio
    async def test_feature_flag_adapter_requires_dispatcher_for_specialist(self):
        class Fallback:
            async def stream(self, state, **kwargs):
                yield {"type": "message_chunk", "content": "legacy"}

        class Specialist:
            async def execute(self, task):
                return {"candidates": [{"name": "X"}], "evidence": {"source": "test"}}

        class Registry:
            def list_agents(self):
                return ["recommendation"]

            def get(self, name):
                return Specialist()

        task = AgentTask(user_id=1, goal="\u63a8\u8350\u52a8\u6f2b")
        state = AgentState(task=task, context={"orchestrate_results": True})
        adapter = FeatureFlagRoutingAdapter(
            Fallback(), AgentRouter(Registry()), enabled=True
        )

        with pytest.raises(RuntimeError, match="Dispatcher"):
            [chunk async for chunk in adapter.stream(state, messages=[])]

    @pytest.mark.asyncio
    async def test_runtime_executes_recommendation_agent(self):
        """The base agent execute() method works for recommendation."""
        agent = RecommendationAgent(StubCapability())
        task = AgentTask(user_id=1, goal="推荐动漫")
        result = await agent.execute(task)
        assert len(result.get("candidates", [])) > 0

"""Tests for MULTI-AGENT-001 Step 02: AgentRouter."""

from __future__ import annotations

import time
import pytest

from app.agents.agent_registry import AgentRegistry
from app.agents.base import BaseAgent
from app.agents.router import AgentRouter
from app.agents.routing import RouteIntent


class StubAgent(BaseAgent):
    async def execute(self, task):
        return {"role": "assistant", "content": "stub"}

    async def plan(self, task):
        return {"goal": "stub", "steps": []}

    async def reflect(self, task, result):
        return {"goal_achieved": True}


@pytest.fixture
def registry():
    r = AgentRegistry()
    r.register("recommendation", StubAgent())
    return r


@pytest.fixture
def router(registry):
    return AgentRouter(registry)


class TestDeterministicRouting:
    def test_recommendation_keyword_routes_to_recommendation(self, router):
        d = router.route("给我推荐一些好看的动漫")
        assert d.intent == RouteIntent.RECOMMENDATION
        assert d.selected_agent == "recommendation"

    def test_recommendation_short_form(self, router):
        d = router.route("求推荐")
        assert d.intent == RouteIntent.RECOMMENDATION

    def test_unknown_input_falls_back(self, router):
        d = router.route("今天天气怎么样？")
        assert d.intent == RouteIntent.UNKNOWN
        assert d.selected_agent == "fallback"

    def test_empty_goal_falls_back(self, router):
        d = router.route("")
        assert d.intent == RouteIntent.UNKNOWN


class TestAgentSelection:
    def test_known_agent_returns_instance(self, router):
        d = router.route("推荐一些番")
        agent = router.select(d)
        assert agent is not None
        assert isinstance(agent, StubAgent)

    def test_fallback_returns_none(self, router):
        d = router.route("unknown request")
        agent = router.select(d)
        assert agent is None

    def test_missing_agent_returns_none(self, registry):
        router = AgentRouter(registry)
        d = router.route("recommend something")
        # Change selected_agent to a missing one
        d.selected_agent = "nonexistent"
        agent = router.select(d)
        assert agent is None


class TestClassifierFallback:
    @pytest.mark.asyncio
    async def test_low_confidence_falls_back(self, registry):
        class LowConfClassifier:
            def classify(self, goal, messages):
                from app.agents.routing import RouteDecision, RouteIntent
                return RouteDecision(
                    intent=RouteIntent.UNKNOWN,
                    selected_agent="recommendation",
                    confidence=0.3,
                )

        router = AgentRouter(registry, classifier=LowConfClassifier())
        d = router.route("some anime question")
        assert d.selected_agent == "fallback"

    @pytest.mark.asyncio
    async def test_classifier_timeout_falls_back(self, registry):
        class FailingClassifier:
            def classify(self, goal, messages):
                raise RuntimeError("classifier timeout")

        router = AgentRouter(registry, classifier=FailingClassifier())
        d = router.route("any input")
        assert d.selected_agent == "fallback"

    def test_slow_classifier_falls_back_without_blocking(self, registry):
        class SlowClassifier:
            calls = 0

            def classify(self, goal, messages):
                self.calls += 1
                time.sleep(0.2)
                return None

        classifier = SlowClassifier()
        router = AgentRouter(registry, classifier=classifier, classifier_timeout_seconds=0.01)
        started = time.perf_counter()
        d = router.route("any input")
        second = router.route("another input")
        elapsed = time.perf_counter() - started

        assert d.selected_agent == "fallback"
        assert second.selected_agent == "fallback"
        assert elapsed < 0.1
        assert classifier.calls == 1

"""Tests for AGENT-001: AgentRegistry."""

import pytest

from app.agents.agent_registry import AgentRegistry
from app.agents.base import BaseAgent


class FakeAgent(BaseAgent):
    async def execute(self, task):
        return task

    async def plan(self, task):
        return {}

    async def reflect(self, task, result):
        return {}


@pytest.fixture
def registry():
    return AgentRegistry()


class TestAgentRegistry:
    def test_register_adds_agent(self, registry):
        agent = FakeAgent()
        registry.register("test-agent", agent)
        assert "test-agent" in registry.list_agents()

    def test_register_duplicate_raises(self, registry):
        registry.register("test-agent", FakeAgent())
        with pytest.raises(ValueError, match="already registered"):
            registry.register("test-agent", FakeAgent())

    def test_get_returns_registered_agent(self, registry):
        agent = FakeAgent()
        registry.register("test-agent", agent)
        assert registry.get("test-agent") is agent

    def test_get_missing_raises(self, registry):
        with pytest.raises(KeyError, match="not found"):
            registry.get("nonexistent")

    def test_list_agents_returns_names(self, registry):
        registry.register("a", FakeAgent())
        registry.register("b", FakeAgent())
        names = registry.list_agents()
        assert sorted(names) == ["a", "b"]

    def test_unregister_removes_agent(self, registry):
        agent = FakeAgent()
        registry.register("test-agent", agent)
        registry.unregister("test-agent")
        assert "test-agent" not in registry.list_agents()

    def test_unregister_missing_raises(self, registry):
        with pytest.raises(KeyError, match="not found"):
            registry.unregister("nonexistent")

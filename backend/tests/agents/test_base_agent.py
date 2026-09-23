"""Tests for AGENT-001: BaseAgent interface."""

import pytest

from app.agents.base import BaseAgent


class ConcreteAgent(BaseAgent):
    """Minimal concrete implementation for testing the interface."""
    async def execute(self, task):
        return {"result": "done"}

    async def plan(self, task):
        return {"goal": "test", "steps": []}

    async def reflect(self, task, result):
        return {"ok": True}


class TestBaseAgent:
    def test_cannot_instantiate_base_agent(self):
        with pytest.raises(TypeError):
            BaseAgent()

    def test_can_instantiate_concrete_agent(self):
        agent = ConcreteAgent()
        assert isinstance(agent, BaseAgent)

    @pytest.mark.asyncio
    async def test_execute(self):
        agent = ConcreteAgent()
        result = await agent.execute(None)
        assert result == {"result": "done"}

    @pytest.mark.asyncio
    async def test_plan(self):
        agent = ConcreteAgent()
        plan = await agent.plan(None)
        assert "goal" in plan
        assert "steps" in plan

    @pytest.mark.asyncio
    async def test_reflect(self):
        agent = ConcreteAgent()
        reflection = await agent.reflect(None, None)
        assert reflection == {"ok": True}

import pytest

from app.harness.capability_adapter import CapabilityAgent
from app.harness.task import AgentTask


class FakeCapability:
    async def execute(self, action, **kwargs):
        assert action == "search"
        assert kwargs == {"keyword": "动画"}
        return {
            "success": True,
            "results": [{"id": 1, "name": "作品 A"}],
            "evidence": {"source": "catalog"},
        }


@pytest.mark.asyncio
async def test_capability_adapter_returns_generic_agent_result():
    agent = CapabilityAgent(
        name="anime.search",
        capability=FakeCapability(),
        action="search",
        input_builder=lambda task: {"keyword": task.goal},
    )

    result = await agent.execute(AgentTask(user_id=1, goal="动画"))

    assert result.kind == "capability"
    assert result.name == "anime.search"
    assert result.data["results"] == [{"id": 1, "name": "作品 A"}]
    assert result.evidence == {"source": "catalog"}

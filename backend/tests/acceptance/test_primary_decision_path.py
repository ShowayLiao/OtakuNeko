from __future__ import annotations

import pytest

from app.capabilities.registry import CapabilityRegistry
from app.capabilities.types import ActionDescriptor, CapabilityResult
from app.harness.dispatcher import Dispatcher
from app.harness.model_types import ModelCallResult
from app.harness.runtime import AgentRuntime
from app.harness.task import AgentTask


class FakeReadCapability:
    name = "catalog"
    calls = 0

    def actions(self):
        return [
            ActionDescriptor(
                name="search",
                public_name="catalog.search",
                description="fake read",
                input_schema={"type": "object"},
            )
        ]

    async def execute(self, action: str, **kwargs):
        type(self).calls += 1
        return CapabilityResult.ok(items=["anime-a"]).to_dict()


class FakeModelGateway:
    def __init__(self, decisions: list[dict]):
        self.decisions = iter(decisions)

    async def infer(self, **kwargs) -> ModelCallResult:
        return ModelCallResult(
            provider="fake",
            model="fake-model",
            operation="infer",
            status="completed",
            decision=next(self.decisions),
        )


@pytest.mark.asyncio
async def test_primary_task_path_is_model_decision_policy_dispatch_and_response() -> None:
    capability = FakeReadCapability()
    registry = CapabilityRegistry()
    registry.register(capability)
    dispatcher = Dispatcher(registry)
    gateway = FakeModelGateway(
        [
            {
                "schema_version": "v1",
                "decision_id": "decision-1",
                "run_id": "run-1",
                "action": "invoke",
                "capability": "catalog.search",
                "capability_version": "v1",
                "arguments": {"query": "anime"},
            },
            {
                "schema_version": "v1",
                "decision_id": "decision-2",
                "run_id": "run-1",
                "action": "respond",
                "content": "found anime-a",
            },
        ]
    )

    runtime = AgentRuntime(object(), model_gateway=gateway, dispatcher=dispatcher)
    result = await runtime.execute_decision(
        AgentTask(task_id=1, user_id=7, goal="find anime", metadata={"run_id": "run-1"}),
        capability_allowlist={"catalog.search"},
    )

    assert result.status == "completed"
    assert result.content == "found anime-a"
    assert FakeReadCapability.calls == 1

"""Primary-path acceptance coverage from AgentRuntime to user response."""

from __future__ import annotations

import pytest

from app.capabilities.registry import CapabilityRegistry
from app.capabilities.types import ActionDescriptor, CapabilityResult
from app.harness.dispatcher import Dispatcher
from app.harness.model_types import ModelCallResult
from app.harness.runtime import AgentRuntime
from app.harness.task import AgentTask


class _ReadCapability:
    name = "catalog"

    def __init__(self) -> None:
        self.calls: list[dict] = []

    def actions(self):
        return [
            ActionDescriptor(
                name="search",
                public_name="catalog.search",
                description="Read catalog data",
                input_schema={"type": "object"},
            )
        ]

    async def execute(self, action: str, **kwargs):
        self.calls.append({"action": action, **kwargs})
        return CapabilityResult.ok(items=["anime-a"]).to_dict()


class _DecisionGateway:
    def __init__(self, decisions: list[dict]) -> None:
        self._decisions = iter(decisions)

    async def infer(self, **kwargs) -> ModelCallResult:
        return ModelCallResult(
            provider="fake",
            model="fake-model",
            operation="infer",
            status="completed",
            decision=next(self._decisions),
        )


@pytest.mark.asyncio
async def test_primary_runtime_path_dispatches_and_returns_structured_response() -> None:
    capability = _ReadCapability()
    registry = CapabilityRegistry()
    registry.register(capability)
    dispatcher = Dispatcher(registry)
    runtime = AgentRuntime(
        object(),
        model_gateway=_DecisionGateway(
            [
                {
                    "schema_version": "v1",
                    "decision_id": "decision-1",
                    "run_id": "run-acceptance",
                    "action": "invoke",
                    "capability": "catalog.search",
                    "capability_version": "v1",
                    "arguments": {"query": "anime"},
                },
                {
                    "schema_version": "v1",
                    "decision_id": "decision-2",
                    "run_id": "run-acceptance",
                    "action": "respond",
                    "content": "found anime-a",
                },
            ]
        ),
        dispatcher=dispatcher,
    )

    result = await runtime.execute_decision(
        AgentTask(
            task_id=1,
            user_id=7,
            goal="find anime",
            metadata={"run_id": "run-acceptance"},
        ),
        capability_allowlist={"catalog.search"},
    )

    assert result.status == "completed"
    assert result.content == "found anime-a"
    assert capability.calls == [{"action": "search", "query": "anime"}]
    assert [event.event_type for event in dispatcher.events] == [
        "invocation_start",
        "invocation_end",
    ]
    assert all(event.run_id == "run-acceptance" for event in dispatcher.events)

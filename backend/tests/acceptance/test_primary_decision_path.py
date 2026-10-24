from __future__ import annotations

from collections.abc import AsyncIterator, Sequence
from typing import Any

import pytest

from app.capabilities.base import BaseCapability
from app.capabilities.registry import CapabilityRegistry
from app.capabilities.types import ActionDescriptor, CapabilityResult
from app.harness.dispatcher import Dispatcher
from app.harness.model_gateway import ModelGateway
from app.harness.model_types import ModelCallResult, ModelStreamEvent
from app.harness.result import AgentResult
from app.harness.runtime import AgentRuntime
from app.harness.task import AgentTask


class FakeReadCapability(BaseCapability):
    @property
    def name(self) -> str:
        return "catalog"

    @property
    def description(self) -> str:
        return "fake read"

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

    async def execute(self, action: str, **kwargs: Any) -> dict[str, Any]:
        type(self).calls += 1
        return CapabilityResult.ok(items=["anime-a"]).to_dict()


class FakeModelGateway(ModelGateway):
    def __init__(self, decisions: list[dict]):
        self.decisions = iter(decisions)

    async def infer(self, **kwargs: Any) -> ModelCallResult:
        return ModelCallResult(
            provider="fake",
            model="fake-model",
            operation="infer",
            status="completed",
            decision=next(self.decisions),
        )

    async def stream_infer(self, **kwargs: Any) -> AsyncIterator[ModelStreamEvent]:
        yield ModelStreamEvent(result=await self.infer(**kwargs))

    async def synthesize(
        self,
        *,
        goal: str,
        messages: list[dict[str, Any]],
        results: Sequence[AgentResult | dict[str, Any]],
        **kwargs: Any,
    ) -> str:
        raise AssertionError("synthesis is outside this acceptance path")

    async def synthesize_result(
        self,
        *,
        goal: str,
        messages: list[dict[str, Any]],
        results: Sequence[AgentResult | dict[str, Any]],
        **kwargs: Any,
    ) -> ModelCallResult:
        raise AssertionError("synthesis is outside this acceptance path")


@pytest.mark.asyncio
async def test_primary_task_path_is_model_decision_policy_dispatch_and_response() -> (
    None
):
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

    runtime = AgentRuntime(None, model_gateway=gateway, dispatcher=dispatcher)
    result = await runtime.execute_decision(
        AgentTask(
            task_id=1, user_id=7, goal="find anime", task_metadata={"run_id": "run-1"}
        ),
        capability_allowlist={"catalog.search"},
    )

    assert result.status == "completed"
    assert result.content == "found anime-a"
    assert FakeReadCapability.calls == 1

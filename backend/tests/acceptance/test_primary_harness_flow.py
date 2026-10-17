"""Primary-path acceptance coverage from AgentRuntime to user response."""

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


class _ReadCapability(BaseCapability):
    @property
    def name(self) -> str:
        return "catalog"

    @property
    def description(self) -> str:
        return "Read catalog data"

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

    async def execute(self, action: str, **kwargs: Any) -> dict[str, Any]:
        self.calls.append({"action": action, **kwargs})
        return CapabilityResult.ok(items=["anime-a"]).to_dict()


class _DecisionGateway(ModelGateway):
    def __init__(self, decisions: list[dict]) -> None:
        self._decisions = iter(decisions)

    async def infer(self, **kwargs: Any) -> ModelCallResult:
        return ModelCallResult(
            provider="fake",
            model="fake-model",
            operation="infer",
            status="completed",
            decision=next(self._decisions),
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
async def test_primary_runtime_path_dispatches_and_returns_structured_response() -> (
    None
):
    capability = _ReadCapability()
    registry = CapabilityRegistry()
    registry.register(capability)
    dispatcher = Dispatcher(registry)
    runtime = AgentRuntime(
        None,
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
            task_metadata={"run_id": "run-acceptance"},
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

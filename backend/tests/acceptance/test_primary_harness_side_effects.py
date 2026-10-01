"""Primary Runtime side-effect approval and idempotency acceptance coverage."""

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
from app.harness.policy import Approval, PolicyEngine
from app.harness.runtime import AgentRuntime
from app.harness.task import AgentTask


class _WriteCapability(BaseCapability):
    @property
    def name(self) -> str:
        return "writer"

    @property
    def description(self) -> str:
        return "Write one record"

    def __init__(self) -> None:
        self.calls = 0

    def actions(self):
        return [
            ActionDescriptor(
                name="write",
                public_name="writer.write",
                description="Write one record",
                input_schema={"type": "object"},
                requires_auth=True,
                is_side_effect=True,
                idempotency_mode="required",
            )
        ]

    async def execute(self, action: str, **kwargs: Any) -> dict[str, Any]:
        self.calls += 1
        return CapabilityResult.ok(written=True).to_dict()


class _WriteGateway(ModelGateway):
    async def infer(self, **kwargs: Any) -> ModelCallResult:
        return ModelCallResult(
            provider="fake",
            model="fake-model",
            operation="infer",
            status="completed",
            decision={
                "schema_version": "v1",
                "decision_id": "write-decision",
                "run_id": "run-side-effect",
                "action": "invoke",
                "capability": "writer.write",
                "capability_version": "v1",
                "arguments": {"value": "safe"},
            },
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
async def test_side_effect_fails_closed_without_idempotency_store() -> None:
    capability = _WriteCapability()
    registry = CapabilityRegistry()
    registry.register(capability)
    dispatcher = Dispatcher(
        registry,
        policy_engine=PolicyEngine(allow_side_effects=True),
        approval=Approval(
            approval_id="approval-1",
            principal_id=7,
            action="write",
        ),
    )
    runtime = AgentRuntime(
        None,
        model_gateway=_WriteGateway(),
        dispatcher=dispatcher,
    )

    result = await runtime.execute_decision(
        AgentTask(
            task_id=5,
            user_id=7,
            goal="write",
            task_metadata={"run_id": "run-side-effect"},
        ),
        capability_allowlist={"writer.write"},
    )

    assert result.status == "failed"
    assert result.error_code is not None
    assert result.error_code.value == "tool_error"
    assert capability.calls == 0

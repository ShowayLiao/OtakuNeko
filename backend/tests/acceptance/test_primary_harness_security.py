"""Primary-path security acceptance coverage."""

from __future__ import annotations

from collections.abc import AsyncIterator, Sequence
from typing import Any

import pytest

from app.capabilities.base import BaseCapability
from app.capabilities.registry import CapabilityRegistry
from app.capabilities.types import ActionDescriptor, CapabilityResult
from app.harness.contracts import ErrorCode
from app.harness.dispatcher import Dispatcher
from app.harness.model_gateway import ModelGateway
from app.harness.model_types import ModelCallResult, ModelStreamEvent
from app.harness.result import AgentResult
from app.harness.runtime import AgentRuntime
from app.harness.task import AgentTask


class _SecureCapability(BaseCapability):
    @property
    def name(self) -> str:
        return "secure"

    @property
    def description(self) -> str:
        return "Secure read"

    def __init__(self) -> None:
        self.calls = 0

    def actions(self):
        return [
            ActionDescriptor(
                name="read",
                public_name="secure.read",
                description="Read secure data",
                input_schema={"type": "object"},
            )
        ]

    async def execute(self, action: str, **kwargs: Any) -> dict[str, Any]:
        self.calls += 1
        return CapabilityResult.ok(value="should not be reached").to_dict()


class _OneDecisionGateway(ModelGateway):
    def __init__(self, decision: dict) -> None:
        self.decision = decision

    async def infer(self, **kwargs: Any) -> ModelCallResult:
        return ModelCallResult(
            provider="fake",
            model="fake-model",
            operation="infer",
            status="completed",
            decision=self.decision,
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
async def test_forged_identity_is_rejected_before_capability_execution() -> None:
    capability = _SecureCapability()
    registry = CapabilityRegistry()
    registry.register(capability)
    runtime = AgentRuntime(
        None,
        model_gateway=_OneDecisionGateway(
            {
                "schema_version": "v1",
                "decision_id": "forged",
                "run_id": "run-security",
                "action": "invoke",
                "capability": "secure.read",
                "capability_version": "v1",
                "arguments": {"principal_id": 999},
            }
        ),
        dispatcher=Dispatcher(registry),
    )

    result = await runtime.execute_decision(
        AgentTask(
            task_id=2,
            user_id=7,
            goal="read",
            task_metadata={"run_id": "run-security"},
        ),
        capability_allowlist={"secure.read"},
    )

    assert result.status == "failed"
    # A model-owned authority field is an invalid public Decision at the
    # parser boundary; it must never reach Dispatcher or the capability.
    assert result.error_code == ErrorCode.INVALID_REQUEST
    assert capability.calls == 0

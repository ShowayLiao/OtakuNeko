"""Primary Runtime side-effect approval and idempotency acceptance coverage."""

from __future__ import annotations

import pytest

from app.capabilities.registry import CapabilityRegistry
from app.capabilities.types import ActionDescriptor, CapabilityResult
from app.harness.dispatcher import Dispatcher
from app.harness.model_types import ModelCallResult
from app.harness.policy import Approval, PolicyEngine
from app.harness.runtime import AgentRuntime
from app.harness.task import AgentTask


class _WriteCapability:
    name = "writer"

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

    async def execute(self, action: str, **kwargs):
        self.calls += 1
        return CapabilityResult.ok(written=True).to_dict()


class _WriteGateway:
    async def infer(self, **kwargs) -> ModelCallResult:
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
        object(),
        model_gateway=_WriteGateway(),
        dispatcher=dispatcher,
    )

    result = await runtime.execute_decision(
        AgentTask(
            task_id=5,
            user_id=7,
            goal="write",
            metadata={"run_id": "run-side-effect"},
        ),
        capability_allowlist={"writer.write"},
    )

    assert result.status == "failed"
    assert result.error_code.value == "tool_error"
    assert capability.calls == 0

from __future__ import annotations

from collections.abc import AsyncIterator, Sequence
from typing import Any

from app.capabilities.base import BaseCapability
from app.capabilities.registry import CapabilityRegistry
from app.capabilities.types import ActionDescriptor
from app.harness.contracts import ErrorCode, ExecutionContext
from app.harness.dispatcher import Dispatcher
from app.harness.model_gateway import ModelGateway
from app.harness.model_types import ModelCallResult, ModelStreamEvent
from app.harness.result import AgentResult
from app.harness.runtime import AgentRuntime
from app.harness.task import AgentTask


class BoundaryCapability(BaseCapability):
    calls: list[tuple[str, dict]] = []

    @property
    def name(self) -> str:
        return "boundary"

    @property
    def description(self) -> str:
        return "boundary test capability"

    def actions(self) -> list[ActionDescriptor]:
        return [
            ActionDescriptor(
                name="read_data",
                public_name="read_data",
                description="Read scoped data",
                requires_auth=True,
                input_schema={"type": "object", "properties": {}},
            ),
            ActionDescriptor(
                name="write_data",
                public_name="write_data",
                description="Write scoped data",
                requires_auth=True,
                is_side_effect=True,
                input_schema={
                    "type": "object",
                    "properties": {"value": {"type": "string"}},
                },
            ),
        ]

    async def execute(self, action: str, **kwargs):
        self.calls.append((action, kwargs))
        return {"success": True, "action": action}


class DecisionGateway(ModelGateway):
    def __init__(self, decision: dict):
        self.decision = decision

    async def infer(self, **kwargs: Any) -> ModelCallResult:
        return ModelCallResult(
            provider="fake",
            model="fake",
            operation="decision",
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
        raise AssertionError("boundary test must use structured decisions")

    async def synthesize_result(
        self,
        *,
        goal: str,
        messages: list[dict[str, Any]],
        results: Sequence[AgentResult | dict[str, Any]],
        **kwargs: Any,
    ) -> ModelCallResult:
        raise AssertionError("boundary test must use structured decisions")


def _task() -> AgentTask:
    return AgentTask(
        task_id=101,
        user_id=7,
        goal="boundary",
        task_metadata={"run_id": "boundary-run"},
    )


def _registry() -> tuple[CapabilityRegistry, BoundaryCapability]:
    capability = BoundaryCapability()
    registry = CapabilityRegistry()
    registry.register(capability)
    return registry, capability


async def test_runtime_rejects_model_owned_identity_before_domain_service() -> None:
    registry, capability = _registry()
    runtime = AgentRuntime(
        None,
        model_gateway=DecisionGateway(
            {
                "schema_version": "v1",
                "decision_id": "decision-identity",
                "run_id": "boundary-run",
                "action": "invoke",
                "capability": "read_data",
                "capability_version": "v1",
                "arguments": {"user_id": 8},
            }
        ),
        dispatcher=Dispatcher(registry),
    )

    result = await runtime.execute_decision(
        _task(),
        context=ExecutionContext(
            principal_id=7,
            run_id="boundary-run",
            trace_id="boundary-trace",
            capability_allowlist=frozenset({"read_data"}),
        ),
    )

    assert result.error_code == ErrorCode.INVALID_REQUEST
    assert capability.calls == []


async def test_runtime_fails_closed_for_unapproved_side_effect() -> None:
    registry, capability = _registry()
    runtime = AgentRuntime(
        None,
        model_gateway=DecisionGateway(
            {
                "schema_version": "v1",
                "decision_id": "decision-write",
                "run_id": "boundary-run",
                "action": "invoke",
                "capability": "write_data",
                "capability_version": "v1",
                "arguments": {"value": "x", "idempotency_key": "write-1"},
            }
        ),
        dispatcher=Dispatcher(registry),
    )

    result = await runtime.execute_decision(
        _task(),
        context=ExecutionContext(
            principal_id=7,
            run_id="boundary-run",
            trace_id="boundary-trace",
            capability_allowlist=frozenset({"write_data"}),
        ),
    )

    assert result.error_code == ErrorCode.TOOL_ERROR
    assert capability.calls == []

from __future__ import annotations

import asyncio

import pytest

from app.capabilities.registry import CapabilityRegistry
from app.capabilities.types import ActionDescriptor, CapabilityResult
from app.harness.budget import CancellationToken
from app.harness.contracts import AgentDecision, ExecutionContext
from app.harness.dispatcher import Dispatcher
from app.harness.policy import Approval, PolicyEngine


class FakeCapability:
    name = "catalog"

    def __init__(self, *, side_effect: bool = False, fail: bool = False) -> None:
        self.calls: list[dict] = []
        self.fail = fail
        self._descriptor = ActionDescriptor(
            name="search" if not side_effect else "write",
            public_name="catalog.search" if not side_effect else "catalog.write",
            description="fake capability",
            input_schema={"type": "object", "properties": {}},
            requires_auth=side_effect,
            is_side_effect=side_effect,
            idempotency_mode="required" if side_effect else "none",
        )

    def actions(self):
        return [self._descriptor]

    async def execute(self, action: str, **kwargs):
        self.calls.append({"action": action, **kwargs})
        if self.fail:
            raise RuntimeError("secret provider failure")
        return CapabilityResult.ok(items=[{"title": "A"}]).to_dict()


def _context() -> ExecutionContext:
    return ExecutionContext(
        principal_id=7,
        run_id="run-1",
        trace_id="trace-1",
        capability_allowlist=frozenset({"catalog.search", "catalog.write"}),
    )


def _decision(capability: str, version: str = "v1", arguments: dict | None = None):
    return AgentDecision(
        decision_id="decision-1",
        run_id="run-1",
        action="invoke",
        capability=capability,
        capability_version=version,
        arguments=arguments or {},
    )


@pytest.mark.asyncio
async def test_dispatcher_uses_registry_and_emits_one_invocation_identity() -> None:
    capability = FakeCapability()
    registry = CapabilityRegistry()
    registry.register(capability)
    dispatcher = Dispatcher(registry)

    result = await dispatcher.dispatch(_decision("catalog.search"), _context())

    assert result.status == "succeeded"
    assert result.output["items"] == [{"title": "A"}]
    assert len(dispatcher.events) == 2
    assert dispatcher.events[0].event_type == "invocation_start"
    assert dispatcher.events[1].event_type == "invocation_end"
    assert dispatcher.events[0].invocation_id == dispatcher.events[1].invocation_id
    assert capability.calls == [{"action": "search"}]


@pytest.mark.asyncio
async def test_missing_capability_and_policy_deny_never_call_service() -> None:
    capability = FakeCapability(side_effect=True)
    registry = CapabilityRegistry()
    registry.register(capability)
    dispatcher = Dispatcher(registry, policy_engine=PolicyEngine(allow_side_effects=False))

    missing = await dispatcher.dispatch(_decision("catalog.missing"), _context())
    denied = await dispatcher.dispatch(_decision("catalog.write"), _context())

    assert missing.output["error_type"] == "not_configured"
    assert denied.output["error_type"] == "policy_denied"
    assert capability.calls == []


@pytest.mark.asyncio
async def test_side_effect_requires_approval_and_idempotency() -> None:
    capability = FakeCapability(side_effect=True)
    registry = CapabilityRegistry()
    registry.register(capability)
    dispatcher = Dispatcher(
        registry,
        policy_engine=PolicyEngine(allow_side_effects=True),
        approval=Approval(approval_id="approval-1", principal_id=7, action="write"),
    )

    result = await dispatcher.dispatch(
        _decision("catalog.write", arguments={"idempotency_key": "key-1"}),
        _context(),
    )

    assert result.status == "denied"
    assert result.output["error_type"] == "idempotency_required"
    assert capability.calls == []


@pytest.mark.asyncio
async def test_failure_is_normalized_and_model_cannot_override_identity() -> None:
    capability = FakeCapability(fail=True)
    registry = CapabilityRegistry()
    registry.register(capability)
    dispatcher = Dispatcher(registry)

    forged = AgentDecision.model_construct(
        decision_id="decision-1",
        run_id="run-1",
        action="invoke",
        capability="catalog.search",
        capability_version="v1",
        arguments={"user_id": 999},
    )
    result = await dispatcher.dispatch(forged, _context())

    assert result.status == "denied"
    assert result.output["error_type"] == "identity_spoofing"
    assert capability.calls == []

    failed = await dispatcher.dispatch(_decision("catalog.search"), _context())
    assert failed.status == "failed"
    assert failed.output["error_type"] == "internal"
    assert "secret provider failure" not in str(failed.output)


@pytest.mark.asyncio
async def test_timeout_and_cancellation_reach_dispatch_boundary() -> None:
    capability = FakeCapability()
    capability._descriptor = ActionDescriptor(
        name="search",
        public_name="catalog.search",
        description="slow fake capability",
        input_schema={"type": "object"},
        timeout_seconds=0.01,
    )

    async def slow_execute(action: str, **kwargs):
        await asyncio.sleep(1)
        return {"success": True}

    capability.execute = slow_execute
    registry = CapabilityRegistry()
    registry.register(capability)
    dispatcher = Dispatcher(registry)

    result = await dispatcher.dispatch(_decision("catalog.search"), _context())
    assert result.status == "timeout"

    token = CancellationToken()
    token.cancel()
    cancelled = await dispatcher.dispatch(
        _decision("catalog.search"), _context(), cancellation=token
    )
    assert cancelled.status == "cancelled"

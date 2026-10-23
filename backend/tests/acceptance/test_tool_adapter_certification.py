"""Certification for the Capability -> LangChain tool adapter boundary."""

from __future__ import annotations

from typing import Any

import pytest

from app.harness.authority import RUNTIME_OWNED_FIELDS
from app.harness.contracts import ErrorCode, ExecutionContext, InvocationResult
from tests.acceptance.exposure_support import (
    RecordingReadCapability,
    RecordingWriteCapability,
    authority_extra_properties,
)


def _tool_for(capability, **kwargs):
    from app.capabilities.langchain_adapter import _build_runtime_tool

    return _build_runtime_tool(capability, capability.actions()[0], **kwargs)


def test_tool_adapter_strips_all_runtime_owned_fields_from_public_schema():
    capability = RecordingReadCapability(extra_properties=authority_extra_properties())
    tool = _tool_for(capability)
    schema = tool.args_schema.model_json_schema()

    assert "value" in schema["properties"]
    assert not set(schema["properties"]) & RUNTIME_OWNED_FIELDS
    assert not set(schema.get("required", ())) & RUNTIME_OWNED_FIELDS


@pytest.mark.asyncio
async def test_tool_adapter_authenticated_read_uses_dispatcher(monkeypatch):
    capability = RecordingReadCapability(requires_auth=True)
    descriptor = capability.actions()[0]
    public_name = descriptor.public_name
    assert public_name is not None

    import app.capabilities.langchain_adapter as adapter_module

    dispatches: list[Any] = []

    class RecordingDispatcher(adapter_module.Dispatcher):
        async def dispatch(self, decision, context, **kwargs):
            dispatches.append((decision, context))
            return await super().dispatch(decision, context, **kwargs)

    monkeypatch.setattr(adapter_module, "Dispatcher", RecordingDispatcher)
    context = ExecutionContext(
        principal_id=7,
        run_id="tool-run",
        trace_id="tool-trace",
        capability_allowlist=frozenset({public_name}),
    )
    tool = _tool_for(capability, context=context)

    result = await tool.ainvoke({"value": "x"})

    assert result == {"success": True, "data": {"value": "x"}}
    assert capability.calls == [{"value": "x", "user_id": 7}]
    assert len(dispatches) == 1
    decision, dispatched_context = dispatches[0]
    assert decision.capability == public_name
    assert dispatched_context.principal_id == 7


@pytest.mark.asyncio
async def test_tool_adapter_public_read_without_context_still_uses_dispatcher(
    monkeypatch,
):
    capability = RecordingReadCapability(requires_auth=False)
    descriptor = capability.actions()[0]
    public_name = descriptor.public_name
    assert public_name is not None

    import app.capabilities.langchain_adapter as adapter_module

    dispatches: list[Any] = []

    class RecordingDispatcher(adapter_module.Dispatcher):
        async def dispatch(self, decision, context, **kwargs):
            dispatches.append(decision)
            return await super().dispatch(decision, context, **kwargs)

    monkeypatch.setattr(adapter_module, "Dispatcher", RecordingDispatcher)
    tool = _tool_for(capability)

    result = await tool.ainvoke({"value": "x"})

    assert result == {"success": True, "data": {"value": "x"}}
    assert capability.calls == [{"value": "x"}]
    assert len(dispatches) == 1
    assert dispatches[0].capability == public_name


@pytest.mark.asyncio
async def test_tool_adapter_auth_required_read_without_context_fails_closed():
    capability = RecordingReadCapability(requires_auth=True)
    tool = _tool_for(capability)

    result = await tool.ainvoke({"value": "x"})

    assert result["success"] is False
    assert result["error_type"] == "unauthorized"
    assert capability.calls == []


@pytest.mark.asyncio
async def test_tool_adapter_supplied_adapter_is_used_through_dispatcher(monkeypatch):
    capability = RecordingReadCapability(requires_auth=False)

    import app.capabilities.langchain_adapter as adapter_module

    dispatches: list[Any] = []

    class RecordingDispatcher(adapter_module.Dispatcher):
        async def dispatch(self, decision, context, **kwargs):
            dispatches.append(decision)
            return await super().dispatch(decision, context, **kwargs)

    monkeypatch.setattr(adapter_module, "Dispatcher", RecordingDispatcher)

    class RecordingAdapter:
        def __init__(self) -> None:
            self.calls = 0

        async def execute(self, context, action, arguments):
            self.calls += 1
            return {"success": True, "value": "adapter"}

    adapter = RecordingAdapter()
    tool = _tool_for(capability, capability_adapter=adapter)

    result = await tool.ainvoke({"value": "x"})

    assert result == {"success": True, "data": {"value": "adapter"}}
    assert adapter.calls == 1
    assert capability.calls == []
    assert len(dispatches) == 1


@pytest.mark.asyncio
async def test_tool_adapter_side_effect_without_runtime_fails_closed():
    capability = RecordingWriteCapability()
    tool = _tool_for(capability)

    result = await tool.ainvoke({"value": "x"})

    assert result["success"] is False
    assert result["error_type"] == "dispatcher_required"
    assert capability.calls == []


@pytest.mark.asyncio
async def test_tool_adapter_omits_unset_optional_fields():
    capability = RecordingReadCapability(
        requires_auth=False,
        extra_properties={"note": {"type": "string"}},
    )
    tool = _tool_for(capability)

    result = await tool.ainvoke({"value": "x"})

    assert result == {"success": True, "data": {"value": "x"}}
    assert capability.calls == [{"value": "x"}]


@pytest.mark.asyncio
async def test_tool_adapter_does_not_forward_forged_authority_fields():
    capability = RecordingReadCapability(
        requires_auth=False,
        extra_properties=authority_extra_properties(),
    )
    tool = _tool_for(capability)
    assert tool.coroutine is not None

    result = await tool.coroutine(value="x", tenant_id="forged-tenant")

    assert result == {"success": True, "data": {"value": "x"}}
    assert capability.calls == [{"value": "x"}]
    assert all("tenant_id" not in call for call in capability.calls)


@pytest.mark.asyncio
async def test_tool_adapter_rejects_nested_authority_fields_instead_of_corrupting():
    capability = RecordingReadCapability(
        requires_auth=False,
        extra_properties={"payload": {"type": "object"}},
    )
    tool = _tool_for(capability)

    result = await tool.ainvoke(
        {"value": "x", "payload": {"role": "admin", "name": "keep"}}
    )

    assert result["success"] is False
    assert result["error_type"] == "identity_spoofing"
    assert capability.calls == []


@pytest.mark.asyncio
async def test_tool_adapter_omits_none_for_anyof_optional_fields():
    capability = RecordingReadCapability(
        requires_auth=False,
        extra_properties={"note": {"anyOf": [{"type": "string"}]}},
    )
    tool = _tool_for(capability)

    result = await tool.ainvoke({"value": "x"})

    assert result == {"success": True, "data": {"value": "x"}}
    assert capability.calls == [{"value": "x"}]


@pytest.mark.asyncio
async def test_tool_adapter_renders_enum_error_codes(monkeypatch):
    capability = RecordingReadCapability(requires_auth=False)

    import app.capabilities.langchain_adapter as adapter_module

    class DeniedDispatcher:
        def __init__(self, *args, **kwargs):
            pass

        async def dispatch(self, decision, context, **kwargs):
            return InvocationResult(
                invocation_id=decision.decision_id,
                status="denied",
                error_code=ErrorCode.POLICY_DENIED,
                output={},
            )

    monkeypatch.setattr(adapter_module, "Dispatcher", DeniedDispatcher)
    tool = _tool_for(capability)

    result = await tool.ainvoke({"value": "x"})

    assert result["success"] is False
    assert result["error_type"] == "policy_denied"
    assert capability.calls == []

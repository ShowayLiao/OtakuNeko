"""Certification for the MCP exposure entry and its Dispatcher boundary."""

from __future__ import annotations

import asyncio
import json
import logging
from contextlib import asynccontextmanager
from typing import Any

import pytest

from app.capabilities.registry import CapabilityRegistry
from app.harness.authority import RUNTIME_OWNED_FIELDS
from app.mcp_server import ExposureMap, MCPServer
from app.mcp_server.context import MCPContext
from app.mcp_server.policy import Policy
from tests.acceptance.exposure_support import (
    RecordingReadCapability,
    RecordingWriteCapability,
    authority_extra_properties,
)
from tests.capabilities.contracts.system_support import capture_application_logs

_PRIVATE = "mcp-exposure-private-sentinel"


def _server(capability, *, extra=()):
    registry = CapabilityRegistry()
    registry.register(capability)
    for item in extra:
        registry.register(item)
    exposure = ExposureMap(
        {capability.name: [action.name for action in capability.actions()]}
    )
    return MCPServer(registry, exposure)


def _tool_name(capability) -> str:
    descriptor = capability.actions()[0]
    return f"{capability.name}_{descriptor.name}"


@pytest.mark.asyncio
async def test_mcp_read_uses_real_dispatcher_and_trusted_identity(monkeypatch):
    capability = RecordingReadCapability(requires_auth=True)
    server = _server(capability)

    import app.mcp_server as mcp_module

    dispatches: list[tuple[Any, Any]] = []

    class RecordingDispatcher(mcp_module.Dispatcher):
        async def dispatch(self, decision, context, **kwargs):
            dispatches.append((decision, context))
            return await super().dispatch(decision, context, **kwargs)

    monkeypatch.setattr(mcp_module, "Dispatcher", RecordingDispatcher)

    result = await server.call_tool(
        _tool_name(capability),
        {"value": "x"},
        context=MCPContext(user_id=7),
    )

    assert result == {"success": True, "data": {"value": "x"}}
    assert capability.calls == [{"value": "x", "user_id": 7}]
    assert len(dispatches) == 1
    decision, context = dispatches[0]
    assert decision.capability == capability.actions()[0].public_name
    assert context.principal_id == 7


@pytest.mark.asyncio
async def test_mcp_exposes_only_allowlisted_actions():
    capability = RecordingReadCapability()
    hidden = RecordingReadCapability(
        name="hidden",
        action="secret",
        public_name="hidden_secret",
        requires_auth=False,
    )
    server = _server(capability, extra=(hidden,))

    names = {tool["name"] for tool in server.list_tools()}
    assert names == {_tool_name(capability)}

    unknown = await server.call_tool("hidden_secret", {})
    assert unknown["success"] is False
    assert unknown["error_type"] == "not_found"
    assert hidden.calls == []


@pytest.mark.asyncio
@pytest.mark.parametrize("field", sorted(RUNTIME_OWNED_FIELDS))
async def test_mcp_rejects_model_supplied_authority_fields(field: str):
    capability = RecordingReadCapability(
        requires_auth=True,
        extra_properties=authority_extra_properties(),
    )
    server = _server(capability)

    result = await server.call_tool(
        _tool_name(capability),
        {"value": "x", field: "forged"},
        context=MCPContext(user_id=7),
    )

    assert result["success"] is False
    assert result["error_type"] == "invalid_args"
    assert capability.calls == []


@pytest.mark.asyncio
async def test_mcp_rejects_nested_runtime_owned_authority_fields():
    capability = RecordingReadCapability(requires_auth=True)
    server = _server(capability)

    result = await server.call_tool(
        _tool_name(capability),
        {"value": "x", "nested": {"user_id": 999}},
        context=MCPContext(user_id=7),
    )

    assert result["success"] is False
    assert result["error_type"] == "invalid_args"
    assert capability.calls == []


@pytest.mark.asyncio
async def test_mcp_anonymous_auth_required_and_side_effect_policy_fail_closed():
    read = RecordingReadCapability(requires_auth=True)
    write = RecordingWriteCapability(name="synthetic_write")
    registry = CapabilityRegistry()
    registry.register(read)
    registry.register(write)
    server = MCPServer(
        registry,
        ExposureMap({read.name: [read.actions()[0].name], write.name: ["append"]}),
    )

    anonymous = await server.call_tool(_tool_name(read), {"value": "x"})
    assert anonymous["success"] is False
    assert anonymous["error_type"] == "unauthorized"
    assert read.calls == []

    no_policy = await server.call_tool(
        _tool_name(write), {"value": "x"}, context=MCPContext(user_id=7)
    )
    assert no_policy["success"] is False
    assert no_policy["error_type"] == "policy_denied"
    assert write.calls == []


@pytest.mark.asyncio
async def test_mcp_side_effect_replay_is_idempotent_and_conflict_is_rejected():
    capability = RecordingWriteCapability()
    server = _server(capability)
    context = MCPContext(user_id=7)
    policy = Policy(allow_side_effects=True, idempotency_key="mcp-replay")

    first = await server.call_tool(
        _tool_name(capability), {"value": "x"}, context, policy
    )
    replay = await server.call_tool(
        _tool_name(capability), {"value": "x"}, context, policy
    )
    conflict = await server.call_tool(
        _tool_name(capability), {"value": "y"}, context, policy
    )

    assert first == replay
    assert first["success"] is True
    assert conflict["success"] is False
    assert conflict["error_type"] == "idempotency_conflict"
    assert len(capability.calls) == 1


@pytest.mark.asyncio
async def test_mcp_capability_exception_is_sanitized_and_not_logged(
    caplog, monkeypatch
):
    capability = RecordingReadCapability(requires_auth=False)
    server = _server(capability)

    async def failing_execute(action, **kwargs):
        raise RuntimeError(_PRIVATE)

    monkeypatch.setattr(capability, "execute", failing_execute)

    with capture_application_logs(caplog):
        logging.getLogger("app.mcp_server").warning("mcp-log-capture-probe")
        result = await server.call_tool(_tool_name(capability), {"value": "x"})
        assert "mcp-log-capture-probe" in caplog.text

    assert result["success"] is False
    assert result["error_type"] == "internal"
    assert result["error"] == "Tool execution failed"
    assert result["data"]["message"] == "Capability execution failed"
    assert _PRIVATE not in json.dumps(result, ensure_ascii=False)
    assert _PRIVATE not in caplog.text
    assert all(_PRIVATE not in repr(record.exc_info) for record in caplog.records)


@pytest.mark.asyncio
async def test_mcp_boundary_exception_is_sanitized_and_not_logged(caplog, monkeypatch):
    capability = RecordingReadCapability(requires_auth=False)
    server = _server(capability)

    @asynccontextmanager
    async def failing_scope(_context):
        raise RuntimeError(_PRIVATE)
        yield {}

    monkeypatch.setattr(server, "_dependency_scope", failing_scope)

    with capture_application_logs(caplog):
        logging.getLogger("app.mcp_server").warning("mcp-log-capture-probe")
        result = await server.call_tool(_tool_name(capability), {"value": "x"})
        assert "mcp-log-capture-probe" in caplog.text

    assert result == {
        "success": False,
        "data": {},
        "error_type": "internal",
        "error": "Tool execution failed",
    }
    assert _PRIVATE not in json.dumps(result, ensure_ascii=False)
    assert _PRIVATE not in caplog.text
    assert all(_PRIVATE not in repr(record.exc_info) for record in caplog.records)


@pytest.mark.asyncio
@pytest.mark.parametrize("user_id", [True, 0, -1, "7"])
async def test_mcp_rejects_invalid_trusted_principal(user_id):
    capability = RecordingReadCapability(requires_auth=True)
    server = _server(capability)

    result = await server.call_tool(
        _tool_name(capability),
        {"value": "x"},
        context=MCPContext(user_id=user_id),
    )

    assert result["success"] is False
    assert result["error_type"] in {"unauthorized", "invalid_args"}
    assert capability.calls == []


@pytest.mark.asyncio
async def test_mcp_concurrent_reads_get_unique_invocation_identity(monkeypatch):
    capability = RecordingReadCapability(requires_auth=False)
    server = _server(capability)

    import app.mcp_server as mcp_module

    dispatches: list[tuple[Any, Any]] = []

    class RecordingDispatcher(mcp_module.Dispatcher):
        async def dispatch(self, decision, context, **kwargs):
            dispatches.append((decision, context))
            return await super().dispatch(decision, context, **kwargs)

    monkeypatch.setattr(mcp_module, "Dispatcher", RecordingDispatcher)

    results = await asyncio.gather(
        server.call_tool(_tool_name(capability), {"value": "a"}),
        server.call_tool(_tool_name(capability), {"value": "b"}),
    )

    assert all(result["success"] is True for result in results)
    assert len({decision.decision_id for decision, _ in dispatches}) == 2
    assert len({context.run_id for _, context in dispatches}) == 2


@pytest.mark.asyncio
async def test_mcp_tools_call_keeps_json_rpc_envelope_and_safe_text():
    capability = RecordingReadCapability(requires_auth=False)
    server = _server(capability)

    response = await server.handle_request(
        {
            "jsonrpc": "2.0",
            "id": 9,
            "method": "tools/call",
            "params": {"name": _tool_name(capability), "arguments": {"value": "x"}},
        }
    )

    assert response is not None
    assert response["id"] == 9
    assert response["result"]["isError"] is False
    payload = json.loads(response["result"]["content"][0]["text"])
    assert payload == {"success": True, "data": {"value": "x"}}

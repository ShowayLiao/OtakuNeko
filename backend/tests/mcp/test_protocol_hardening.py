"""Protocol edge-case tests required by MCP-002."""

from __future__ import annotations

import asyncio
import json

import pytest

from app.capabilities.anime import AnimeCapability
from app.capabilities.registry import CapabilityRegistry
from app.mcp_server import ExposureMap, MCPServer, StdioServer


def _server() -> MCPServer:
    registry = CapabilityRegistry()
    registry.register(AnimeCapability())
    return MCPServer(registry, ExposureMap({"anime": ["search"]}))


@pytest.mark.asyncio
async def test_initialized_notification_has_no_response():
    response = await _server().handle_request({
        "jsonrpc": "2.0",
        "method": "notifications/initialized",
    })

    assert response is None


@pytest.mark.asyncio
async def test_invalid_request_returns_json_rpc_error():
    response = await _server().handle_request({"jsonrpc": "2.0", "id": 1})

    assert response["error"]["code"] == -32600


@pytest.mark.asyncio
async def test_invalid_tool_arguments_return_protocol_error():
    response = await _server().handle_request({
        "jsonrpc": "2.0",
        "id": 2,
        "method": "tools/call",
        "params": {"name": "anime_search", "arguments": {}},
    })

    assert response["error"]["code"] == -32602


@pytest.mark.asyncio
async def test_unknown_tool_returns_protocol_error():
    response = await _server().handle_request({
        "jsonrpc": "2.0",
        "id": 3,
        "method": "tools/call",
        "params": {"name": "missing", "arguments": {}},
    })

    assert response["error"]["code"] == -32602


@pytest.mark.asyncio
async def test_failed_capability_result_sets_is_error(monkeypatch):
    server = _server()

    async def fail(action_name, **kwargs):
        return {"success": False, "error": "upstream failed", "error_type": "upstream"}

    monkeypatch.setattr(server._registry.get("anime"), "execute", fail)
    response = await server.handle_request({
        "jsonrpc": "2.0",
        "id": 4,
        "method": "tools/call",
        "params": {"name": "anime_search", "arguments": {"keyword": "x"}},
    })

    assert response["result"]["isError"] is True


@pytest.mark.asyncio
async def test_oversized_tool_result_remains_valid_json(monkeypatch):
    import app.mcp_server as module

    server = _server()

    async def large(action_name, **kwargs):
        return {"success": True, "data": "x" * 200}

    monkeypatch.setattr(server._registry.get("anime"), "execute", large)
    monkeypatch.setattr(module, "MAX_RESPONSE_SIZE", 100)
    response = await server.handle_request({
        "jsonrpc": "2.0",
        "id": 5,
        "method": "tools/call",
        "params": {"name": "anime_search", "arguments": {"keyword": "x"}},
    })

    content = json.loads(response["result"]["content"][0]["text"])
    assert response["result"]["isError"] is True
    assert content["error_type"] == "response_too_large"


@pytest.mark.asyncio
async def test_cancellation_stops_in_flight_request():
    stdio = StdioServer(_server())
    started = asyncio.Event()
    cancelled = asyncio.Event()

    async def slow_call():
        try:
            started.set()
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            cancelled.set()
            raise

    task = asyncio.create_task(slow_call())
    stdio._pending_requests[7] = task
    await started.wait()

    invalid = {
        "method": "notifications/cancelled",
        "params": {"requestId": 7},
    }
    assert stdio.handle_cancellation(invalid) is False
    assert task.cancelled() is False

    valid = {
        "jsonrpc": "2.0",
        "method": "notifications/cancelled",
        "params": {"requestId": 7},
    }
    assert stdio.handle_cancellation(valid) is True
    await asyncio.sleep(0)

    assert task.cancelled()
    assert cancelled.is_set()

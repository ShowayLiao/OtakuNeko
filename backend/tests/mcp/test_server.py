"""Tests for the MCP server wrapping AnimeCapability."""

from __future__ import annotations

import json
import pytest

from app.capabilities.anime import AnimeCapability
from app.capabilities.registry import CapabilityRegistry
from app.mcp_server import MCPServer, _build_tool_schema
from app.capabilities.recommendation import RecommendationCapability
from app.capabilities.schedule import ScheduleCapability


class TestMCPToolSchema:
    """Verify tool schemas generated from capabilities."""

    def test_search_schema_has_required_fields(self):
        cap = AnimeCapability()
        schema = _build_tool_schema(cap, "search")

        assert schema["name"] == "anime_search"
        assert "description" in schema
        assert "inputSchema" in schema
        assert schema["inputSchema"]["type"] == "object"

    def test_get_detail_schema_requires_subject_id(self):
        cap = AnimeCapability()
        schema = _build_tool_schema(cap, "get_detail")

        assert "subject_id" in schema["inputSchema"]["required"]

    def test_get_staff_schema(self):
        cap = AnimeCapability()
        schema = _build_tool_schema(cap, "get_staff")
        assert schema["name"] == "anime_get_staff"

    def test_get_cast_schema(self):
        cap = AnimeCapability()
        schema = _build_tool_schema(cap, "get_cast")
        assert schema["name"] == "anime_get_cast"

    def test_get_reviews_schema(self):
        cap = AnimeCapability()
        schema = _build_tool_schema(cap, "get_reviews")
        assert schema["name"] == "anime_get_reviews"


class TestMCPServer:
    """Test the MCP server protocol handling."""

    def _make_server(self) -> MCPServer:
        registry = CapabilityRegistry()
        registry.register(AnimeCapability())
        return MCPServer(registry)

    def test_list_tools_returns_five_tools(self):
        server = self._make_server()
        tools = server.list_tools()
        assert len(tools) == 5
        names = {t["name"] for t in tools}
        assert names == {
            "anime_search",
            "anime_get_detail",
            "anime_get_staff",
            "anime_get_cast",
            "anime_get_reviews",
        }

    @pytest.mark.asyncio
    async def test_handle_initialize(self):
        server = self._make_server()
        resp = await server.handle_request({
            "jsonrpc": "2.0", "id": 1, "method": "initialize",
            "params": {"protocolVersion": "2024-11-05", "capabilities": {}},
        })
        assert resp["result"]["protocolVersion"] == "2024-11-05"
        assert "tools" in resp["result"]["capabilities"]

    @pytest.mark.asyncio
    async def test_handle_tools_list(self):
        server = self._make_server()
        resp = await server.handle_request({
            "jsonrpc": "2.0", "id": 2, "method": "tools/list",
        })
        assert len(resp["result"]["tools"]) == 5

    @pytest.mark.asyncio
    async def test_handle_unknown_method(self):
        server = self._make_server()
        resp = await server.handle_request({
            "jsonrpc": "2.0", "id": 9, "method": "bogus/method",
        })
        assert "error" in resp
        assert resp["error"]["code"] == -32601

    @pytest.mark.asyncio
    async def test_call_unknown_tool_returns_error(self):
        server = self._make_server()
        result = await server.call_tool("nonexistent_tool", {})
        assert result["success"] is False

    @pytest.mark.asyncio
    async def test_handle_tools_call_unknown(self):
        server = self._make_server()
        resp = await server.handle_request({
            "jsonrpc": "2.0", "id": 3, "method": "tools/call",
            "params": {"name": "bogus", "arguments": {}},
        })
        content = resp["result"]["content"][0]["text"]
        inner = json.loads(content)
        assert inner["success"] is False

    @pytest.mark.asyncio
    async def test_handle_notifications_initialized(self):
        server = self._make_server()
        resp = await server.handle_request({
            "jsonrpc": "2.0", "id": 4, "method": "notifications/initialized",
        })
        assert resp["result"] == {}

    @pytest.mark.asyncio
    async def test_protected_actions_require_mcp_auth_context(self):
        registry = CapabilityRegistry()
        registry.register(RecommendationCapability())
        server = MCPServer(registry)

        result = await server.call_tool(
            "recommendation_generate_profile", {"collections": []}
        )

        assert result["success"] is False
        assert result["error_type"] == "unauthorized"

    @pytest.mark.asyncio
    async def test_side_effecting_actions_require_mcp_policy_context(self):
        registry = CapabilityRegistry()
        registry.register(ScheduleCapability())
        server = MCPServer(registry)

        result = await server.call_tool("schedule_create_schedule", {})

        assert result["success"] is False
        assert result["error_type"] == "policy_denied"

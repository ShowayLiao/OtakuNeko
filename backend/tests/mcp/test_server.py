"""Tests for the MCP server wrapping AnimeCapability."""

from __future__ import annotations

import json
import pytest

from app.capabilities.anime import AnimeCapability
from app.capabilities.registry import CapabilityRegistry
from app.mcp_server import MCPServer, ExposureMap, _build_tool_schema
from app.capabilities.recommendation import RecommendationCapability
from app.capabilities.schedule import ScheduleCapability


_ANIME_ACTIONS = [
    "search", "get_detail", "get_staff", "get_cast", "get_reviews",
]


def _anime_exposure() -> ExposureMap:
    return ExposureMap({"anime": _ANIME_ACTIONS})


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

    def _make_server(self, exposure: ExposureMap | None = None) -> MCPServer:
        registry = CapabilityRegistry()
        registry.register(AnimeCapability())
        return MCPServer(registry, exposure or _anime_exposure())

    def test_list_tools_returns_anime_only_tools(self):
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

    def test_exposure_filters_actions(self):
        """Only actions in the exposure map are listed."""
        registry = CapabilityRegistry()
        registry.register(AnimeCapability())
        exposure = ExposureMap({"anime": ["search", "get_detail"]})
        server = MCPServer(registry, exposure)
        tools = server.list_tools()
        names = {t["name"] for t in tools}
        assert names == {"anime_search", "anime_get_detail"}

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
        assert resp["error"]["code"] == -32602

    @pytest.mark.asyncio
    async def test_handle_tools_call_routes_known_action(self, monkeypatch):
        capability = AnimeCapability()
        registry = CapabilityRegistry()
        registry.register(capability)
        server = MCPServer(registry, _anime_exposure())

        async def execute(action_name, **arguments):
            assert action_name == "search"
            assert arguments == {"keyword": "Frieren"}
            return {"success": True, "data": {"items": []}}

        monkeypatch.setattr(capability, "execute", execute)

        resp = await server.handle_request({
            "jsonrpc": "2.0", "id": 4, "method": "tools/call",
            "params": {
                "name": "anime_search",
                "arguments": {"keyword": "Frieren"},
            },
        })

        content = resp["result"]["content"][0]["text"]
        assert json.loads(content) == {
            "success": True,
            "data": {"items": []},
        }

    @pytest.mark.asyncio
    async def test_handle_notifications_initialized(self):
        server = self._make_server()
        resp = await server.handle_request({
            "jsonrpc": "2.0", "method": "notifications/initialized",
        })
        assert resp is None

    @pytest.mark.asyncio
    async def test_protected_actions_require_authentication(self):
        """Auth-required actions are denied without MCPContext."""
        registry = CapabilityRegistry()
        registry.register(RecommendationCapability())
        server = MCPServer(
            registry,
            ExposureMap({"recommendation": ["generate_profile", "analyse_taste"]}),
        )

        result = await server.call_tool(
            "recommendation_generate_profile", {"collections": []}
        )

        assert result["success"] is False
        assert result["error_type"] == "unauthorized"

    @pytest.mark.asyncio
    async def test_side_effecting_actions_require_policy(self):
        """Side-effecting actions are denied without Policy."""
        registry = CapabilityRegistry()
        registry.register(ScheduleCapability())
        server = MCPServer(
            registry,
            ExposureMap({"schedule": ["create_schedule"]}),
        )

        from app.mcp_server.context import MCPContext

        result = await server.call_tool(
            "schedule_create_schedule", {}, context=MCPContext(user_id=1)
        )

        assert result["success"] is False
        assert result["error_type"] == "policy_denied"

    @pytest.mark.asyncio
    async def test_authenticated_context_allows_protected_action(self, monkeypatch):
        """auth-required action passes with an authenticated MCPContext."""
        registry = CapabilityRegistry()
        registry.register(RecommendationCapability())
        server = MCPServer(
            registry,
            ExposureMap({"recommendation": ["generate_profile", "analyse_taste"]}),
        )

        from app.mcp_server.context import MCPContext

        async def fake_execute(action_name, **kwargs):
            return {"success": True, "action": action_name}

        monkeypatch.setattr(
            registry.get("recommendation"), "execute", fake_execute
        )

        result = await server.call_tool(
            "recommendation_generate_profile",
            {"collections": []},
            context=MCPContext(user_id=42),
        )
        assert result["success"] is True

    @pytest.mark.asyncio
    async def test_policy_allows_side_effect(self, monkeypatch):
        """Side-effecting action passes with explicit Policy."""
        registry = CapabilityRegistry()
        registry.register(ScheduleCapability())
        server = MCPServer(
            registry,
            ExposureMap({"schedule": ["create_schedule"]}),
        )

        from app.mcp_server.context import MCPContext
        from app.mcp_server.policy import Policy

        async def fake_execute(action_name, **kwargs):
            return {"success": True, "action": action_name}

        monkeypatch.setattr(
            registry.get("schedule"), "execute", fake_execute
        )

        result = await server.call_tool(
            "schedule_create_schedule",
            {"source": "bangumi", "source_id": "42",
             "day_of_week": 0, "start_time": "18:00:00"},
            context=MCPContext(user_id=1),
            policy=Policy(allow_side_effects=True, idempotency_key="create-42"),
        )
        assert result["success"] is True

    @pytest.mark.asyncio
    async def test_non_exposed_tool_is_not_found(self):
        """Calling a non-exposed tool returns error, not unauth."""
        server = self._make_server()  # only anime exposed

        result = await server.call_tool(
            "recommendation_generate_profile", {"collections": []}
        )
        assert result["success"] is False

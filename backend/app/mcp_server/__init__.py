"""MCP server — exposes OtakuNeko capabilities via the Model Context Protocol.

This package wraps registered capabilities (AnimeCapability, etc.) as
standard MCP tools that external clients (Claude Desktop, Cursor, etc.)
can consume through JSON-RPC over stdio.

Uses the same protocol version (2024-11-05) as the existing MCP client
code in ``app/agents/mcp/``.
"""

from __future__ import annotations

import asyncio
import json
import sys
from typing import Any

from app.capabilities.base import BaseCapability
from app.capabilities.registry import CapabilityRegistry
from app.core.logging import get_logger

logger = get_logger(__name__)

RPC_VERSION = "2.0"
PROTOCOL_VERSION = "2024-11-05"
CLIENT_INFO = {"name": "OtakuNeko-MCP-Server", "version": "0.1.0"}


def _build_tool_schema(cap: BaseCapability, action: str) -> dict[str, Any]:
    """Generate an MCP tool definition for a capability action."""
    action_map: dict[str, dict[str, Any]] = {
        "search": {
            "description": "Search anime by keyword, tags, rating, or air date.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "keyword": {"type": "string", "description": "Search keyword"},
                    "subject_types": {
                        "type": "array",
                        "items": {"type": "integer"},
                        "description": "Subject type filter (2=anime, 3=music, etc.)",
                    },
                    "tags": {"type": "array", "items": {"type": "string"}, "description": "Tag filters"},
                    "limit": {"type": "integer", "description": "Max results (default 10)"},
                },
                "required": ["keyword"],
            },
        },
        "get_detail": {
            "description": "Get detailed information about a specific anime subject.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "subject_id": {"type": "integer", "description": "Bangumi subject ID"},
                },
                "required": ["subject_id"],
            },
        },
        "get_staff": {
            "description": "Get production staff information for an anime.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "subject_id": {"type": "integer", "description": "Bangumi subject ID"},
                },
                "required": ["subject_id"],
            },
        },
        "get_cast": {
            "description": "Get voice actor / cast information for an anime.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "subject_id": {"type": "integer", "description": "Bangumi subject ID"},
                },
                "required": ["subject_id"],
            },
        },
        "get_reviews": {
            "description": "Get audience reviews and feedback for an anime.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "subject_id": {"type": "integer", "description": "Bangumi subject ID"},
                },
                "required": ["subject_id"],
            },
        },
    }

    base = action_map.get(action, {})
    return {
        "name": f"{cap.name}_{action}",
        "description": base.get("description", f"{cap.name} {action}"),
        "inputSchema": base.get("inputSchema", {
            "type": "object",
            "properties": {},
        }),
    }


class MCPServer:
    """JSON-RPC server that wraps a CapabilityRegistry as MCP tools."""

    def __init__(self, registry: CapabilityRegistry) -> None:
        self._registry = registry

    def list_tools(self) -> list[dict[str, Any]]:
        """Return MCP tool definitions for all registered capabilities."""
        tools: list[dict[str, Any]] = []
        for name in self._registry.list_names():
            cap = self._registry.get(name)
            # Introspect the capability's known actions and build schemas
            known_actions = ["search", "get_detail", "get_staff", "get_cast", "get_reviews"]
            for action in known_actions:
                tools.append(_build_tool_schema(cap, action))
        return tools

    async def call_tool(self, tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        """Execute a tool call by routing to the correct capability action."""
        for name in self._registry.list_names():
            cap = self._registry.get(name)
            for action in ["search", "get_detail", "get_staff", "get_cast", "get_reviews"]:
                if tool_name == f"{name}_{action}":
                    return await cap.execute(action, **arguments)
        return {"success": False, "error": f"Unknown tool: {tool_name}"}

    async def handle_request(self, request: dict[str, Any]) -> dict[str, Any]:
        """Process a single JSON-RPC request."""
        method = request.get("method", "")
        req_id = request.get("id")

        if method == "initialize":
            return {
                "jsonrpc": RPC_VERSION,
                "id": req_id,
                "result": {
                    "protocolVersion": PROTOCOL_VERSION,
                    "capabilities": {"tools": {}},
                    "serverInfo": CLIENT_INFO,
                },
            }
        elif method == "notifications/initialized":
            return {"jsonrpc": RPC_VERSION, "id": req_id, "result": {}}
        elif method == "tools/list":
            return {
                "jsonrpc": RPC_VERSION,
                "id": req_id,
                "result": {"tools": self.list_tools()},
            }
        elif method == "tools/call":
            params = request.get("params", {})
            tool_name = params.get("name", "")
            arguments = params.get("arguments", {})
            result = await self.call_tool(tool_name, arguments)
            return {
                "jsonrpc": RPC_VERSION,
                "id": req_id,
                "result": {
                    "content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False)}],
                },
            }
        else:
            return {
                "jsonrpc": RPC_VERSION,
                "id": req_id,
                "error": {"code": -32601, "message": f"Method not found: {method}"},
            }

    def handle_response(self, request: dict[str, Any]) -> str:
        """Synchronous wrapper around handle_request for stdio dispatch."""
        return asyncio.get_event_loop().run_until_complete(
            self.handle_request(request)
        )


class StdioServer:
    """Runs an MCPServer over stdin/stdout JSON-RPC."""

    def __init__(self, server: MCPServer) -> None:
        self._server = server

    async def run(self) -> None:
        """Read JSON-RPC requests from stdin, write responses to stdout."""
        reader = asyncio.StreamReader()
        protocol = asyncio.StreamReaderProtocol(reader)
        await asyncio.get_event_loop().connect_read_pipe(lambda: protocol, sys.stdin)

        while True:
            line = await reader.readline()
            if not line:
                break

            try:
                request = json.loads(line.decode("utf-8").strip())
            except json.JSONDecodeError:
                continue

            response = await self._server.handle_request(request)
            sys.stdout.write(json.dumps(response, ensure_ascii=False) + "\n")
            sys.stdout.flush()

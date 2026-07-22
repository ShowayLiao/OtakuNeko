"""Entry point for the OtakuNeko MCP server.

Usage::

    uv run python backend/app/mcp_server/entry.py

This starts a stdio-based MCP server exposing capabilities to any MCP-
compatible client (Claude Desktop, Cursor, etc.).  All registered
capabilities are discoverable through the MCP tools/list endpoint.
"""

from __future__ import annotations

import asyncio

from app.capabilities.anime import AnimeCapability
from app.capabilities.registry import CapabilityRegistry
from app.mcp_server import MCPServer, StdioServer


def build_registry() -> CapabilityRegistry:
    """Build the MCP-001 registry with its authenticated legacy-safe scope."""
    registry = CapabilityRegistry()
    registry.register(AnimeCapability())
    return registry


def main() -> None:
    registry = build_registry()
    server = MCPServer(registry)
    stdio = StdioServer(server)
    asyncio.run(stdio.run())


if __name__ == "__main__":
    main()

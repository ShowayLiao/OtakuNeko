"""Entry point for the OtakuNeko MCP server.

Usage::

    uv run python backend/app/mcp_server/entry.py

This starts a stdio-based MCP server exposing the anime capability
to any MCP-compatible client (Claude Desktop, Cursor, etc.).
"""

from __future__ import annotations

import asyncio

from app.capabilities.anime import AnimeCapability
from app.capabilities.registry import CapabilityRegistry
from app.mcp_server import MCPServer, StdioServer


def main() -> None:
    registry = CapabilityRegistry()
    registry.register(AnimeCapability())
    server = MCPServer(registry)
    stdio = StdioServer(server)
    asyncio.run(stdio.run())


if __name__ == "__main__":
    main()

"""Entry point for the OtakuNeko MCP server.

Usage::

    cd backend
    uv run python -m app.mcp_server.entry

This starts a stdio-based MCP server exposing only explicitly approved
capability actions. Protected tools require a trusted user identity supplied
by the server process environment, never by tool arguments.
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
import os

from app.capabilities.factory import build_capability_registry
from app.capabilities.registry import CapabilityRegistry
from app.mcp_server import ExposureMap, MCPServer, StdioServer
from app.mcp_server.context import MCPContext


def build_registry() -> CapabilityRegistry:
    """Build the registry with all capabilities registered."""
    return build_capability_registry()


def build_exposure(registry: CapabilityRegistry | None = None) -> ExposureMap:
    """Define which capability actions are publicly exposed over MCP.

    MCP-001 scope: Anime (all 5 read-only actions).
    MCP-002 additions: schedule list (read), media (list_rss, library_status).
    """
    exposure = {
        "anime": ["search", "get_detail", "get_staff", "get_cast", "get_reviews"],
        "schedule": ["list_schedules"],
        "media": ["library_status", "list_rss_feeds"],
    }
    canonical_registry = registry or build_registry()
    for capability_name, action_names in exposure.items():
        for action_name in action_names:
            definition = canonical_registry.get_public_definition(action_name, "v1")
            if definition is None or definition.is_side_effect:
                raise RuntimeError(
                    f"MCP exposure is not backed by a read-only Registry action: "
                    f"{capability_name}.{action_name}"
                )
    return ExposureMap(exposure)


def build_context() -> MCPContext:
    """Build trusted stdio identity from server-controlled configuration."""
    raw_user_id = os.getenv("OTAKUNEKO_MCP_USER_ID")
    if raw_user_id is None or not raw_user_id.strip():
        return MCPContext()
    try:
        user_id = int(raw_user_id)
    except ValueError as exc:
        raise ValueError(
            "OTAKUNEKO_MCP_USER_ID must be a positive integer"
        ) from exc
    if user_id <= 0:
        raise ValueError("OTAKUNEKO_MCP_USER_ID must be a positive integer")
    return MCPContext(user_id=user_id)


@asynccontextmanager
async def _request_dependencies():
    """Create mutable backend dependencies for exactly one tool call."""
    from app.db.database import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        yield {"db": db}


async def _run() -> None:
    registry = build_registry()
    exposure = build_exposure(registry)
    server = MCPServer(registry, exposure)
    context = build_context()

    if not context.is_authenticated:
        await StdioServer(server, context=context).run()
        return

    trusted_context = MCPContext(
        user_id=context.user_id,
        dependency_provider=_request_dependencies,
    )
    await StdioServer(server, context=trusted_context).run()


def main() -> None:
    asyncio.run(_run())


if __name__ == "__main__":
    main()

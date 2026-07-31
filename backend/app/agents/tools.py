"""Backward-compatible tool export module.

The canonical implementation lives in the ``app.agents.tools`` package.
This file is retained for older import paths and deliberately contains no
self-imports or duplicate registration side effects.
"""

from app.agents.tools.anime import (
    fetch_audience_reviews,
    get_anime_cast,
    get_anime_info,
    get_anime_staff,
)
from app.agents.tools.datetime import get_current_time
from app.agents.tools.profile import generate_user_profile_tool
from app.agents.tools.search import search_anime_advanced

_LEGACY_PUBLIC_NAMES = (
    "get_anime_info",
    "fetch_audience_reviews",
    "get_anime_staff",
    "get_anime_cast",
    "search_anime_advanced",
    "get_current_time",
    "generate_user_profile_tool",
)


def build_legacy_tools() -> list:
    """Keep legacy callables while validating parity against the Registry."""
    from app.capabilities.factory import build_capability_registry

    legacy_tools = [
        get_anime_info,
        fetch_audience_reviews,
        get_anime_staff,
        get_anime_cast,
        search_anime_advanced,
        get_current_time,
        generate_user_profile_tool,
    ]
    registry = build_capability_registry()
    for tool in legacy_tools:
        if registry.find_action(tool.name) is None:
            raise RuntimeError(f"Legacy tool '{tool.name}' has no registry action")
    if tuple(tool.name for tool in legacy_tools) != _LEGACY_PUBLIC_NAMES:
        raise RuntimeError("Legacy tool order or names diverged from the Registry")
    return legacy_tools


ALL_TOOLS = build_legacy_tools()

__all__ = ["ALL_TOOLS", "build_legacy_tools"]

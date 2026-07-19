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

ALL_TOOLS = [
    get_anime_info,
    fetch_audience_reviews,
    get_anime_staff,
    get_anime_cast,
    search_anime_advanced,
    get_current_time,
    generate_user_profile_tool,
]

__all__ = ["ALL_TOOLS"]

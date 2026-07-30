"""Anime capability — wraps existing anime service functions.

Delegates to the same service layer that the current tools use.
Existing tools and services are NOT modified.
"""

from __future__ import annotations

from typing import Any

from app.capabilities.base import BaseCapability
from app.capabilities.types import ActionDescriptor, CapabilityResult
from app.services.bangumi_service import (
    fetch_subject_by_id,
    get_audience_feedback,
    get_staff_info,
    get_cast_info,
)
from app.services.bangumi_client import search_subjects_advanced
from app.core.logging import get_logger

logger = get_logger(__name__)

_SEARCH_RESULT_SUMMARY_LENGTH = 200


def _simplify_search_results(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "id": item.get("id"),
            "name": item.get("name"),
            "name_cn": item.get("name_cn"),
            "summary": (item.get("summary", "") or "")[:_SEARCH_RESULT_SUMMARY_LENGTH] + "..."
            if item.get("summary")
            else "",
            "score": item.get("rating", {}).get("score", 0),
            "rank": item.get("rating", {}).get("rank", 0),
            "type": item.get("type"),
            "air_date": item.get("air_date"),
            "images": item.get("images", {}),
        }
        for item in items
    ]


class AnimeCapability(BaseCapability):
    """Provides anime information via the existing Bangumi service layer."""

    @property
    def name(self) -> str:
        return "anime"

    @property
    def description(self) -> str:
        return "Search anime, get details, staff, cast, and audience reviews via Bangumi"

    def actions(self) -> list[ActionDescriptor]:
        subject_id_schema: dict[str, Any] = {
            "type": "object",
            "properties": {
                "subject_id": {"type": "integer", "description": "Bangumi subject ID"},
            },
            "required": ["subject_id"],
        }
        return [
            ActionDescriptor(
                name="search",
                public_name="search_anime_advanced",
                description="Search anime by keyword, tags, rating, or air date",
                input_schema={
                    "type": "object",
                    "properties": {
                        "keyword": {"type": "string", "description": "Search keyword"},
                        "subject_types": {
                            "type": "array", "items": {"type": "integer"},
                            "description": "Subject type filter (2=anime)",
                        },
                        "tags": {"type": "array", "items": {"type": "string"}},
                        "limit": {"type": "integer", "description": "Max results (default 10)"},
                    },
                    "required": ["keyword"],
                },
            ),
            ActionDescriptor(
                name="get_detail",
                public_name="get_anime_info",
                description="Get detailed information about a specific anime subject",
                input_schema=subject_id_schema,
            ),
            ActionDescriptor(
                name="get_staff",
                public_name="get_anime_staff",
                description="Get production staff information for an anime",
                input_schema=subject_id_schema,
            ),
            ActionDescriptor(
                name="get_cast",
                public_name="get_anime_cast",
                description="Get voice actor / cast information for an anime",
                input_schema=subject_id_schema,
            ),
            ActionDescriptor(
                name="get_reviews",
                public_name="fetch_audience_reviews",
                description="Get audience reviews and feedback for an anime",
                input_schema=subject_id_schema,
            ),
        ]

    async def execute(self, action: str, **kwargs: Any) -> dict[str, Any]:
        """Dispatch to the appropriate internal action handler."""
        handlers = {
            "search": self._search,
            "get_detail": self._get_detail,
            "get_staff": self._get_staff,
            "get_cast": self._get_cast,
            "get_reviews": self._get_reviews,
        }
        handler = handlers.get(action)
        if handler is None:
            return CapabilityResult.fail(
                f"Unknown action: {action}", error_type="invalid_action"
            ).to_dict()
        try:
            return await handler(**kwargs)
        except Exception as exc:
            logger.error("anime_capability_failed", extra={"action": action, "error": str(exc)})
            return CapabilityResult.fail(str(exc), error_type="internal").to_dict()

    # -- action handlers -------------------------------------------------------

    async def _search(self, **kwargs: Any) -> dict[str, Any]:
        result = await search_subjects_advanced(
            keyword=kwargs.get("keyword", ""),
            subject_types=kwargs.get("subject_types") or [2],
            tags=kwargs.get("tags"),
            rating_ranges=kwargs.get("rating_ranges"),
            air_date_ranges=kwargs.get("air_date_ranges"),
            limit=kwargs.get("limit", 10),
            offset=kwargs.get("offset", 0),
        )
        simplified = _simplify_search_results(result.get("data", []))
        return CapabilityResult.ok(total=result.get("total", 0), results=simplified).to_dict()

    async def _get_detail(self, **kwargs: Any) -> dict[str, Any]:
        subject_id = kwargs["subject_id"]
        result = await fetch_subject_by_id(subject_id)
        return CapabilityResult.ok(**result.model_dump(exclude_none=True)).to_dict()

    async def _get_staff(self, **kwargs: Any) -> dict[str, Any]:
        subject_id = kwargs["subject_id"]
        result = await get_staff_info(subject_id)
        return CapabilityResult.ok(staff=[s.model_dump() for s in result]).to_dict()

    async def _get_cast(self, **kwargs: Any) -> dict[str, Any]:
        subject_id = kwargs["subject_id"]
        result = await get_cast_info(subject_id)
        return CapabilityResult.ok(cast=[c.model_dump() for c in result]).to_dict()

    async def _get_reviews(self, **kwargs: Any) -> dict[str, Any]:
        subject_id = kwargs["subject_id"]
        result = await get_audience_feedback(subject_id)
        return CapabilityResult.ok(**result.model_dump(exclude_none=True)).to_dict()

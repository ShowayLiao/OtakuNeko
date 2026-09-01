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
    get_bangumi_calendar,
    get_bangumi_subject_details,
    get_bangumi_user_info,
    get_staff_info,
    get_cast_info,
)
from app.services.bangumi_client import search_subjects_advanced
from app.core.logging import get_logger

logger = get_logger(__name__)

_SEARCH_RESULT_SUMMARY_LENGTH = 200
_MAX_BATCH_DETAIL_SUBJECTS = 5


def _normalise_tags(raw_tags: Any) -> list[str]:
    names: list[str] = []
    for tag in raw_tags or []:
        if isinstance(tag, dict):
            name = tag.get("name")
        elif isinstance(tag, str):
            name = tag
        else:
            name = None
        if name:
            names.append(str(name))
    return names


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
            "tags": _normalise_tags(item.get("tags")),
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
                description="Get detailed information about one anime subject. Use this after a calendar lookup when more evidence is needed.",
                input_schema=subject_id_schema,
            ),
            ActionDescriptor(
                name="get_detail_batch",
                public_name="get_anime_info_batch",
                description=(
                    "Get detailed information for up to five selected anime subject IDs. "
                    "Use this after get_bangumi_calendar; calendar summaries may be empty."
                ),
                input_schema={
                    "type": "object",
                    "properties": {
                        "subject_ids": {
                            "type": "array",
                            "items": {"type": "integer", "minimum": 1},
                            "minItems": 1,
                            "maxItems": _MAX_BATCH_DETAIL_SUBJECTS,
                        }
                    },
                    "required": ["subject_ids"],
                    "additionalProperties": False,
                },
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
            ActionDescriptor(
                name="get_bangumi_calendar",
                public_name="get_bangumi_calendar",
                description=(
                    "Get the complete current Bangumi broadcast calendar. "
                    "Use get_anime_info_batch with selected subject IDs before answering "
                    "calendar-analysis requests because summaries may be empty."
                ),
                input_schema={"type": "object", "properties": {}, "required": []},
                max_output_fields=8192,
            ),
            ActionDescriptor(
                name="get_bangumi_user_info",
                public_name="get_bangumi_user_info",
                description="Get public profile data for the authenticated user's linked Bangumi account",
                input_schema={"type": "object", "properties": {}, "required": []},
                requires_auth=True,
            ),
        ]

    async def execute(self, action: str, **kwargs: Any) -> dict[str, Any]:
        """Dispatch to the appropriate internal action handler."""
        handlers = {
            "search": self._search,
            "get_detail": self._get_detail,
            "get_detail_batch": self._get_detail_batch,
            "get_staff": self._get_staff,
            "get_cast": self._get_cast,
            "get_reviews": self._get_reviews,
            "get_bangumi_calendar": self._get_calendar,
            "get_bangumi_user_info": self._get_bangumi_user,
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

    async def _get_detail_batch(self, **kwargs: Any) -> dict[str, Any]:
        subject_ids = kwargs.get("subject_ids")
        if (
            not isinstance(subject_ids, list)
            or not subject_ids
            or len(subject_ids) > _MAX_BATCH_DETAIL_SUBJECTS
        ):
            return CapabilityResult.fail(
                "Select between one and five anime subject IDs",
                error_type="invalid_request",
            ).to_dict()
        try:
            result = await get_bangumi_subject_details(subject_ids)
        except ValueError:
            return CapabilityResult.fail(
                "Anime subject IDs did not match the batch detail contract",
                error_type="invalid_request",
            ).to_dict()
        return CapabilityResult.ok(**result).to_dict()

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

    async def _get_calendar(self, **kwargs: Any) -> dict[str, Any]:
        result = await get_bangumi_calendar()
        payload = result.model_dump(mode="json") if hasattr(result, "model_dump") else result
        return CapabilityResult.ok(calendar=payload).to_dict()

    async def _get_bangumi_user(self, **kwargs: Any) -> dict[str, Any]:
        user = kwargs.get("user")
        username = getattr(user, "bangumi_name", None)
        if not isinstance(username, str) or not username.strip():
            return CapabilityResult.fail(
                "Linked Bangumi account is required", error_type="not_configured"
            ).to_dict()
        result = await get_bangumi_user_info(username.strip())
        payload = result.model_dump(mode="json") if hasattr(result, "model_dump") else result
        return CapabilityResult.ok(user=payload).to_dict()

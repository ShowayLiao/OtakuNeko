"""Recommendation capability — wraps existing user profile service.

The capability generates preference profiles and provides candidate
retrieval and ranking inputs. It does NOT generate conversational
prose or invoke an agent from the capability.
"""

from __future__ import annotations

from typing import Any

from app.capabilities.base import BaseCapability
from app.capabilities.types import ActionDescriptor, CapabilityResult
from app.schemas.collection import CollectionSearchBase
from app.services.collection_service import get_user_collections
from app.services.user_profile_service import generate_user_profile
from app.core.logging import get_logger

logger = get_logger(__name__)

_RECOMMEND_FALLBACK_MESSAGE = (
    "No preference data is available yet. "
    "Watch and rate a few anime to get personalized recommendations."
)


class RecommendationCapability(BaseCapability):
    """Provides user preference analysis and recommendation candidates."""

    @property
    def name(self) -> str:
        return "recommendation"

    @property
    def description(self) -> str:
        return (
            "Generate user preference profiles from collection history, "
            "analyse taste affinities, and assemble ranking inputs for "
            "the recommendation agent."
        )

    def actions(self) -> list[ActionDescriptor]:
        return [
            ActionDescriptor(
                name="generate_profile",
                public_name="generate_user_profile_tool",
                description="Generate a user preference profile from collection data",
                input_schema={
                    "type": "object",
                    "properties": {
                        "collections": {
                            "type": "array",
                            "description": "User collection list with subject data",
                            "items": {"type": "object"},
                        },
                    },
                    "required": [],
                },
                requires_auth=True,
            ),
            ActionDescriptor(
                name="analyse_taste",
                public_name="analyse_taste",
                description="Analyse taste affinities and extract quadrant labels",
                input_schema={
                    "type": "object",
                    "properties": {
                        "collections": {
                            "type": "array",
                            "description": "User collection list with subject data",
                            "items": {"type": "object"},
                        },
                    },
                    "required": [],
                },
                requires_auth=True,
            ),
        ]

    async def execute(self, action: str, **kwargs: Any) -> dict[str, Any]:
        handlers: dict[str, Any] = {
            "generate_profile": self._generate_profile,
            "analyse_taste": self._analyse_taste,
        }
        handler = handlers.get(action)
        if handler is None:
            return CapabilityResult.fail(
                f"Unknown action: {action}", error_type="invalid_action"
            ).to_dict()
        try:
            result = await handler(**kwargs)
            if isinstance(result, CapabilityResult):
                return result.to_dict()
            return result
        except Exception as exc:
            logger.error(
                "recommendation_capability_failed",
                extra={"action": action, "error": str(exc)},
            )
            return CapabilityResult.fail(str(exc), error_type="internal").to_dict()

    # -- action handlers -------------------------------------------------------

    async def _generate_profile(self, **kwargs: Any) -> CapabilityResult:
        collections = await self._resolve_collections(kwargs)
        if not collections:
            return CapabilityResult.ok(
                profile={"llm_summary": {"total_rated": 0, "taste_dictionary": {}},
                         "chart_data": {"radar": [], "bar_count": [], "bar_score": []},
                         "watched_ids": []},
                evidence={"source": "empty_history", "message": _RECOMMEND_FALLBACK_MESSAGE},
            )

        profile = generate_user_profile(collections)
        total_rated = profile.get("llm_summary", {}).get("total_rated", 0)

        return CapabilityResult.ok(
            profile=profile,
            evidence={
                "source": "profile",
                "total_rated": total_rated,
                "taste_tags": list(
                    profile.get("llm_summary", {}).get("taste_dictionary", {}).keys()
                )[:20],
            },
        )

    async def _analyse_taste(self, **kwargs: Any) -> CapabilityResult:
        collections = await self._resolve_collections(kwargs)
        if not collections:
            return CapabilityResult.ok(
                quadrants={
                    "core_favorites": [],
                    "time_killers": [],
                    "avoid_tags": [],
                },
                evidence={"source": "empty_history", "message": _RECOMMEND_FALLBACK_MESSAGE},
            )

        profile = generate_user_profile(collections)

        from app.services.user_profile_service import _extract_four_quadrants

        tag_stats: dict[str, Any] = {}
        for tag, tag_data in profile.get("llm_summary", {}).get(
            "taste_dictionary", {}
        ).items():
            count, avg_score = tag_data
            tag_stats[tag] = {"count": count, "avg_score": avg_score}

        quadrants = _extract_four_quadrants(tag_stats) if tag_stats else {
            "core_favorites": [],
            "time_killers": [],
            "avoid_tags": [],
        }

        chart_data = profile.get("chart_data", {})
        return CapabilityResult.ok(
            quadrants=quadrants,
            chart_data=chart_data,
            evidence={
                "source": "profile",
                "total_tags_analysed": len(tag_stats),
            },
        )

    @staticmethod
    async def _resolve_collections(kwargs: dict[str, Any]) -> list[Any]:
        """Load owned data from trusted dependencies, with direct-call compatibility."""
        db = kwargs.get("db")
        user_id = kwargs.get("user_id")
        if db is not None and isinstance(user_id, int) and user_id > 0:
            result = await get_user_collections(
                db, CollectionSearchBase(user_id=user_id, limit=100)
            )
            items = getattr(result, "items", None)
            if items is None and isinstance(result, dict):
                items = result.get("items")
            return [
                item.model_dump(mode="json") if hasattr(item, "model_dump") else item
                for item in (items or [])
            ]
        return list(kwargs.get("collections") or [])

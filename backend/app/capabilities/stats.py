"""Authenticated, read-only dashboard statistics capability."""

from __future__ import annotations

from typing import Any

from app.capabilities.base import BaseCapability
from app.capabilities.types import ActionDescriptor, CapabilityResult
from app.models import SubjectType
from app.services.stats_service import get_collection_statistics, get_user_stats


class StatsCapability(BaseCapability):
    @property
    def name(self) -> str:
        return "stats"

    @property
    def description(self) -> str:
        return "Read dashboard statistics for the authenticated user"

    def actions(self) -> list[ActionDescriptor]:
        return [
            ActionDescriptor(
                name="get_user_stats",
                public_name="get_user_stats",
                description="Get aggregate statistics for the authenticated user",
                input_schema={"type": "object", "properties": {}, "required": []},
                requires_auth=True,
            ),
            ActionDescriptor(
                name="get_collection_statistics",
                public_name="get_collection_statistics",
                description=(
                    "Get complete database-backed collection statistics for the "
                    "authenticated user, including watch-status counts and the "
                    "top three subject tags. Use this for full-collection "
                    "statistics; do not infer them from list_collections."
                ),
                input_schema={
                    "type": "object",
                    "properties": {
                        "subject_type": {
                            "type": "integer",
                            "enum": [1, 2, 3, 4, 6],
                            "default": int(SubjectType.ANIME),
                        }
                    },
                    "required": [],
                },
                output_schema={
                    "type": "object",
                    "properties": {
                        "statistics": {
                            "type": "object",
                            "required": [
                                "subject_type",
                                "total",
                                "status_counts",
                                "top_genres",
                                "complete",
                                "genre_subject_count",
                                "genre_complete",
                            ],
                        }
                    },
                    "required": ["statistics"],
                },
                requires_auth=True,
            ),
        ]

    async def execute(self, action: str, **kwargs: Any) -> dict[str, Any]:
        if action not in {"get_user_stats", "get_collection_statistics"}:
            return CapabilityResult.fail(
                f"Unknown action: {action}", error_type="invalid_action"
            ).to_dict()
        db = kwargs.get("db")
        user_id = kwargs.get("user_id")
        if db is None or not isinstance(user_id, int) or user_id <= 0:
            return CapabilityResult.fail(
                "Trusted db and principal are required", error_type="invalid_args"
            ).to_dict()
        try:
            if action == "get_collection_statistics":
                result = await get_collection_statistics(
                    user_id,
                    db,
                    int(kwargs.get("subject_type") or SubjectType.ANIME),
                )
            else:
                result = await get_user_stats(user_id, db)
        except ValueError as exc:
            return CapabilityResult.fail(str(exc), error_type="invalid_args").to_dict()
        except Exception:
            return CapabilityResult.fail(
                "Statistics operation failed", error_type="internal"
            ).to_dict()
        payload = result.model_dump(mode="json") if hasattr(result, "model_dump") else result
        if action == "get_collection_statistics":
            return CapabilityResult.ok(statistics=payload).to_dict()
        return CapabilityResult.ok(stats=payload).to_dict()

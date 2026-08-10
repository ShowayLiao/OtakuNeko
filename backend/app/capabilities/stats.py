"""Authenticated, read-only dashboard statistics capability."""

from __future__ import annotations

from typing import Any

from app.capabilities.base import BaseCapability
from app.capabilities.types import ActionDescriptor, CapabilityResult
from app.services.stats_service import get_user_stats


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
        ]

    async def execute(self, action: str, **kwargs: Any) -> dict[str, Any]:
        if action != "get_user_stats":
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
            result = await get_user_stats(user_id, db)
        except ValueError as exc:
            return CapabilityResult.fail(str(exc), error_type="invalid_args").to_dict()
        except Exception:
            return CapabilityResult.fail(
                "Statistics operation failed", error_type="internal"
            ).to_dict()
        payload = result.model_dump(mode="json") if hasattr(result, "model_dump") else result
        return CapabilityResult.ok(stats=payload).to_dict()

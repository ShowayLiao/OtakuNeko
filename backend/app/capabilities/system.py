"""Focused capability for local system information."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from app.capabilities.base import BaseCapability
from app.capabilities.types import ActionDescriptor, CapabilityResult


class SystemCapability(BaseCapability):
    """Expose deterministic, read-only local system helpers."""

    @property
    def name(self) -> str:
        return "system"

    @property
    def description(self) -> str:
        return "Read-only local system information"

    def actions(self) -> list[ActionDescriptor]:
        return [
            ActionDescriptor(
                name="current_time",
                public_name="get_current_time",
                description="Get the current local date and time",
                input_schema={"type": "object", "properties": {}},
            )
        ]

    async def execute(self, action: str, **kwargs: Any) -> dict[str, Any]:
        if action != "current_time":
            return CapabilityResult.fail(
                f"Unknown action: {action}",
                error_type="invalid_action",
            ).to_dict()

        now = datetime.now()
        weekday_names = (
            "星期一",
            "星期二",
            "星期三",
            "星期四",
            "星期五",
            "星期六",
            "星期日",
        )
        return CapabilityResult.ok(
            current_time=now.strftime("%Y-%m-%d %H:%M:%S"),
            current_date=now.strftime("%Y-%m-%d"),
            current_year=now.year,
            current_month=now.month,
            current_day=now.day,
            current_hour=now.hour,
            current_minute=now.minute,
            current_second=now.second,
            weekday=now.weekday(),
            weekday_cn=weekday_names[now.weekday()],
            timestamp=now.timestamp(),
            timezone="本地时间",
        ).to_dict()

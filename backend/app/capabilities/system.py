"""Focused capability for local system information."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime
from typing import Any

from app.capabilities.base import BaseCapability
from app.capabilities.types import ActionDescriptor, CapabilityResult

INPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {},
    "additionalProperties": False,
}

_WEEKDAY_NAMES = (
    "星期一",
    "星期二",
    "星期三",
    "星期四",
    "星期五",
    "星期六",
    "星期日",
)

OUTPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "current_time": {"type": "string"},
        "current_date": {"type": "string"},
        "current_year": {"type": "integer"},
        "current_month": {"type": "integer", "minimum": 1, "maximum": 12},
        "current_day": {"type": "integer", "minimum": 1, "maximum": 31},
        "current_hour": {"type": "integer", "minimum": 0, "maximum": 23},
        "current_minute": {"type": "integer", "minimum": 0, "maximum": 59},
        "current_second": {"type": "integer", "minimum": 0, "maximum": 59},
        "weekday": {"type": "integer", "minimum": 0, "maximum": 6},
        "weekday_cn": {
            "type": "string",
            "enum": list(_WEEKDAY_NAMES),
        },
        "timestamp": {"type": "number"},
        "timezone": {"type": "string"},
    },
    "required": [
        "current_time",
        "current_date",
        "current_year",
        "current_month",
        "current_day",
        "current_hour",
        "current_minute",
        "current_second",
        "weekday",
        "weekday_cn",
        "timestamp",
        "timezone",
    ],
    "additionalProperties": False,
}


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
                input_schema=deepcopy(INPUT_SCHEMA),
                output_schema=deepcopy(OUTPUT_SCHEMA),
                requires_auth=False,
            )
        ]

    async def execute(self, action: str, **kwargs: Any) -> dict[str, Any]:
        if action != "current_time":
            return CapabilityResult.fail(
                f"Unknown action: {action}",
                error_type="invalid_action",
            ).to_dict()

        try:
            now = datetime.now()
            weekday = now.weekday()
            payload = {
                "current_time": now.strftime("%Y-%m-%d %H:%M:%S"),
                "current_date": now.strftime("%Y-%m-%d"),
                "current_year": now.year,
                "current_month": now.month,
                "current_day": now.day,
                "current_hour": now.hour,
                "current_minute": now.minute,
                "current_second": now.second,
                "weekday": weekday,
                "weekday_cn": _WEEKDAY_NAMES[weekday],
                "timestamp": now.timestamp(),
                "timezone": "本地时间",
            }
        except Exception:
            return CapabilityResult.fail(
                "System time lookup failed",
                error_type="internal",
            ).to_dict()
        return CapabilityResult.ok(**payload).to_dict()

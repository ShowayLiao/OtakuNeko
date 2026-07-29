"""Cron and timezone helpers for scheduled tasks."""

from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo


def validate_schedule(schedule_expr: str, timezone_name: str) -> None:
    from app.models.agent_task import _validate_schedule

    _validate_schedule(schedule_expr)
    ZoneInfo(timezone_name)


def next_slot(schedule_expr: str, after: datetime, timezone_name: str) -> datetime:
    """Return the next minute matching a small, deterministic cron subset."""
    validate_schedule(schedule_expr, timezone_name)
    zone = ZoneInfo(timezone_name)
    local = after.astimezone(zone).replace(second=0, microsecond=0) + timedelta(minutes=1)
    fields = schedule_expr.split()
    for _ in range(366 * 24 * 60):
        values = (local.minute, local.hour, local.day, local.month, (local.weekday() + 1) % 7)
        if all(_matches(field, value) for field, value in zip(fields, values)):
            return local.astimezone(after.tzinfo or zone)
        local += timedelta(minutes=1)
    raise ValueError("schedule does not contain a matching slot within one year")


def _matches(field: str, value: int) -> bool:
    if field == "*":
        return True
    for part in field.split(","):
        base, _, step = part.partition("/")
        step_value = int(step) if step else 1
        if base == "*" and value % step_value == 0:
            return True
        if base.isdigit() and value == int(base):
            return True
    return False

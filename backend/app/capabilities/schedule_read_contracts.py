"""Read-only schedule result shapes, independent of write descriptors."""

from copy import deepcopy

READ_ACTIONS = frozenset(
    {"list_schedules", "list_schedules_by_day", "list_unified_schedules"}
)


def _object(properties: dict, required: list[str]) -> dict:
    return {
        "type": "object",
        "properties": properties,
        "required": required,
        "additionalProperties": True,
    }


_TEXT = {"type": "string"}
_DAY = {"type": "integer", "minimum": 0, "maximum": 6}
_SCHEDULE = _object(
    {
        "id": {"type": "integer"},
        "source": _TEXT,
        "source_id": _TEXT,
        "day_of_week": _DAY,
        "start_time": _TEXT,
        "watch_day": {"type": ["integer", "null"], "minimum": 0, "maximum": 6},
        "watch_time": {"type": ["string", "null"]},
        "duration": {"type": ["integer", "null"]},
        "watch_type": {"type": ["integer", "null"], "enum": [1, 2, 3, 4, None]},
    },
    ["id", "source", "source_id", "day_of_week", "start_time"],
)
_SUBJECT = _object(
    {"id": {"type": "integer"}, "name": _TEXT, "source": _TEXT, "source_id": _TEXT},
    ["id", "name", "source", "source_id"],
)
_COLLECTION = _object(
    {
        "source": _TEXT,
        "source_id": _TEXT,
        "type": {"type": "integer", "minimum": 1, "maximum": 5},
    },
    ["source", "source_id", "type"],
)
_UNIFIED = _object(
    {
        "schedule": _SCHEDULE,
        "subject": {"anyOf": [_SUBJECT, {"type": "null"}]},
        "collection": {"anyOf": [_COLLECTION, {"type": "null"}]},
    },
    ["schedule", "subject", "collection"],
)


def output_schema(action: str) -> dict:
    return deepcopy(
        _object(
            {
                "schedules": {
                    "type": "array",
                    "items": _UNIFIED
                    if action == "list_unified_schedules"
                    else _SCHEDULE,
                },
                "count": {"type": "integer", "minimum": 0},
            },
            ["schedules", "count"],
        )
    )

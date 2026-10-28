"""Schedule write contracts; existing read views and REST DTOs stay separate."""

from copy import deepcopy
from typing import Any

WRITE_ACTIONS = frozenset(
    {
        "create_schedule",
        "update_schedule",
        "delete_schedule",
        "upsert_schedule",
        "bulk_upsert_schedules",
        "sync_bangumi_schedule",
    }
)


def input_schema(schema: dict[str, Any]) -> dict[str, Any]:
    value = deepcopy(schema)

    def close(node: dict[str, Any]) -> None:
        if node.get("type") == "object":
            node["additionalProperties"] = False
            for name, child in node.get("properties", {}).items():
                if name == "source_id":
                    child.update(minLength=1, maxLength=20)
                elif name == "watch_type":
                    child["enum"] = [1, 2, 3, 4, None]
                close(child)
        if isinstance(node.get("items"), dict):
            close(node["items"])

    close(value)
    return value


def _object(properties: dict, required: list[str]) -> dict:
    return {
        "type": "object",
        "properties": properties,
        "required": required,
        "additionalProperties": True,
    }


_TEXT = {"type": "string"}
_SCHEDULE = _object(
    {
        "id": {"type": "integer"},
        "user_id": {"type": "integer"},
        "source": _TEXT,
        "source_id": _TEXT,
        "day_of_week": {"type": "integer", "minimum": 0, "maximum": 6},
        "start_time": _TEXT,
        "watch_day": {"type": ["integer", "null"], "minimum": 0, "maximum": 6},
        "watch_time": {"type": ["string", "null"]},
        "watch_type": {"type": ["integer", "null"], "enum": [1, 2, 3, 4, None]},
        "duration": {"type": ["integer", "null"]},
    },
    ["id", "source", "source_id", "day_of_week", "start_time"],
)
_SUBJECT = _object(
    {
        "id": {"type": "integer", "minimum": 0},
        "name": _TEXT,
        "source": _TEXT,
        "source_id": _TEXT,
    },
    ["id", "name", "source", "source_id"],
)
_SYNC_ITEM = _object(
    {
        "subject": _SUBJECT,
        "collection": {"type": ["object", "null"]},
    },
    ["subject", "collection"],
)


def output_schema(action: str) -> dict[str, Any]:
    if action == "delete_schedule":
        return _object({"deleted": {"type": "boolean", "const": True}}, ["deleted"])
    if action in {"bulk_upsert_schedules", "sync_bangumi_schedule"}:
        return deepcopy(
            _object(
                {
                    "schedules": {
                        "type": "array",
                        "items": _SYNC_ITEM
                        if action == "sync_bangumi_schedule"
                        else _SCHEDULE,
                    },
                    "count": {"type": "integer", "minimum": 0},
                },
                ["schedules", "count"],
            )
        )
    return deepcopy(_object({"schedule": _SCHEDULE}, ["schedule"]))

"""Minimal successful catalog payloads, matching the unified domain views."""

from copy import deepcopy
from typing import Any


def _object(properties: dict, required: list[str]) -> dict:
    return {
        "type": "object",
        "properties": properties,
        "required": required,
        "additionalProperties": True,
    }


_TEXT = {"type": "string"}
_SUBJECT = _object(
    {"id": {"type": "integer"}, "name": _TEXT, "source": _TEXT, "source_id": _TEXT},
    ["id", "name", "source", "source_id"],
)
_UNIFIED = _object(
    {
        "subject": {"anyOf": [_SUBJECT, {"type": "null"}]},
        "collection": {"type": ["object", "null"]},
    },
    ["subject", "collection"],
)
_SEARCH = _object(
    {
        "total": {"type": "integer", "minimum": 0},
        "subjects": {"type": "array", "items": _UNIFIED},
    },
    ["total", "subjects"],
)
_OUTPUTS = {
    "get_subject": _object({"subject": _UNIFIED}, ["subject"]),
    "search_local_subjects": _SEARCH,
    "search_remote_subjects": _SEARCH,
    "search_mixed_subjects": _SEARCH,
    "get_subject_air_time": _object(
        {
            "source": _TEXT,
            "source_id": _TEXT,
            "air_time": {"type": ["string", "null"]},
            "air_weekday": {"type": ["integer", "null"], "minimum": 1, "maximum": 7},
        },
        ["source", "source_id", "air_time", "air_weekday"],
    ),
}


def output_schema(action: str) -> dict[str, Any]:
    """Keep individual Registry descriptors independent of schema mutation."""
    return deepcopy(_OUTPUTS[action])

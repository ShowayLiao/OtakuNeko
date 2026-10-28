"""Minimal successful Anime payload contracts, independent of provider objects."""

from copy import deepcopy
from typing import Any


def _object(properties: dict, required: list[str]) -> dict:
    return {
        "type": "object",
        "properties": properties,
        "required": required,
        "additionalProperties": True,
    }


def _array(items: dict) -> dict:
    return {"type": "array", "items": items}


_TEXT = {"type": "string"}
_ID = {"type": "integer"}
_DETAIL = _object(
    {"id": _ID, "name": _TEXT, "summary": _TEXT}, ["id", "name", "summary"]
)
_DAYS = _array(
    _object(
        {
            "weekday": {"type": "object"},
            "items": _array(_object({"id": _ID}, ["id"])),
        },
        ["weekday", "items"],
    )
)

_OUTPUTS = {
    "search": _object(
        {
            "total": {"type": "integer", "minimum": 0},
            "results": _array(_object({"id": _ID, "name": _TEXT}, ["id", "name"])),
        },
        ["total", "results"],
    ),
    "get_detail": _DETAIL,
    "get_detail_batch": _object(
        {"details": _array(_DETAIL), "failed_subject_ids": _array(_ID)},
        ["details", "failed_subject_ids"],
    ),
    "get_staff": _object(
        {"staff": _array(_object({"name": _TEXT, "role": _TEXT}, ["name", "role"]))},
        ["staff"],
    ),
    "get_cast": _object(
        {
            "cast": _array(
                _object(
                    {"character_name": _TEXT, "role": _TEXT, "cv_names": _array(_TEXT)},
                    ["character_name", "role", "cv_names"],
                )
            )
        },
        ["cast"],
    ),
    "get_reviews": _object(
        {
            "subject_id": _ID,
            "comments": _array(_object({"content": _TEXT}, ["content"])),
            "reviews": _array(
                _object({"title": _TEXT, "summary": _TEXT}, ["title", "summary"])
            ),
        },
        ["subject_id", "comments", "reviews"],
    ),
    # The domain RootModel serializes to a list. Preserve the existing dict/days
    # compatibility shape used by non-provider adapters as an explicit branch.
    "get_bangumi_calendar": _object(
        {"calendar": {"anyOf": [_DAYS, _object({"days": _DAYS}, ["days"])]}},
        ["calendar"],
    ),
    "get_bangumi_user_info": _object(
        {"user": _object({"id": _ID, "username": _TEXT}, ["id", "username"])}, ["user"]
    ),
}


def output_schema(action: str) -> dict[str, Any]:
    """Return a fresh schema so callers cannot mutate another action's contract."""
    return deepcopy(_OUTPUTS[action])

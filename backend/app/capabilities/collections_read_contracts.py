"""Successful owned collection views; write contracts remain independent."""

from copy import deepcopy


READ_ACTIONS = frozenset({"list_collections", "get_collection", "search_collections"})


def _object(properties: dict, required: list[str]) -> dict:
    return {
        "type": "object",
        "properties": properties,
        "required": required,
        "additionalProperties": True,
    }


_TEXT = {"type": "string"}
_COLLECTION = _object(
    {
        "source": _TEXT,
        "source_id": _TEXT,
        "type": {"type": "integer", "minimum": 1, "maximum": 5},
    },
    ["source", "source_id", "type"],
)
_SUBJECT = _object(
    {"id": {"type": "integer"}, "name": _TEXT, "source": _TEXT, "source_id": _TEXT},
    ["id", "name", "source", "source_id"],
)
_UNIFIED = _object(
    {"collection": _COLLECTION, "subject": {"anyOf": [_SUBJECT, {"type": "null"}]}},
    ["collection", "subject"],
)
_PAGE = _object(
    {
        "total": {"type": "integer", "minimum": 0},
        "collections": {"type": "array", "items": _UNIFIED},
    },
    ["total", "collections"],
)
_OUTPUTS = {
    "list_collections": _PAGE,
    "search_collections": _PAGE,
    "get_collection": _object({"collection": _UNIFIED}, ["collection"]),
}


def output_schema(action: str) -> dict:
    return deepcopy(_OUTPUTS[action])

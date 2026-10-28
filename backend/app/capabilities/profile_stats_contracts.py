"""Minimal executable successful profile and statistics contracts."""

from copy import deepcopy


def _object(properties: dict, required: list[str]) -> dict:
    return {
        "type": "object",
        "properties": properties,
        "required": required,
        "additionalProperties": True,
    }


_COUNT = {"type": "integer", "minimum": 0}
_TEXT = {"type": "string"}
_CHART = _object(
    {
        key: {"type": "array", "items": {"type": "object"}}
        for key in ("radar", "bar_count", "bar_score")
    },
    ["radar", "bar_count", "bar_score"],
)
_EVIDENCE = _object(
    {"source": {"type": "string", "enum": ["profile", "empty_history"]}}, ["source"]
)
_PROFILE = _object(
    {
        "llm_summary": _object(
            {"total_rated": _COUNT, "taste_dictionary": {"type": "object"}},
            ["total_rated", "taste_dictionary"],
        ),
        "chart_data": _CHART,
        "watched_ids": {"type": "array", "items": {"type": "integer"}},
    },
    ["llm_summary", "chart_data", "watched_ids"],
)
_COUNTS = ("anime", "books", "music", "games", "real", "total")
_STATUSES = ("wish", "watched", "watching", "on_hold", "dropped")
_STATISTICS = _object(
    {
        "subject_type": {"type": "integer", "enum": [1, 2, 3, 4, 6]},
        "total": _COUNT,
        "status_counts": _object({key: _COUNT for key in _STATUSES}, list(_STATUSES)),
        "top_genres": {
            "type": "array",
            "maxItems": 3,
            "items": _object({"name": _TEXT, "count": _COUNT}, ["name", "count"]),
        },
        "complete": {"type": "boolean"},
        "genre_subject_count": _COUNT,
        "genre_complete": {"type": "boolean"},
    },
    [
        "subject_type",
        "total",
        "status_counts",
        "top_genres",
        "complete",
        "genre_subject_count",
        "genre_complete",
    ],
)
_OUTPUTS = {
    "generate_profile": _object(
        {"profile": _PROFILE, "evidence": _EVIDENCE}, ["profile", "evidence"]
    ),
    "analyse_taste": _object(
        {
            "quadrants": _object(
                {
                    key: {"type": "array", "items": _TEXT}
                    for key in ("core_favorites", "time_killers", "avoid_tags")
                },
                ["core_favorites", "time_killers", "avoid_tags"],
            ),
            "chart_data": _CHART,
            "evidence": _EVIDENCE,
        },
        ["quadrants", "evidence"],
    ),
    "get_user_stats": _object(
        {"stats": _object({key: _COUNT for key in _COUNTS}, list(_COUNTS))}, ["stats"]
    ),
    "get_collection_statistics": _object({"statistics": _STATISTICS}, ["statistics"]),
}


def output_schema(action: str) -> dict:
    return deepcopy(_OUTPUTS[action])

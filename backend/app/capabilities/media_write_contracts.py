"""Closed input and safe success output contracts for RSS writes."""

from copy import deepcopy

from app.schemas.rss import RssRule

WRITE_ACTIONS = frozenset(
    {
        "add_rss_feed",
        "upsert_rss_feed",
        "remove_rss_feed",
        "set_rss_rule",
        "remove_rss_rule",
    }
)


def write_input_schema(schema: dict) -> dict:
    value = deepcopy(schema)
    value["additionalProperties"] = False
    if "rule" in value["properties"]:
        value["properties"]["rule"] = RssRule.model_json_schema()
    return value


WRITE_OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "operation": {
            "type": "object",
            "properties": {
                "status": {"type": "string", "enum": ["succeeded"]},
                "message": {"type": "string"},
            },
            "required": ["status", "message"],
            "additionalProperties": False,
        },
        "idempotency_key": {"type": ["string", "null"]},
    },
    "required": ["operation", "idempotency_key"],
    "additionalProperties": True,
}

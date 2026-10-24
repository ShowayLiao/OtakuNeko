"""Success contracts for authenticated collection mutations."""

from copy import deepcopy

from app.capabilities.collections_read_contracts import output_schema as read_output


WRITE_ACTIONS = frozenset(
    {
        "create_collection",
        "update_collection",
        "delete_collection",
        "upsert_collection",
        "batch_upsert_collections",
        "import_json_collections",
        "sync_bangumi_collections",
        "sync_douban_collections",
    }
)


def output_schema(action: str) -> dict:
    unified = read_output("get_collection")
    if action == "upsert_collection":
        return unified
    if action in {"create_collection", "update_collection"}:
        collection = unified["properties"]["collection"]["properties"]["collection"]
        properties = {"collection": collection}
    elif action == "delete_collection":
        properties = {"deleted": {"type": "boolean", "const": True}}
    else:
        properties = {"processed_count": {"type": "integer", "minimum": 0}}
        if action == "batch_upsert_collections":
            properties["requested_count"] = {"type": "integer", "minimum": 0}
    return deepcopy(
        {
            "type": "object",
            "properties": properties,
            "required": list(properties),
            "additionalProperties": True,
        }
    )

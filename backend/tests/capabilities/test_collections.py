from __future__ import annotations

import pytest

from app.capabilities.collections import CollectionCapability


def test_collection_actions_hide_runtime_identity_and_mark_writes():
    capability = CollectionCapability()
    actions = {action.name: action for action in capability.actions()}

    assert {
        "list_collections",
        "get_collection",
        "search_collections",
    } <= actions.keys()
    assert {
        "create_collection",
        "update_collection",
        "delete_collection",
        "upsert_collection",
        "batch_upsert_collections",
        "import_json_collections",
        "sync_bangumi_collections",
        "sync_douban_collections",
    } <= actions.keys()
    for action in actions.values():
        assert "user_id" not in action.input_schema.get("properties", {})
    assert all(
        actions[name].is_side_effect
        for name in {
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


@pytest.mark.asyncio
async def test_list_collections_uses_trusted_user_id(monkeypatch):
    captured: dict[str, object] = {}

    async def fake_list(db, search_data):
        captured["db"] = db
        captured["user_id"] = search_data.user_id
        return type(
            "ListResult",
            (),
            {"model_dump": lambda self, **_: {"total": 0, "items": []}},
        )()

    monkeypatch.setattr("app.capabilities.collections.get_user_collections", fake_list)
    result = await CollectionCapability().execute(
        "list_collections", db="trusted-db", user_id=7, limit=25
    )

    assert result["success"] is True
    assert captured == {"db": "trusted-db", "user_id": 7}


@pytest.mark.asyncio
async def test_collection_read_requires_trusted_dependencies():
    result = await CollectionCapability().execute("list_collections")

    assert result["success"] is False
    assert result["error_type"] == "invalid_args"

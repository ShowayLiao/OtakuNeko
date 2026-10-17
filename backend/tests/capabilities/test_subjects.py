from __future__ import annotations

import pytest

from app.capabilities.subjects import SubjectCapability


def test_subject_actions_are_read_only_and_hide_runtime_identity():
    capability = SubjectCapability()
    actions = capability.actions()

    assert {action.name for action in actions} == {
        "get_subject",
        "search_local_subjects",
        "search_remote_subjects",
        "search_mixed_subjects",
        "get_subject_air_time",
    }
    assert all(not action.is_side_effect for action in actions)
    assert all(
        "user_id" not in action.input_schema.get("properties", {}) for action in actions
    )


@pytest.mark.asyncio
async def test_local_subject_search_uses_trusted_user_id(monkeypatch):
    captured: dict[str, object] = {}

    async def fake_search(db, search_data):
        captured["db"] = db
        captured["user_id"] = search_data.user_id
        return type(
            "ListResult",
            (),
            {"model_dump": lambda self, **_: {"total": 0, "items": []}},
        )()

    monkeypatch.setattr("app.capabilities.subjects.search_subject_by_name", fake_search)
    result = await SubjectCapability().execute(
        "search_local_subjects", db="trusted-db", user_id=9, keyword="eva"
    )

    assert result["success"] is True
    assert captured == {"db": "trusted-db", "user_id": 9}

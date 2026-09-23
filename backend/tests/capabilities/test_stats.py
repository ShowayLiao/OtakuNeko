from __future__ import annotations

import pytest

from app.capabilities.stats import StatsCapability


def test_stats_is_authenticated_read_only_capability():
    actions = {action.name: action for action in StatsCapability().actions()}
    action = actions["get_user_stats"]

    assert action.name == "get_user_stats"
    assert action.requires_auth is True
    assert action.is_side_effect is False
    assert "user_id" not in action.input_schema.get("properties", {})


def test_collection_statistics_is_authenticated_read_only_action():
    actions = {action.name: action for action in StatsCapability().actions()}
    action = actions["get_collection_statistics"]

    assert action.requires_auth is True
    assert action.is_side_effect is False
    assert "user_id" not in action.input_schema.get("properties", {})
    assert "subject_type" in action.input_schema.get("properties", {})


@pytest.mark.asyncio
async def test_stats_uses_trusted_user_id(monkeypatch):
    captured: dict[str, object] = {}

    async def fake_stats(user_id, db):
        captured.update(user_id=user_id, db=db)
        return type("Stats", (), {"model_dump": lambda self, **_: {"total": 3}})()

    monkeypatch.setattr("app.capabilities.stats.get_user_stats", fake_stats)
    result = await StatsCapability().execute(
        "get_user_stats", db="trusted-db", user_id=11
    )

    assert result == {"success": True, "stats": {"total": 3}}
    assert captured == {"user_id": 11, "db": "trusted-db"}


@pytest.mark.asyncio
async def test_collection_statistics_uses_trusted_user_id(monkeypatch):
    captured: dict[str, object] = {}

    async def fake_statistics(user_id, db, subject_type):
        captured.update(user_id=user_id, db=db, subject_type=subject_type)
        return type(
            "Statistics",
            (),
            {"model_dump": lambda self, **_: {"total": 768, "complete": True}},
        )()

    monkeypatch.setattr(
        "app.capabilities.stats.get_collection_statistics", fake_statistics
    )
    result = await StatsCapability().execute(
        "get_collection_statistics", db="trusted-db", user_id=11, subject_type=2
    )

    assert result == {
        "success": True,
        "statistics": {"total": 768, "complete": True},
    }
    assert captured == {"user_id": 11, "db": "trusted-db", "subject_type": 2}

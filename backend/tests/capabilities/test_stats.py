from __future__ import annotations

import pytest

from app.capabilities.stats import StatsCapability


def test_stats_is_authenticated_read_only_capability():
    action = StatsCapability().actions()[0]

    assert action.name == "get_user_stats"
    assert action.requires_auth is True
    assert action.is_side_effect is False
    assert "user_id" not in action.input_schema.get("properties", {})


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

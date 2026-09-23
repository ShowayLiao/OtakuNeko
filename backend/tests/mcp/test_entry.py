"""Tests for the MCP stdio entry-point composition and trusted context."""

import pytest

from app.mcp_server.entry import build_context, build_registry, build_exposure


def test_registry_contains_all_capabilities():
    registry = build_registry()
    assert "anime" in registry.list_names()
    assert "recommendation" in registry.list_names()
    assert "schedule" in registry.list_names()
    assert "media" in registry.list_names()
    assert "system" in registry.list_names()
    assert registry.get_public_definition("get_current_time", "v1") is not None


def test_exposure_map_limits_to_approved_actions():
    exposure = build_exposure()
    actions = exposure.capabilities

    # Anime: all 5 read-only actions
    assert actions["anime"] == [
        "search", "get_detail", "get_staff", "get_cast", "get_reviews",
    ]

    # Schedule: only list_schedules (read-only)
    assert actions["schedule"] == ["list_schedules"]

    # Media: status and RSS list (read-only)
    assert set(actions["media"]) == {"library_status", "list_rss_feeds"}

    # Recommendation: not exposed in MCP
    assert "recommendation" not in actions


def test_context_is_anonymous_without_trusted_environment(monkeypatch):
    monkeypatch.delenv("OTAKUNEKO_MCP_USER_ID", raising=False)
    assert build_context().is_authenticated is False


def test_context_uses_server_environment_identity(monkeypatch):
    monkeypatch.setenv("OTAKUNEKO_MCP_USER_ID", "42")
    context = build_context()
    assert context.user_id == 42
    assert context.is_authenticated is True


def test_context_rejects_invalid_environment_identity(monkeypatch):
    monkeypatch.setenv("OTAKUNEKO_MCP_USER_ID", "not-an-integer")
    with pytest.raises(ValueError, match="OTAKUNEKO_MCP_USER_ID"):
        build_context()
